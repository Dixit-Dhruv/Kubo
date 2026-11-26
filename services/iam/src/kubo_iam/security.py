from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from uuid import UUID

from pwdlib import PasswordHash

from kubo_iam.models import ApiToken, ServiceCredential

TOKEN_LIFETIME = timedelta(hours=1)
MINIMUM_PASSWORD_LENGTH = 12
_password_hash = PasswordHash.recommended()
_dummy_password_hash = _password_hash.hash(secrets.token_urlsafe(32))


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MINIMUM_PASSWORD_LENGTH} characters.")
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate_hash = password_hash or _dummy_password_hash
    is_valid = _password_hash.verify(password, candidate_hash)
    return bool(password_hash and is_valid)


def create_api_token(user_id: UUID) -> tuple[str, ApiToken]:
    token = secrets.token_urlsafe(32)
    token_hash = hash_api_token(token)
    now = datetime.now(UTC)
    record = ApiToken(user_id=user_id, token_hash=token_hash, created_at=now, expires_at=now + TOKEN_LIFETIME)
    return token, record


def create_service_credential(
    service_id: str,
    scopes: list[str],
) -> tuple[str, ServiceCredential]:
    token = secrets.token_urlsafe(32)
    record = ServiceCredential(
        service_id=service_id,
        token_hash=hash_service_token(token),
        scopes=sorted(set(scopes)),
    )
    return token, record


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def hash_service_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
