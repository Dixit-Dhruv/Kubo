from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from kubo_iam.database import get_db
from kubo_iam.models import ApiToken, Membership, MembershipRole, User
from kubo_iam.security import as_utc, hash_api_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    token: ApiToken


def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
) -> AuthContext:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    if not credentials.credentials.isascii():
        raise unauthorized

    token = session.scalar(
        select(ApiToken)
        .options(joinedload(ApiToken.user))
        .where(ApiToken.token_hash == hash_api_token(credentials.credentials))
    )
    if token is None or token.revoked_at is not None or as_utc(token.expires_at) <= datetime.now(UTC):
        raise unauthorized
    if not token.user.is_active:
        raise unauthorized
    return AuthContext(user=token.user, token=token)


def get_current_user(context: AuthContext = Depends(get_auth_context)) -> User:
    return context.user


def require_membership(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
    allowed_roles: set[str],
) -> Membership:
    membership = session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    if membership.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient organization permissions.")
    return membership


OWNER_ADMIN = {MembershipRole.OWNER.value, MembershipRole.ADMIN.value}
