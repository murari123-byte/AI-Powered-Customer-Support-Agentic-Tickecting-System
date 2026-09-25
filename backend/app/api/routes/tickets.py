"""Ticket endpoints. Each one just reads the input, calls ticket_service, and returns the result.

The rules (who can see and do what) live in app/services/ticket_service.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_service
from app.ai.service import AIService
from app.api.deps import get_current_user, require_roles
from app.api.routes.knowledge import answer_out
from app.core.roles import STAFF, Role
from app.db.session import get_db
from app.models import AIInteraction, Ticket, TicketMessage, TicketPriority, TicketStatus, TicketStatusHistory, User
from app.schemas.knowledge import AnswerOut
from app.schemas.ticket import (
    AIInteractionOut,
    AssignRequest,
    EscalateRequest,
    HistoryOut,
    MessageCreate,
    MessageOut,
    StatusChange,
    TicketCreate,
    TicketListOut,
    TicketOut,
    TicketUpdate,
)
from app.services import ticket_service, triage_service
from app.workers.queue import enqueue_agent, enqueue_triage

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    body: TicketCreate, user: User = Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)
) -> Ticket:
    """Save the ticket and answer at once. AI classification then runs in the background."""
    ticket = ticket_service.create_ticket(
        db, user, subject=body.subject, description=body.description, category=body.category
    )
    enqueue_triage(ticket.id)
    return ticket


@router.get("", response_model=TicketListOut)
def list_tickets(
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    priority: TicketPriority | None = None,
    team_id: uuid.UUID | None = None,
    assigned_to_me: bool = False,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketListOut:
    """Tickets this user may see, newest first."""
    tickets, total = ticket_service.list_tickets(
        db,
        user,
        status=status_filter,
        priority=priority,
        team_id=team_id,
        assigned_to_me=assigned_to_me,
        search=search,
        limit=limit,
        offset=offset,
    )
    return TicketListOut(items=[TicketOut.model_validate(t) for t in tickets], total=total)


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Ticket:
    return ticket_service.get_ticket(db, user, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: uuid.UUID, body: TicketUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Ticket:
    return ticket_service.update_ticket(db, user, ticket_id, body.model_dump(exclude_unset=True))


@router.post("/{ticket_id}/status", response_model=TicketOut)
def change_status(
    ticket_id: uuid.UUID, body: StatusChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Ticket:
    return ticket_service.change_status(db, user, ticket_id, body.status, body.reason)


@router.get("/{ticket_id}/messages", response_model=list[MessageOut])
def list_messages(
    ticket_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[TicketMessage]:
    return ticket_service.list_messages(db, user, ticket_id)


@router.post("/{ticket_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def add_message(
    ticket_id: uuid.UUID, body: MessageCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TicketMessage:
    return ticket_service.add_message(db, user, ticket_id, body.body, body.is_internal)


@router.post("/{ticket_id}/assign", response_model=TicketOut)
def assign_ticket(
    ticket_id: uuid.UUID, body: AssignRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Ticket:
    return ticket_service.assign(db, user, ticket_id, team_id=body.team_id, assignee_id=body.assignee_id)


@router.post("/{ticket_id}/escalate", response_model=TicketOut)
def escalate_ticket(
    ticket_id: uuid.UUID, body: EscalateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Ticket:
    return ticket_service.escalate(db, user, ticket_id, body.reason)


@router.get("/{ticket_id}/history", response_model=list[HistoryOut])
def ticket_history(
    ticket_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[TicketStatusHistory]:
    return ticket_service.get_history(db, user, ticket_id)


@router.get("/{ticket_id}/ai", response_model=list[AIInteractionOut])
def ticket_ai_history(
    ticket_id: uuid.UUID, user: User = Depends(require_roles(*STAFF)), db: Session = Depends(get_db)
) -> list[AIInteraction]:
    """Staff: every AI answer for this ticket and what the code did with it, oldest first."""
    ticket = ticket_service.get_ticket(db, user, ticket_id)
    return triage_service.ai_history(db, ticket.id)


@router.post("/{ticket_id}/suggest-reply", response_model=AnswerOut)
def suggest_reply(
    ticket_id: uuid.UUID,
    user: User = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
) -> AnswerOut:
    """Staff: an AI-drafted answer from the knowledge base, with sources. Nothing is sent to the customer."""
    ticket = ticket_service.get_ticket(db, user, ticket_id)
    return answer_out(triage_service.suggest_reply(db, ai, ticket))


@router.post("/{ticket_id}/agent", status_code=status.HTTP_202_ACCEPTED)
def start_agent(
    ticket_id: uuid.UUID, user: User = Depends(require_roles(*STAFF)), db: Session = Depends(get_db)
) -> dict:
    """Staff: let the AI agent work this ticket in the background (it acts with YOUR rights).

    Takes about a minute. The result (tools used, changes made, draft reply) appears in GET /tickets/{id}/ai.
    """
    ticket = ticket_service.get_ticket(db, user, ticket_id)
    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The agent doesn't work {ticket.status} tickets")
    if not enqueue_agent(ticket.id, user.id):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Background jobs are not available right now")
    return {"queued": True, "results": f"/api/v1/tickets/{ticket.id}/ai"}
