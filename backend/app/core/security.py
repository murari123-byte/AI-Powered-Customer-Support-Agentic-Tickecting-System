"""Password hashing and token helpers. No database access here, so it's easy to unit-test."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

# Fixed in code, never taken from the token itself. Letting the token choose its algorithm is
# a classic JWT attack ("alg": "none").
JWT_ALGORITHM = "HS256"

_password_hasher = PasswordHasher()  # Argon2id, library defaults


class InvalidTokenError(Exception):
    """Token missing, malformed, expired, or wrongly signed."""


# ---------- Passwords ----------


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# ---------- Access tokens (JWT) ----------


def create_access_token(user_id: uuid.UUID, *, expires_in: timedelta | None = None) -> tuple[str, int]:
    """Signed JWT holding only the user id. Returns (token, lifetime in seconds).

    The role is NOT in the token: it's read from the database on every request, so a role
    change or deactivation works immediately.
    """
    settings = get_settings()
    lifetime = expires_in or timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": now, "exp": now + lifetime}
    token = jwt.encode(claims, settings.jwt_secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> uuid.UUID:
    """Return the user id inside a valid token, or raise InvalidTokenError."""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc


# ---------- Refresh tokens ----------


def new_refresh_token() -> str:
    """A long random string (not a JWT). It only means something while its row exists."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 is fine here (unlike passwords): the token is random and long, so it can't be guessed."""
    return hashlib.sha256(token.encode()).hexdigest()
