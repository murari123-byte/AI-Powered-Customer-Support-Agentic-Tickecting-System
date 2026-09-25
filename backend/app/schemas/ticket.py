import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import TicketCategory, TicketPriority, TicketStatus
from app.schemas.team import UserRef

# ---------- Requests ----------


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TicketCreate(_Input):
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)  # becomes the first message
    category: TicketCategory | None = None  # priority is NOT accepted from customers


class TicketUpdate(_Input):
    subject: str | None = Field(default=None, min_length=3, max_length=200)
    priority: TicketPriority | None = None
    category: TicketCategory | None = None


class StatusChange(_Input):
    status: TicketStatus
    reason: str | None = Field(default=None, max_length=1000)


class MessageCreate(_Input):
    body: str = Field(min_length=1, max_length=10_000)
    is_internal: bool = False  # staff-only note


class AssignRequest(_Input):
    team_id: uuid.UUID | None = None  # leave out to keep the current team
    assignee_id: uuid.UUID | None = None  # leave out (or null) = team queue, nobody yet


class EscalateRequest(_Input):
    reason: str = Field(min_length=3, max_length=1000)


# ---------- Responses ----------


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    subject: str
    status: TicketStatus
    priority: TicketPriority
    category: TicketCategory | None
    customer: UserRef
    team: TeamRef | None
    assignee: UserRef | None
    created_at: datetime
    resolved_at: datetime | None


class TicketListOut(BaseModel):
    items: list[TicketOut]
    total: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author: UserRef
    body: str
    is_internal: bool
    created_at: datetime


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: TicketStatus | None
    to_status: TicketStatus
    changed_by: UserRef | None  # null = done automatically by the system
    reason: str | None
    created_at: datetime


class AIInteractionOut(BaseModel):
    """What the AI said about a ticket, and what the code did with it (staff only)."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    status: str
    model: str
    prompt_version: str
    result: dict | None
    confidence: float | None
    applied: bool
    decision: str | None
    latency_ms: int | None
    created_at: datetime
