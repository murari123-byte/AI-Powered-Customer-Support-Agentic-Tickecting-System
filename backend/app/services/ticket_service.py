"""Tickets: create, list, view, edit, change status, messages, assign, escalate.

Who can see a ticket:
- CUSTOMER: tickets they raised
- SUPPORT_AGENT: tickets in their teams, or assigned to them
- SUPPORT_MANAGER / ADMIN: every ticket

Every action first loads the ticket with get_ticket(), which applies those rules. A ticket you
can't see is "not found" (404), so nobody can even learn that it exists.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.metrics import ESCALATIONS, TICKETS_CREATED
from app.core.roles import MANAGERS, STAFF, Role
from app.models import (
    Team,
    TeamMember,
    Ticket,
    TicketCategory,
    TicketEscalation,
    TicketMessage,
    TicketPriority,
    TicketStatus,
    TicketStatusHistory,
    User,
)
from app.services.ticket_workflow import CAN_ESCALATE_FROM, check_move
from app.services.user_service import escape_like


class TicketNotFoundError(Exception):
    pass


class NotAllowedError(Exception):
    """User can see the ticket but may not do this (HTTP 403)."""


class ConflictError(Exception):
    """Not possible in the ticket's current state (HTTP 409)."""


class InvalidAssignmentError(Exception):
    """Team/assignee combination is wrong (HTTP 400)."""


# ---------- Who can see what ----------


def _visible_to(user: User):
    """SQL condition for the tickets this user may see (None = all tickets)."""
    if user.role in MANAGERS:
        return None
    if user.role == Role.SUPPORT_AGENT:
        my_teams = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
        return or_(Ticket.team_id.in_(my_teams), Ticket.assignee_id == user.id)
    return Ticket.customer_id == user.id


def get_ticket(db: Session, user: User, ticket_id: uuid.UUID) -> Ticket:
    query = select(Ticket).where(Ticket.id == ticket_id)
    condition = _visible_to(user)
    if condition is not None:
        query = query.where(condition)
    ticket = db.execute(query).scalar_one_or_none()
    if ticket is None:
        raise TicketNotFoundError()
    return ticket


def list_tickets(
    db: Session,
    user: User,
    *,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    team_id: uuid.UUID | None = None,
    assigned_to_me: bool = False,
    search: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[Ticket], int]:
    query = select(Ticket)
    condition = _visible_to(user)
    if condition is not None:
        query = query.where(condition)
    if status:
        query = query.where(Ticket.status == status)
    if priority:
        query = query.where(Ticket.priority == priority)
    if team_id:
        query = query.where(Ticket.team_id == team_id)
    if assigned_to_me:
        query = query.where(Ticket.assignee_id == user.id)
    if search:
        query = query.where(Ticket.subject.ilike(f"%{escape_like(search)}%", escape="\\"))

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    newest_first = query.order_by(Ticket.number.desc()).limit(limit).offset(offset)
    return list(db.execute(newest_first).scalars()), total


# ---------- Create and edit ----------


def create_ticket(
    db: Session, customer: User, *, subject: str, description: str, category: TicketCategory | None
) -> Ticket:
    """Save the ticket, its first message (the description) and the first history row."""
    ticket = Ticket(customer_id=customer.id, subject=subject, category=category)
    db.add(ticket)
    db.flush()  # gives the ticket its id so the other rows can point at it
    db.add(TicketMessage(ticket_id=ticket.id, author_id=customer.id, body=description))
    db.add(TicketStatusHistory(ticket_id=ticket.id, to_status=TicketStatus.OPEN, changed_by_id=customer.id))
    db.commit()
    db.refresh(ticket)
    TICKETS_CREATED.inc()
    return ticket


def update_ticket(db: Session, user: User, ticket_id: uuid.UUID, changes: dict) -> Ticket:
    """Staff can change subject, priority and category."""
    ticket = get_ticket(db, user, ticket_id)
    if user.role not in STAFF:
        raise NotAllowedError("Only support staff can edit tickets")
    for field, value in changes.items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)
    return ticket


# ---------- Status ----------


def _set_status(db: Session, ticket: Ticket, new: TicketStatus, by: User | None, reason: str | None = None) -> None:
    """Change the status and write a history row. `by=None` means the system did it.

    The caller has already checked the rules."""
    if ticket.status == TicketStatus.ESCALATED:
        # Leaving ESCALATED = the manager has dealt with the escalation.
        open_escalation = db.execute(
            select(TicketEscalation).where(
                TicketEscalation.ticket_id == ticket.id, TicketEscalation.resolved_at.is_(None)
            )
        ).scalar_one_or_none()
        if open_escalation:
            open_escalation.resolved_at = datetime.now(UTC)
            open_escalation.resolved_by_id = by.id if by else None

    if new == TicketStatus.RESOLVED:
        ticket.resolved_at = datetime.now(UTC)
    elif new == TicketStatus.OPEN:
        ticket.resolved_at = None  # reopened

    db.add(
        TicketStatusHistory(
            ticket_id=ticket.id,
            from_status=ticket.status,
            to_status=new,
            changed_by_id=by.id if by else None,
            reason=reason,
        )
    )
    ticket.status = new


