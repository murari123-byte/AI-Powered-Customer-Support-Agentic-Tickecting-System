"""Turn service errors into HTTP responses, in one place.

Services raise normal Python exceptions and know nothing about HTTP. This table picks the
status code, so every endpoint answers the same way for the same problem.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.ai.errors import AIInvalidOutputError, AIUnavailableError
from app.services.team_service import InvalidMemberError, TeamNameTakenError, TeamNotFoundError
from app.services.ticket_service import ConflictError, InvalidAssignmentError, NotAllowedError, TicketNotFoundError
from app.services.ticket_workflow import InvalidMoveError, MoveNotAllowedError

ERROR_STATUS: dict[type[Exception], int] = {
    TicketNotFoundError: 404,
    TeamNotFoundError: 404,
    NotAllowedError: 403,
    MoveNotAllowedError: 403,
    ConflictError: 409,
    InvalidMoveError: 409,
    TeamNameTakenError: 409,
    InvalidAssignmentError: 400,
    InvalidMemberError: 400,
    AIUnavailableError: 503,
    AIInvalidOutputError: 503,
}

DEFAULT_MESSAGES = {
    TicketNotFoundError: "Ticket not found",
    TeamNotFoundError: "Team not found",
    TeamNameTakenError: "A team with this name already exists",
}

# Never show the raw model/server error to users; it can contain internal details.
FIXED_MESSAGES = {
    AIUnavailableError: "The AI is not available right now. Please try again later.",
    AIInvalidOutputError: "The AI gave an unusable answer. Please try again.",
}


def register_error_handlers(app: FastAPI) -> None:
    async def handle(_: Request, exc: Exception) -> JSONResponse:
        message = FIXED_MESSAGES.get(type(exc)) or str(exc) or DEFAULT_MESSAGES.get(type(exc), "Request failed")
        return JSONResponse({"detail": message}, status_code=ERROR_STATUS[type(exc)])

    for error_class in ERROR_STATUS:
        app.add_exception_handler(error_class, handle)
