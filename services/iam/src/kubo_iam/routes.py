from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kubo_iam.database import get_db
from kubo_iam.dependencies import AuthContext, OWNER_ADMIN, get_auth_context, get_current_user, require_membership
from kubo_iam.models import Membership, MembershipRole, Organization, User
from kubo_iam.schemas import (
    LoginRequest,
    MemberResponse,
    MembershipUpsert,
    OrganizationCreate,
    OrganizationResponse,
    TokenResponse,
    UserResponse,
)
from kubo_iam.security import create_api_token, normalize_email, verify_password

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/v1")


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(
    request: Request,
    payload: LoginRequest,
    session: Session = Depends(get_db),
) -> TokenResponse:
    user = session.scalar(select(User).where(User.email == normalize_email(str(payload.email))))
    if not verify_password(payload.password, user.password_hash if user else None) or user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    token_value, token_record = create_api_token(user.id)
    session.add(token_record)
    session.commit()
    return TokenResponse(access_token=token_value, expires_at=token_record.expires_at)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    context: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_db),
) -> Response:
    context.token.revoked_at = datetime.now(UTC)
    session.add(context.token)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> OrganizationResponse:
    organization = Organization(name=payload.name)
    session.add(organization)
    session.flush()
    membership = Membership(
        organization_id=organization.id,
        user_id=user.id,
        role=MembershipRole.OWNER.value,
    )
    session.add(membership)
    session.commit()
    session.refresh(organization)
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        role=membership.role,
        created_at=organization.created_at,
    )


@router.get("/organizations", response_model=list[OrganizationResponse])
def list_organizations(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[OrganizationResponse]:
    rows = session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.created_at, Organization.id)
    )
    return [
        OrganizationResponse(
            id=organization.id,
            name=organization.name,
            role=role,
            created_at=organization.created_at,
        )
        for organization, role in rows
    ]


@router.get("/organizations/{organization_id}/members", response_model=list[MemberResponse])
def list_members(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[MemberResponse]:
    require_membership(session, organization_id, user.id, OWNER_ADMIN)
    rows = session.execute(
        select(Membership, User.email)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at, Membership.user_id)
    )
    return [
        MemberResponse(
            user_id=membership.user_id,
            email=email,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, email in rows
    ]


@router.put(
    "/organizations/{organization_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_200_OK,
)
def upsert_member(
    organization_id: UUID,
    payload: MembershipUpsert,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> MemberResponse:
    actor = require_membership(session, organization_id, user.id, OWNER_ADMIN)
    if actor.role == MembershipRole.ADMIN.value and payload.role != MembershipRole.MEMBER.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins may assign the member role only.")

    target_user = session.get(User, payload.user_id)
    if target_user is None or not target_user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    membership = session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == payload.user_id,
        )
    )
    if membership is not None and membership.role == MembershipRole.OWNER.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization ownership cannot be changed here.")

    if membership is None:
        membership = Membership(
            organization_id=organization_id,
            user_id=payload.user_id,
            role=payload.role,
        )
        session.add(membership)
    else:
        if actor.role == MembershipRole.ADMIN.value and membership.role == MembershipRole.ADMIN.value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins cannot modify another admin.")
        membership.role = payload.role

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Membership could not be updated.")
    session.refresh(membership)
    return MemberResponse(
        user_id=membership.user_id,
        email=target_user.email,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.delete(
    "/organizations/{organization_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    organization_id: UUID,
    member_user_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    actor = require_membership(session, organization_id, user.id, OWNER_ADMIN)
    membership = session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == member_user_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    if membership.role == MembershipRole.OWNER.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization ownership cannot be removed here.")
    if actor.role == MembershipRole.ADMIN.value and membership.role != MembershipRole.MEMBER.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins may remove members only.")

    session.delete(membership)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