def _check(ticket: Ticket, user: User, new: TicketStatus) -> None:
    check_move(
        ticket.status,
        new,
        is_owner=ticket.customer_id == user.id,
        is_staff=user.role in STAFF,
        is_manager=user.role in MANAGERS,
        resolved_at=ticket.resolved_at,
        now=datetime.now(UTC),
        reopen_window=timedelta(days=get_settings().ticket_reopen_window_days),
    )


def change_status(db: Session, user: User, ticket_id: uuid.UUID, new: TicketStatus, reason: str | None) -> Ticket:
    ticket = get_ticket(db, user, ticket_id)
    _check(ticket, user, new)
    _set_status(db, ticket, new, user, reason)
    db.commit()
    db.refresh(ticket)
    return ticket


# ---------- Messages ----------


def list_messages(db: Session, user: User, ticket_id: uuid.UUID) -> list[TicketMessage]:
    ticket = get_ticket(db, user, ticket_id)
    query = select(TicketMessage).where(TicketMessage.ticket_id == ticket.id)
    if user.role not in STAFF:
        query = query.where(TicketMessage.is_internal.is_(False))  # customers never see notes
    return list(db.execute(query.order_by(TicketMessage.created_at)).scalars())


def add_message(db: Session, user: User, ticket_id: uuid.UUID, body: str, is_internal: bool) -> TicketMessage:
    ticket = get_ticket(db, user, ticket_id)
    is_staff = user.role in STAFF

    if ticket.status == TicketStatus.CLOSED:
        raise ConflictError("This ticket is closed. Please open a new ticket.")
    if is_internal and not is_staff:
        raise NotAllowedError("Only support staff can add internal notes")

    # When the customer replies, the ticket moves on by itself.
    if not is_staff:
        if ticket.status == TicketStatus.WAITING_FOR_CUSTOMER:
            _set_status(db, ticket, TicketStatus.IN_PROGRESS, user, "Customer replied")
        elif ticket.status == TicketStatus.RESOLVED:
            _check(ticket, user, TicketStatus.OPEN)  # only within the reopen window
            _set_status(db, ticket, TicketStatus.OPEN, user, "Customer replied")

    message = TicketMessage(ticket_id=ticket.id, author_id=user.id, body=body, is_internal=is_internal)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


# ---------- Assignment ----------


def assign(
    db: Session, user: User, ticket_id: uuid.UUID, *, team_id: uuid.UUID | None, assignee_id: uuid.UUID | None
) -> Ticket:
    """Put a ticket in a team and (optionally) give it to one person in that team.

    - Managers/admins: any active team, any active staff member of that team.
    - Agents: can only take a ticket from their own team for themselves (assignee_id = their id).
    """
    ticket = get_ticket(db, user, ticket_id)
    if user.role not in STAFF:
        raise NotAllowedError("You cannot assign tickets")
    if ticket.status == TicketStatus.CLOSED:
        raise ConflictError("Closed tickets can't be reassigned")

    team_id = team_id or ticket.team_id
    if user.role == Role.SUPPORT_AGENT and (team_id != ticket.team_id or assignee_id != user.id):
        raise NotAllowedError("Agents can only take tickets from their team for themselves")

    team = db.get(Team, team_id) if team_id else None
    if team is None or not team.is_active:
        raise InvalidAssignmentError("Choose an active team")
    if assignee_id is not None:
        assignee = db.get(User, assignee_id)
        if assignee is None or not assignee.is_active or assignee.role not in STAFF:
            raise InvalidAssignmentError("Assignee must be active support staff")
        if db.get(TeamMember, (team.id, assignee.id)) is None:
            raise InvalidAssignmentError("Assignee is not a member of this team")

    ticket.team_id = team.id
    ticket.assignee_id = assignee_id
    db.commit()
    db.refresh(ticket)
    return ticket


# ---------- Escalation ----------


def escalate(db: Session, user: User, ticket_id: uuid.UUID, reason: str, *, source: str = "person") -> Ticket:
    ticket = get_ticket(db, user, ticket_id)
    if user.role not in STAFF:
        raise NotAllowedError("Only support staff can escalate")
    if ticket.status not in CAN_ESCALATE_FROM:
        raise ConflictError(f"A {ticket.status} ticket can't be escalated")

    record_escalation(db, ticket, user, reason, source=source)
    db.commit()
    db.refresh(ticket)
    return ticket


def record_escalation(db: Session, ticket: Ticket, by: User | None, reason: str, *, source: str = "person") -> None:
    """Record the escalation and move the ticket to ESCALATED. `by=None` = the system. Caller commits."""
    db.add(TicketEscalation(ticket_id=ticket.id, reason=reason, raised_by_id=by.id if by else None))
    _set_status(db, ticket, TicketStatus.ESCALATED, by, reason)
    ESCALATIONS.labels(source=source).inc()  # person / ai_triage / ai_agent / sla


# ---------- History ----------


def get_history(db: Session, user: User, ticket_id: uuid.UUID) -> list[TicketStatusHistory]:
    """Every status change, oldest first. Staff only."""
    ticket = get_ticket(db, user, ticket_id)
    if user.role not in STAFF:
        raise NotAllowedError("Only support staff can see the history")
    query = select(TicketStatusHistory).where(TicketStatusHistory.ticket_id == ticket.id)
    return list(db.execute(query.order_by(TicketStatusHistory.created_at)).scalars())
