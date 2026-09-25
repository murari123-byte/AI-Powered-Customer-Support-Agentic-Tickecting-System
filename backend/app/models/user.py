import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.roles import Role
from app.db.base import Base, enum_column, one_of


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are stored lowercase, so "Ana@X.com" and "ana@x.com" can't both register.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        one_of("role", Role),
    )

    # Random UUIDs: ids can't be guessed or counted (unlike 1, 2, 3...).
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    # Argon2 hash (includes its own salt). The plain password is never stored.
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(enum_column(Role), default=Role.CUSTOMER, server_default=Role.CUSTOMER.value)
    # Deactivate instead of delete: tickets keep pointing at the user.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
