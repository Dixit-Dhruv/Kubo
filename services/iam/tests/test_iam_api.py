from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from kubo_iam.models import ApiToken, Membership, Organization, User
from kubo_iam.security import hash_api_token, hash_password, verify_password


def create_user(sessions, email: str, password: str = "correct horse battery") -> User:
    with sessions() as session:
        user = User(email=email, password_hash=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def login(client, email: str, password: str = "correct horse battery") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_health_endpoints(test_context):
    client, _ = test_context

    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_password_hashing_enforces_minimum_and_verifies():
    with pytest.raises(ValueError, match="12 characters"):
        hash_password("too short")

    encoded = hash_password("correct horse battery")

    assert encoded.startswith("$argon2id$")
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("wrong password", encoded)


def test_login_stores_only_token_hash_and_logout_revokes_it(test_context):
    client, sessions = test_context
    user = create_user(sessions, "owner@example.com")

    token = login(client, "OWNER@example.com")
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == user.email

    with sessions() as session:
        stored = session.scalar(select(ApiToken).where(ApiToken.user_id == user.id))
        assert stored is not None
        assert stored.token_hash == hash_api_token(token)
        assert token not in stored.token_hash
        assert stored.expires_at.replace(tzinfo=UTC) - stored.created_at.replace(tzinfo=UTC) == timedelta(hours=1)

    response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 204
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_token_is_rejected(test_context):
    client, sessions = test_context
    user = create_user(sessions, "expired@example.com")
    token = login(client, user.email)

    with sessions() as session:
        stored = session.scalar(select(ApiToken).where(ApiToken.user_id == user.id))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_non_ascii_bearer_token_is_rejected():
    from kubo_iam.dependencies import get_auth_context

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="\u2603")
    with pytest.raises(HTTPException) as error:
        get_auth_context(credentials=credentials, session=None)
    assert error.value.status_code == 401


def test_login_rate_limit_is_applied(test_context):
    client, _ = test_context
    responses = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "missing@example.com", "password": "not a valid password"},
        )
        for _ in range(6)
    ]

    assert all(response.status_code == 401 for response in responses[:5])
    assert responses[5].status_code == 429


def test_organization_membership_roles_and_isolation(test_context):
    client, sessions = test_context
    owner = create_user(sessions, "owner@example.com")
    admin = create_user(sessions, "admin@example.com")
    member = create_user(sessions, "member@example.com")
    outsider = create_user(sessions, "outsider@example.com")
    owner_headers = {"Authorization": f"Bearer {login(client, owner.email)}"}
    admin_headers = {"Authorization": f"Bearer {login(client, admin.email)}"}
    outsider_headers = {"Authorization": f"Bearer {login(client, outsider.email)}"}

    created = client.post("/api/v1/organizations", headers=owner_headers, json={"name": "Kubo Lab"})
    assert created.status_code == 201
    organization_id = created.json()["id"]
    organization_uuid = UUID(organization_id)
    assert created.json()["role"] == "owner"

    with sessions() as session:
        owner_membership = session.scalar(
            select(Membership).where(
                Membership.organization_id == organization_uuid,
                Membership.user_id == owner.id,
            )
        )
        assert owner_membership is not None
        assert owner_membership.role == "owner"
        assert session.get(Organization, organization_uuid) is not None

    add_admin = client.put(
        f"/api/v1/organizations/{organization_id}/members",
        headers=owner_headers,
        json={"user_id": str(admin.id), "role": "admin"},
    )
    assert add_admin.status_code == 200

    add_member = client.put(
        f"/api/v1/organizations/{organization_id}/members",
        headers=admin_headers,
        json={"user_id": str(member.id), "role": "member"},
    )
    assert add_member.status_code == 200

    denied_promotion = client.put(
        f"/api/v1/organizations/{organization_id}/members",
        headers=admin_headers,
        json={"user_id": str(member.id), "role": "admin"},
    )
    assert denied_promotion.status_code == 403

    hidden_org = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers=outsider_headers,
    )
    assert hidden_org.status_code == 404

    member_list = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers=owner_headers,
    )
    assert member_list.status_code == 200
    assert {item["email"] for item in member_list.json()} == {
        owner.email,
        admin.email,
        member.email,
    }

    with sessions() as session:
        assert session.scalar(
            select(Membership.id).where(
                Membership.organization_id == organization_uuid,
                Membership.user_id == outsider.id,
            )
        ) is None


def test_owner_cannot_be_removed_and_admin_cannot_manage_admins(test_context):
    client, sessions = test_context
    owner = create_user(sessions, "owner@example.com")
    admin = create_user(sessions, "admin@example.com")
    owner_headers = {"Authorization": f"Bearer {login(client, owner.email)}"}
    admin_headers = {"Authorization": f"Bearer {login(client, admin.email)}"}

    organization = client.post(
        "/api/v1/organizations",
        headers=owner_headers,
        json={"name": "Protected org"},
    ).json()
    organization_id = organization["id"]
    client.put(
        f"/api/v1/organizations/{organization_id}/members",
        headers=owner_headers,
        json={"user_id": str(admin.id), "role": "admin"},
    )

    remove_owner = client.delete(
        f"/api/v1/organizations/{organization_id}/members/{owner.id}",
        headers=owner_headers,
    )
    remove_admin = client.delete(
        f"/api/v1/organizations/{organization_id}/members/{admin.id}",
        headers=admin_headers,
    )

    assert remove_owner.status_code == 409
    assert remove_admin.status_code == 403
