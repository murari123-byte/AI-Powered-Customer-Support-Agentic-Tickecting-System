"""Status rules, tested as pure logic (no database)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import TicketStatus as S
from app.services.ticket_workflow import InvalidMoveError, MoveNotAllowedError, check_move

NOW = datetime(2026, 9, 25, tzinfo=UTC)


def move(current: S, target: S, who: str, resolved_days_ago: int = 1) -> None:
    check_move(
        current,
        target,
        is_owner=who == "customer",
        is_staff=who in {"agent", "manager"},
        is_manager=who == "manager",
        resolved_at=NOW - timedelta(days=resolved_days_ago),
        now=NOW,
    )


@pytest.mark.parametrize(
    "current, target",
    [
        (S.OPEN, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.WAITING_FOR_CUSTOMER),
        (S.WAITING_FOR_CUSTOMER, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.RESOLVED),
        (S.RESOLVED, S.CLOSED),
    ],
)
def test_agent_can_work_a_ticket(current: S, target: S) -> None:
    move(current, target, "agent")


def test_customer_can_close_and_reopen() -> None:
    move(S.OPEN, S.CLOSED, "customer")
    move(S.RESOLVED, S.OPEN, "customer")


def test_customer_cannot_resolve() -> None:
    with pytest.raises(MoveNotAllowedError):
        move(S.OPEN, S.RESOLVED, "customer")


def test_only_manager_takes_ticket_out_of_escalated() -> None:
    with pytest.raises(MoveNotAllowedError):
        move(S.ESCALATED, S.IN_PROGRESS, "agent")
    move(S.ESCALATED, S.IN_PROGRESS, "manager")


def test_escalated_is_not_set_by_a_status_change() -> None:
    with pytest.raises(InvalidMoveError):
        move(S.OPEN, S.ESCALATED, "manager")


@pytest.mark.parametrize("target", [S.OPEN, S.IN_PROGRESS, S.RESOLVED])
def test_closed_is_final(target: S) -> None:
    with pytest.raises(InvalidMoveError):
        move(S.CLOSED, target, "manager")


def test_reopen_window() -> None:
    move(S.RESOLVED, S.OPEN, "customer", resolved_days_ago=6)
    with pytest.raises(InvalidMoveError, match="Too late"):
        move(S.RESOLVED, S.OPEN, "customer", resolved_days_ago=8)
    move(S.RESOLVED, S.OPEN, "agent", resolved_days_ago=365)  # staff can reopen any time
