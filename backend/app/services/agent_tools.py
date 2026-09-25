"""The tools the AI agent may ask for. Our code runs them, never the model.

Every tool:
- has a Pydantic model for its arguments: anything that doesn't fit is refused before running;
- works only on THE ticket the agent was started for: there is no ticket_id argument, so the
  model can't reach another ticket or customer;
- runs through the normal services, with the rights of the STAFF MEMBER who started the agent,
  so the usual role rules apply (an agent-started run can't do what that agent couldn't do);
- returns a small JSON-able dict: data for reads, {"ok": ...} / {"error": ...} for writes.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.service import AIService
from app.models import Team, Ticket, TicketMessage, TicketStatus, TicketStatusHistory, User
from app.services import knowledge_service, ticket_service
from app.services.ticket_service import ConflictError, InvalidAssignmentError, NotAllowedError
from app.services.ticket_workflow import InvalidMoveError, MoveNotAllowedError
from app.services.triage_service import TEAM_FOR_CATEGORY

TeamName = Literal[tuple(sorted(set(TEAM_FOR_CATEGORY.values())))]  # the 5 routing teams, nothing else

# Errors from the normal ticket rules. The model is told what went wrong, so it can adjust.
RULE_ERRORS = (NotAllowedError, ConflictError, InvalidAssignmentError, InvalidMoveError, MoveNotAllowedError)


@dataclass
class ToolContext:
    """What a tool may touch. Built by our code for one agent run; the model never sees it."""

    db: Session
    ai: AIService
    ticket: Ticket
    actor: User  # the staff member who started the agent: their rights apply


# ---------- Arguments (checked with Pydantic before a tool runs) ----------


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")  # an unexpected argument (e.g. "ticket_id") is refused


class NoArgs(_Args):
    pass


class SearchArgs(_Args):
    query: str = Field(min_length=3, max_length=300, description="What to look for, in plain words")


class AssignArgs(_Args):
    team: TeamName = Field(description="The team that should handle this ticket")


class StatusArgs(_Args):
    # Only these two. Resolving or closing a ticket is always a human decision.
    status: Literal["IN_PROGRESS", "WAITING_FOR_CUSTOMER"]
    reason: str = Field(min_length=3, max_length=300)


class EscalateArgs(_Args):
    reason: str = Field(min_length=3, max_length=500, description="Why a manager must look at this now")


# ---------- The tools ----------


def search_knowledge_base(ctx: ToolContext, args: SearchArgs) -> dict:
    hits = knowledge_service.search(ctx.db, ctx.ai, args.query, top_k=3)
    if not hits:
        return {"results": [], "note": "Nothing relevant in the knowledge base"}
    return {"results": [{"title": h.title, "similarity": h.similarity, "text": h.content[:700]} for h in hits]}


def get_ticket_history(ctx: ToolContext, args: NoArgs) -> dict:
    messages = (
        ctx.db.execute(
            select(TicketMessage).where(TicketMessage.ticket_id == ctx.ticket.id).order_by(TicketMessage.created_at)
        )
        .scalars()
        .all()
    )
    changes = (
        ctx.db.execute(
            select(TicketStatusHistory)
            .where(TicketStatusHistory.ticket_id == ctx.ticket.id)
            .order_by(TicketStatusHistory.created_at)
        )
        .scalars()
        .all()
    )
    return {
        "messages": [
            {
                "from": "customer" if m.author_id == ctx.ticket.customer_id else "support",
                "internal_note": m.is_internal,
                "text": m.body[:500],
            }
            for m in messages[-10:]
        ],
        "status_changes": [f"{c.from_status or 'new'} -> {c.to_status}" for c in changes],
    }


def get_customer_details(ctx: ToolContext, args: NoArgs) -> dict:
    """Only what helps with support. No email, no password hash, no ids."""
    customer = ctx.ticket.customer
    ticket_count = ctx.db.execute(select(func.count()).where(Ticket.customer_id == customer.id)).scalar_one()
    open_count = ctx.db.execute(
        select(func.count()).where(
            Ticket.customer_id == customer.id, Ticket.status.not_in([TicketStatus.RESOLVED, TicketStatus.CLOSED])
        )
    ).scalar_one()
    return {
        "name": customer.full_name,
        "customer_since": customer.created_at.date().isoformat(),
        "account_active": customer.is_active,
        "tickets_total": ticket_count,
        "tickets_open": open_count,
    }


def assign_ticket(ctx: ToolContext, args: AssignArgs) -> dict:
    team = ctx.db.execute(select(Team).where(Team.name == args.team)).scalar_one_or_none()
    if team is None:
        return {"error": f"There is no team called {args.team}"}
    ticket_service.assign(ctx.db, ctx.actor, ctx.ticket.id, team_id=team.id, assignee_id=None)
    return {"ok": f"Ticket assigned to {args.team}"}


def update_status(ctx: ToolContext, args: StatusArgs) -> dict:
    ticket_service.change_status(
        ctx.db, ctx.actor, ctx.ticket.id, TicketStatus(args.status), f"AI agent: {args.reason}"
    )
    return {"ok": f"Status is now {args.status}"}


def escalate_ticket(ctx: ToolContext, args: EscalateArgs) -> dict:
    ticket_service.escalate(ctx.db, ctx.actor, ctx.ticket.id, f"AI agent: {args.reason}", source="ai_agent")
    return {"ok": "Ticket escalated to a manager"}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str  # the model reads this to decide when to use the tool
    args_model: type[_Args]
    run: Callable[[ToolContext, BaseModel], dict]
    writes: bool = False  # changes data? Write tools are limited and disabled in read-only mode

    def spec(self) -> dict:
        """The definition sent to the model (OpenAI/Ollama function format)."""
        schema = self.args_model.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
            },
        }


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in [
        Tool(
            "search_knowledge_base",
            "Search the help-centre articles. Use it before answering any question about how things work.",
            SearchArgs,
            search_knowledge_base,
        ),
        Tool("get_ticket_history", "Read this ticket's messages and status changes.", NoArgs, get_ticket_history),
        Tool(
            "get_customer_details",
            "Basic facts about this ticket's customer: how long they've been a customer, how many tickets they have.",
            NoArgs,
            get_customer_details,
        ),
        Tool(
            "assign_ticket",
            "Send this ticket to the team that should handle it.",
            AssignArgs,
            assign_ticket,
            writes=True,
        ),
        Tool(
            "update_status",
            "Set the status to IN_PROGRESS, or to WAITING_FOR_CUSTOMER when you need more information from the customer.",
            StatusArgs,
            update_status,
            writes=True,
        ),
        Tool(
            "escalate_ticket",
            "Ask a manager to look at this ticket now. Only for security incidents, outages, or customers threatening to leave.",
            EscalateArgs,
            escalate_ticket,
            writes=True,
        ),
    ]
}


@dataclass
class ToolResult:
    tool: str
    arguments: dict
    ok: bool
    output: dict
    blocked: bool = False  # refused by our checks (invalid, not allowed, read-only, repeated)


@dataclass
class Guard:
    """Limits for one agent run."""

    read_only: bool = False
    used_writes: set[str] = field(default_factory=set)


def run_tool(ctx: ToolContext, guard: Guard, name: str, arguments: dict) -> ToolResult:
    """Check a tool request from the model and, if it passes every check, run it."""
    tool = TOOLS.get(name)
    if tool is None:
        return ToolResult(name, arguments, False, {"error": f"Unknown tool '{name}'"}, blocked=True)
    if tool.writes and guard.read_only:
        return ToolResult(
            name, arguments, False, {"error": "Changes are disabled for this ticket (read-only mode)"}, blocked=True
        )
    if tool.writes and name in guard.used_writes:
        return ToolResult(name, arguments, False, {"error": f"{name} was already used in this run"}, blocked=True)
    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in exc.errors()[:3])
        return ToolResult(name, arguments, False, {"error": f"Invalid arguments: {problems}"}, blocked=True)

    try:
        output = tool.run(ctx, args)
    except RULE_ERRORS as exc:
        ctx.db.rollback()
        return ToolResult(name, arguments, False, {"error": f"Not allowed: {exc}"}, blocked=True)
    if tool.writes:
        guard.used_writes.add(name)
        ctx.db.refresh(ctx.ticket)
    return ToolResult(name, arguments, "error" not in output, output)
