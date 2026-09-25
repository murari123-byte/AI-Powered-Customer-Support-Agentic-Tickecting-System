"""The SLA check (service) and its Celery task."""

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import TicketEscalation, TicketPriority, TicketStatus, TicketStatusHistory
from app.services.sla_service import escalate_overdue_tickets
from app.workers import tasks
from app.workers.celery_app import celery
from tests.helpers import World, auth

pytestmark = pytest.mark.db

NOW = datetime.now(UTC)


def opened_ago(db: Session, ticket, hours: float) -> None:
    """Pretend the ticket became OPEN `hours` ago."""
    db.execute(
        update(TicketStatusHistory)
        .where(TicketStatusHistory.ticket_id == ticket.id, TicketStatusHistory.to_status == TicketStatus.OPEN)
        .values(created_at=NOW - timedelta(hours=hours))
    )
    db.commit()


def test_overdue_open_ticket_is_escalated_by_the_system(db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)  # MEDIUM priority: 24h limit
    opened_ago(db_session, ticket, 25)

    escalated = escalate_overdue_tickets(db_session, now=NOW)

    assert escalated == [ticket.number]
    db_session.refresh(ticket)
    assert ticket.status == TicketStatus.ESCALATED
    escalation = db_session.execute(select(TicketEscalation)).scalar_one()
    assert escalation.raised_by_id is None  # the system, not a person
    assert "SLA breached" in escalation.reason


def test_ticket_within_its_limit_is_left_alone(db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)
    opened_ago(db_session, ticket, 23)

    assert escalate_overdue_tickets(db_session, now=NOW) == []


@pytest.mark.parametrize(
    "priority, hours, overdue",
    [
        (TicketPriority.CRITICAL, 1.5, True),
        (TicketPriority.CRITICAL, 0.5, False),
        (TicketPriority.HIGH, 5, True),
        (TicketPriority.LOW, 48, False),
    ],
)
def test_limit_depends_on_priority(db_session: Session, world: World, priority, hours, overdue) -> None:
    ticket = world.new_ticket(db_session)
    ticket.priority = priority
    db_session.commit()
    opened_ago(db_session, ticket, hours)

    assert (escalate_overdue_tickets(db_session, now=NOW) == [ticket.number]) is overdue


def test_only_open_tickets_count(db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)
    ticket.status = TicketStatus.IN_PROGRESS  # someone is working on it
    db_session.commit()
    opened_ago(db_session, ticket, 100)

    assert escalate_overdue_tickets(db_session, now=NOW) == []


def test_running_twice_escalates_once(db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)
    opened_ago(db_session, ticket, 25)

    assert escalate_overdue_tickets(db_session, now=NOW) == [ticket.number]
    assert escalate_overdue_tickets(db_session, now=NOW) == []


def test_system_escalation_shows_in_history(api: TestClient, db_session: Session, world: World) -> None:
    ticket = world.new_ticket(db_session)
    opened_ago(db_session, ticket, 25)
    escalate_overdue_tickets(db_session, now=NOW)

    history = api.get(f"/api/v1/tickets/{ticket.id}/history", headers=auth(world.manager)).json()

    assert history[-1]["to_status"] == "ESCALATED"
    assert history[-1]["changed_by"] is None


# ---------- The Celery side ----------


def test_task_is_registered_and_scheduled() -> None:
    assert "tickets.check_sla" in celery.tasks
    assert celery.conf.beat_schedule["sla-check"]["task"] == "tickets.check_sla"


def test_task_runs_the_sla_check(db_session: Session, world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """Call the task function directly (no worker needed), using the test database session."""
    monkeypatch.setattr(tasks, "session_factory", lambda: lambda: nullcontext(db_session))
    ticket = world.new_ticket(db_session)
    opened_ago(db_session, ticket, 25)

    assert tasks.check_sla() == [ticket.number]
