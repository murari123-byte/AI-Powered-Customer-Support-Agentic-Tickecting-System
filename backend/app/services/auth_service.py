"""Registration, login, token refresh and logout. No HTTP here: routes translate the errors."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import Role
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Wrong email, wrong password, or disabled account: one error for all three on purpose."""


class InvalidRefreshTokenError(Exception):
    pass


@dataclass(frozen=True)
class IssuedTokens:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str  # plain value: goes into the cookie, only its hash goes into the database


def create_user(db: Session, *, email: str, password: str, full_name: str, role: Role = Role.CUSTOMER) -> User:
    """Create and save a user. The email must already be lowercase."""
    user = User(email=email, password_hash=hash_password(password), full_name=full_name, role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # the unique email index is the real guard, even for races
        db.rollback()
        raise EmailAlreadyRegisteredError(email) from exc
    db.refresh(user)
    return user


def register(db: Session, *, email: str, password: str, full_name: str) -> User:
    """Public sign-up always creates a CUSTOMER. Only an admin can give a staff role."""
    return create_user(db, email=email, password=password, full_name=full_name, role=Role.CUSTOMER)


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    return user


def issue_tokens(db: Session, user: User) -> IssuedTokens:
    """New access token + new refresh token (saved as a hash)."""
    access_token, expires_in = create_access_token(user.id)
    refresh_token = new_refresh_token()
    days = get_settings().refresh_token_expire_days
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=days),
        )
    )
    db.commit()
    return IssuedTokens(user=user, access_token=access_token, expires_in=expires_in, refresh_token=refresh_token)


def refresh(db: Session, refresh_token: str) -> IssuedTokens:
    """Swap a refresh token for a new pair. Each refresh token works only ONCE.

    One DELETE ... RETURNING both finds and removes the token. If two requests send the same
    token at the same moment, only one of them can delete the row, so only one succeeds.
    """
    row = db.execute(
        delete(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
        .returning(RefreshToken.user_id, RefreshToken.expires_at)
    ).first()
    if row is None or row.expires_at <= datetime.now(UTC):
        db.commit()  # keep the delete of an expired token
        raise InvalidRefreshTokenError()

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        db.commit()
        raise InvalidRefreshTokenError()
    return issue_tokens(db, user)  # commits the delete and the new token together


def logout(db: Session, refresh_token: str | None) -> None:
    """Delete this session's refresh token. Safe to call with a missing or unknown token."""
    if refresh_token:
        db.execute(delete(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token)))
        db.commit()


def logout_everywhere(db: Session, user_id: uuid.UUID) -> None:
    """Delete all of a user's refresh tokens (used when an admin deactivates them). Caller commits."""
    db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
