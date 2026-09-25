"""SLA check: escalate tickets that have waited too long for someone to start on them.

SLA = "service level agreement": a promise about how fast support responds. Here the rule is:
a ticket must not stay OPEN (nobody working on it) longer than its priority allows.
If it does, the system escalates it so a manager notices.

Runs every few minutes as a Celery beat job (app/workers/tasks.py). Safe to run again and
again: an escalated ticket is no longer OPEN, so it's never escalated twice.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ticket, TicketPriority, TicketStatus, TicketStatusHistory
from app.services.ticket_service import record_escalation

# How long a ticket may wait in OPEN, by priority.
MAX_WAIT = {
    TicketPriority.CRITICAL: timedelta(hours=1),
    TicketPriority.HIGH: timedelta(hours=4),
    TicketPriority.MEDIUM: timedelta(hours=24),
    TicketPriority.LOW: timedelta(hours=72),
}


def escalate_overdue_tickets(db: Session, *, now: datetime) -> list[int]:
    """Escalate every OPEN ticket that has waited longer than its limit. Returns their numbers."""
    # When did each ticket (last) become OPEN? A reopened ticket starts its clock again.
    became_open = (
        select(TicketStatusHistory.ticket_id, func.max(TicketStatusHistory.created_at).label("since"))
        .where(TicketStatusHistory.to_status == TicketStatus.OPEN)
        .group_by(TicketStatusHistory.ticket_id)
        .subquery()
    )
    rows = db.execute(
        select(Ticket, became_open.c.since)
        .join(became_open, Ticket.id == became_open.c.ticket_id)
        .where(Ticket.status == TicketStatus.OPEN)
    ).all()

    escalated = []
    for ticket, since in rows:
        limit = MAX_WAIT[ticket.priority]
        if now - since > limit:
            hours = int(limit.total_seconds() // 3600)
            record_escalation(
                db,
                ticket,
                None,
                f"SLA breached: {ticket.priority} ticket waited more than {hours}h in OPEN",
                source="sla",
            )
            escalated.append(ticket.number)
    db.commit()
    return escalated
