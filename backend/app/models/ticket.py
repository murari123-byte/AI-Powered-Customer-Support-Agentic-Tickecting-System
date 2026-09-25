import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, enum_column, one_of
from app.models.team import Team
from app.models.user import User


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_CUSTOMER = "WAITING_FOR_CUSTOMER"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TicketPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TicketCategory(StrEnum):
    BILLING = "BILLING"
    PAYMENT = "PAYMENT"
    TECHNICAL = "TECHNICAL"
    ACCOUNT = "ACCOUNT"
    LOGIN = "LOGIN"
    PRODUCT = "PRODUCT"
    SECURITY = "SECURITY"
    OTHER = "OTHER"


def event_time():
    """Real time of each statement. (now() is the transaction START time, so two events saved
    in the same transaction would get the same timestamp and the timeline could mix up.)"""
    return func.clock_timestamp()


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_customer_id", "customer_id"),  # a customer's tickets
        Index("ix_tickets_team_id_status", "team_id", "status"),  # a team's queue
        Index("ix_tickets_assignee_id", "assignee_id"),  # an agent's tickets
        one_of("status", TicketStatus),
        one_of("priority", TicketPriority),
        one_of("category", TicketCategory),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Short number for people ("ticket 1042"). The UUID stays the API id.
    number: Mapped[int] = mapped_column(BigInteger, Identity(start=1001), unique=True)
    subject: Mapped[str] = mapped_column(String(200))
    status: Mapped[TicketStatus] = mapped_column(
        enum_column(TicketStatus), default=TicketStatus.OPEN, server_default=TicketStatus.OPEN.value
    )
    priority: Mapped[TicketPriority] = mapped_column(
        enum_column(TicketPriority), default=TicketPriority.MEDIUM, server_default=TicketPriority.MEDIUM.value
    )
    # Optional hint from the customer; the AI classifier fills it in later.
    category: Mapped[TicketCategory | None] = mapped_column(enum_column(TicketCategory))

    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=event_time())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[User] = relationship(foreign_keys=[customer_id], lazy="selectin")
    team: Mapped[Team | None] = relationship(lazy="selectin")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="selectin")


class TicketMessage(Base):
    """One message in the conversation. Internal notes are visible to staff only."""

    __tablename__ = "ticket_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=event_time())

    author: Mapped[User] = relationship(lazy="selectin")


class TicketStatusHistory(Base):
    """Every status change: who, from what, to what, why. Rows are never changed."""

    __tablename__ = "ticket_status_history"
    __table_args__ = (one_of("from_status", TicketStatus), one_of("to_status", TicketStatus))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[TicketStatus | None] = mapped_column(enum_column(TicketStatus))  # null = created
    to_status: Mapped[TicketStatus] = mapped_column(enum_column(TicketStatus))
    # Null = changed automatically by the system (e.g. the SLA check), not by a person.
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=event_time())

    changed_by: Mapped[User | None] = relationship(lazy="selectin")


class TicketEscalation(Base):
    """An escalation: who raised it and why; filled in when a manager resolves it."""

    __tablename__ = "ticket_escalations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    # Null = raised automatically by the system (e.g. the SLA check), not by a person.
    raised_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=event_time())
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    raised_by: Mapped[User | None] = relationship(foreign_keys=[raised_by_id], lazy="selectin")
    resolved_by: Mapped[User | None] = relationship(foreign_keys=[resolved_by_id], lazy="selectin")
