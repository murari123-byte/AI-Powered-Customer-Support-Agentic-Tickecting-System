"""Admin operations on users."""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models import User
from app.services.auth_service import logout_everywhere


class UserNotFoundError(Exception):
    pass


class SelfLockoutError(Exception):
    """An admin tried to demote or deactivate themselves."""


def escape_like(text: str) -> str:
    """Make % and _ typed by a user match literally in a LIKE search."""
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def list_users(db: Session, *, limit: int, offset: int, search: str | None = None) -> tuple[list[User], int]:
    query = select(User)
    if search:
        pattern = f"%{escape_like(search.lower())}%"
        query = query.where(
            or_(User.email.like(pattern, escape="\\"), func.lower(User.full_name).like(pattern, escape="\\"))
        )
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    users = db.execute(query.order_by(User.created_at, User.email).limit(limit).offset(offset)).scalars().all()
    return list(users), total


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    return user


def update_user(db: Session, *, actor: User, user_id: uuid.UUID, role: Role | None, is_active: bool | None) -> User:
    user = get_user(db, user_id)

    # Stops the last admin from locking everyone out by accident.
    if user.id == actor.id and ((role is not None and role != Role.ADMIN) or is_active is False):
        raise SelfLockoutError("You cannot remove your own admin access")

    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            logout_everywhere(db, user.id)
    db.commit()
    db.refresh(user)
    return user
