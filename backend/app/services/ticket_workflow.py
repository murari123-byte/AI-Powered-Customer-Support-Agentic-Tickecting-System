"""Ticket status rules. Pure logic: no database, no HTTP, so it's easy to test.

The table below lists every allowed move, and who may make it:
- "staff"    agents, managers, admins
- "owner"    the customer who raised the ticket (staff may do it too)
- "manager"  managers and admins only

A move that isn't in the table is not allowed. CLOSED is final. ESCALATED can't be set here:
escalating needs a reason, so it has its own action.
"""

from datetime import datetime, timedelta

from app.models.ticket import TicketStatus as S

ALLOWED_MOVES: dict[S, dict[S, str]] = {
    S.OPEN: {S.IN_PROGRESS: "staff", S.WAITING_FOR_CUSTOMER: "staff", S.RESOLVED: "staff", S.CLOSED: "owner"},
    S.IN_PROGRESS: {S.WAITING_FOR_CUSTOMER: "staff", S.RESOLVED: "staff", S.CLOSED: "owner"},
    S.WAITING_FOR_CUSTOMER: {S.IN_PROGRESS: "staff", S.RESOLVED: "staff", S.CLOSED: "owner"},
    S.ESCALATED: {S.IN_PROGRESS: "manager", S.RESOLVED: "manager"},
    S.RESOLVED: {S.OPEN: "owner", S.CLOSED: "owner"},  # RESOLVED -> OPEN = reopen
    S.CLOSED: {},
}

CAN_ESCALATE_FROM = {S.OPEN, S.IN_PROGRESS, S.WAITING_FOR_CUSTOMER}


class InvalidMoveError(Exception):
    """That move doesn't exist from the current status (HTTP 409)."""


class MoveNotAllowedError(Exception):
    """The move exists, but this user may not make it (HTTP 403)."""


def check_move(
    current: S,
    target: S,
    *,
    is_owner: bool,
    is_staff: bool,
    is_manager: bool,
    resolved_at: datetime | None = None,
    now: datetime | None = None,
    reopen_window: timedelta = timedelta(days=7),
) -> None:
    """Raise if this user may not move the ticket from `current` to `target`."""
    if target == S.ESCALATED:
        raise InvalidMoveError("Use the escalate action to escalate a ticket")

    who = ALLOWED_MOVES[current].get(target)
    if who is None:
        raise InvalidMoveError(f"Cannot move a ticket from {current} to {target}")

    allowed = {"staff": is_staff, "owner": is_owner or is_staff, "manager": is_manager}[who]
    if not allowed:
        raise MoveNotAllowedError(f"You cannot move this ticket to {target}")

    # Customers can only reopen for a limited time after it was resolved.
    if current == S.RESOLVED and target == S.OPEN and not is_staff:
        if resolved_at is None or now is None or now - resolved_at > reopen_window:
            raise InvalidMoveError("Too late to reopen; please open a new ticket")
