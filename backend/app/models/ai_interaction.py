import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_column, one_of


class AIStatus(StrEnum):
    OK = "OK"  # the model answered with valid JSON
    INVALID_OUTPUT = "INVALID_OUTPUT"  # the model answered, but the answer failed validation
    UNAVAILABLE = "UNAVAILABLE"  # the model could not be reached


class AIInteraction(Base):
    """One call to the AI about a ticket, kept for auditing and for measuring AI quality.

    Stores what the AI said and what our code did with it. It does NOT store the prompt:
    the ticket text is already in the tickets table, and duplicating customer data isn't needed.
    """

    __tablename__ = "ai_interactions"
    __table_args__ = (one_of("status", AIStatus),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # "classification" for now
    status: Mapped[AIStatus] = mapped_column(enum_column(AIStatus))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))  # which prompt produced this answer
    result: Mapped[dict | None] = mapped_column(JSONB)  # the validated answer
    confidence: Mapped[float | None] = mapped_column(Float)
    # Did our code act on the answer (set category/priority, route, escalate)?
    applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    decision: Mapped[str | None] = mapped_column(Text)  # what the code did, in words
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
