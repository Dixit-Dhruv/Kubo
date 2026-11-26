import argparse
from datetime import UTC, datetime
from getpass import getpass
import os
from pathlib import Path
import sys
from uuid import UUID

from alembic import command
from alembic.config import Config
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kubo_iam.config import get_settings
from kubo_iam.database import SessionLocal
from kubo_iam.models import BootstrapClaim, ServiceCredential, User
from kubo_iam.security import (
    create_service_credential as make_service_credential,
    hash_password,
    normalize_email,
)

SERVICE_ROOT = Path(os.environ.get("KUBO_IAM_SERVICE_ROOT", Path(__file__).resolve().parents[2]))
SERVICE_SCOPES = {
    "api-gateway": {"iam:authenticate"},
    "compute-api": {"iam:authorize"},
    "compute-worker": {"iam:authorize", "network:attachments:manage"},
    "networking": {"iam:authorize"},
}


def upgrade_database() -> None:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    database_url = get_settings().database_url.replace("%", "%%")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def prompt_for_password() -> str:
    password = getpass("Password (minimum 12 characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    return hash_password(password)


def create_user(
    session: Session,
    email: str,
    password_hash: str,
    is_platform_admin: bool = False,
) -> User:
    try:
        normalized_email = normalize_email(validate_email(email, check_deliverability=False).normalized)
    except EmailNotValidError as exc:
        raise ValueError("A valid email address is required.") from exc
    existing = session.scalar(select(User.id).where(User.email == normalized_email))
    if existing is not None:
        raise ValueError("A user with that email already exists.")

    user = User(
        email=normalized_email,
        password_hash=password_hash,
        is_platform_admin=is_platform_admin,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("A user with that email already exists.") from exc
    session.refresh(user)
    return user


def bootstrap_admin(email: str) -> None:
    upgrade_database()
    with SessionLocal() as session:
        if session.scalar(select(User.id).limit(1)) is not None:
            raise ValueError("Bootstrap is only available before the first account is created.")
        password_hash = prompt_for_password()
        session.add(BootstrapClaim(name="initial_admin"))
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError("Bootstrap is only available before the first account is created.") from exc
        if session.scalar(select(User.id).limit(1)) is not None:
            session.rollback()
            raise ValueError("Bootstrap is only available before the first account is created.")
        user = create_user(session, email, password_hash, is_platform_admin=True)
        print(f"Created initial platform administrator {user.email} ({user.id}).")


def add_user(email: str) -> None:
    upgrade_database()
    with SessionLocal() as session:
        has_platform_admin = session.scalar(
            select(User.id).where(User.is_platform_admin.is_(True)).limit(1)
        )
        if has_platform_admin is None:
            raise ValueError("Create the initial platform administrator before adding users.")
        user = create_user(session, email, prompt_for_password())
        print(f"Created user {user.email} ({user.id}).")


def create_service_credential(service_id: str, scopes: list[str]) -> None:
    if service_id not in SERVICE_SCOPES:
        raise ValueError("Unknown service identity.")
    requested_scopes = set(scopes)
    if not requested_scopes:
        raise ValueError("At least one service scope is required.")
    if not requested_scopes.issubset(SERVICE_SCOPES[service_id]):
        raise ValueError("One or more scopes are not allowed for this service identity.")

    upgrade_database()
    with SessionLocal() as session:
        has_platform_admin = session.scalar(
            select(User.id).where(User.is_platform_admin.is_(True)).limit(1)
        )
        if has_platform_admin is None:
            raise ValueError("Create the initial platform administrator before adding service credentials.")

        token, credential = make_service_credential(service_id, sorted(requested_scopes))
        session.add(credential)
        session.commit()
        session.refresh(credential)
        print(f"Created service credential {credential.id} for {service_id}.")
        print(f"Bearer token (shown once): {token}")


def revoke_service_credential(credential_id: str) -> None:
    try:
        parsed_id = UUID(credential_id)
    except ValueError as exc:
        raise ValueError("A valid service credential UUID is required.") from exc

    upgrade_database()
    with SessionLocal() as session:
        credential = session.get(ServiceCredential, parsed_id)
        if credential is None:
            raise ValueError("Service credential not found.")
        if credential.revoked_at is None:
            credential.revoked_at = datetime.now(UTC)
            session.commit()
        print(f"Revoked service credential {credential.id}.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="kubo-iam")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("upgrade-db", help="Apply IAM database migrations.")
    bootstrap = commands.add_parser("bootstrap-admin", help="Create the first platform administrator.")
    bootstrap.add_argument("--email", required=True)
    create = commands.add_parser("create-user", help="Create a user account for organization membership.")
    create.add_argument("--email", required=True)
    create_service = commands.add_parser(
        "create-service-credential",
        help="Create a scoped service bearer credential; the token is displayed once.",
    )
    create_service.add_argument("--service-id", required=True, choices=sorted(SERVICE_SCOPES))
    create_service.add_argument("--scope", action="append", required=True)
    revoke_service = commands.add_parser(
        "revoke-service-credential",
        help="Revoke a service credential by its credential UUID.",
    )
    revoke_service.add_argument("--credential-id", required=True)
    args = parser.parse_args()

    try:
        if args.command == "upgrade-db":
            upgrade_database()
            print("IAM database is up to date.")
        elif args.command == "bootstrap-admin":
            bootstrap_admin(args.email)
        elif args.command == "create-service-credential":
            create_service_credential(args.service_id, args.scope)
        elif args.command == "revoke-service-credential":
            revoke_service_credential(args.credential_id)
        else:
            add_user(args.email)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
