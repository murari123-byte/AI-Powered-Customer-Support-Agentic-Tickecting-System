import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.roles import Role


class UserOut(BaseModel):
    """What the API returns about a user. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)  # can be built straight from a User row

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class UserListOut(BaseModel):
    items: list[UserOut]
    total: int


class UserUpdate(BaseModel):
    """Admin changes. Leave a field out to keep it as it is."""

    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    is_active: bool | None = None
