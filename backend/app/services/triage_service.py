"""AI triage of a new ticket: ask the classifier, then let PLAIN CODE decide what to do.

"The LLM suggests, the code decides."
- The model only returns a validated answer (category, priority, confidence, reason).
- These rules decide whether to use it, and what to change:

  0. The ticket text tries to instruct the AI -> change nothing (don't trust an answer it may have steered)
  1. A person already started on the ticket  -> change nothing (people win over the AI)
  2. Confidence below the threshold           -> change nothing; a manager sorts it out
  3. Otherwise                                 -> set category + priority, route to the team for that category
  4. ... and if CRITICAL or SECURITY           -> also escalate, so a manager looks at it now

Every call is saved in ai_interactions, including failures, so AI quality can be checked later.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.classifier import PROMPT_VERSION, classify_ticket
from app.ai.errors import AIInvalidOutputError, AIUnavailableError
from app.ai.injection import looks_like_prompt_injection
from app.ai.rag import PROMPT_VERSION as RAG_PROMPT_VERSION
from app.ai.rag import RagResult, answer_question
from app.ai.service import AIService
from app.core.config import get_settings
from app.core.metrics import TRIAGE_DECISIONS
from app.models import (
    AIInteraction,
    AIStatus,
    Team,
    Ticket,
    TicketCategory,
    TicketMessage,
    TicketPriority,
    TicketStatus,
)
from app.services.knowledge_service import search
from app.services.ticket_service import record_escalation

logger = logging.getLogger(__name__)

# Which team handles which category. Create these teams with: python -m app.cli seed-teams
TEAM_FOR_CATEGORY = {
    TicketCategory.BILLING: "Billing Team",
    TicketCategory.PAYMENT: "Billing Team",
    TicketCategory.TECHNICAL: "Technical Support",
    TicketCategory.PRODUCT: "Technical Support",
    TicketCategory.ACCOUNT: "Account Support",
    TicketCategory.LOGIN: "Account Support",
    TicketCategory.SECURITY: "Security Team",
    TicketCategory.OTHER: "General Support",
}


def triage_ticket(db: Session, ai: AIService, ticket_id: uuid.UUID) -> AIInteraction | None:
    """Classify one ticket and act on the answer. Raises AIUnavailableError so the job can retry."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        return None  # deleted before the job ran
    description = (
        db.execute(
            select(TicketMessage.body).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at)
        )
        .scalars()
        .first()
        or ""
    )

    record = AIInteraction(
        ticket_id=ticket.id, kind="classification", model=ai.chat_model, prompt_version=PROMPT_VERSION
    )
    try:
        answer = classify_ticket(ai, subject=ticket.subject, description=description, category_hint=ticket.category)
    except AIUnavailableError as exc:
        _save(db, record, AIStatus.UNAVAILABLE, error=str(exc), decision="AI unavailable; will retry")
        TRIAGE_DECISIONS.labels(outcome="failed").inc()
        raise
    except AIInvalidOutputError as exc:
        _save(db, record, AIStatus.INVALID_OUTPUT, error=str(exc), decision="Answer was invalid; left for a person")
        TRIAGE_DECISIONS.labels(outcome="failed").inc()
        return record

    result = answer.classification
    record.model = answer.model
    record.result = result.model_dump(mode="json")
    record.confidence = result.confidence
    record.latency_ms = answer.latency_ms
    if looks_like_prompt_injection(f"{ticket.subject}\n{description}"):
        record.applied, decision = (
            False,
            "Not applied: the ticket text looks like instructions to the AI; left for a person",
        )
    else:
        record.applied, decision = _decide_and_apply(db, ticket, result.category, result.priority, result.confidence)
    _save(db, record, AIStatus.OK, decision=decision)
    TRIAGE_DECISIONS.labels(outcome="applied" if record.applied else "not_applied").inc()
    logger.info("Ticket %s triaged: %s", ticket.number, decision)
    return record


def _decide_and_apply(
    db: Session, ticket: Ticket, category: TicketCategory, priority: TicketPriority, confidence: float
) -> tuple[bool, str]:
    """The rules from the top of this file. Returns (applied?, what happened in words)."""
    threshold = get_settings().ai_confidence_threshold

    if ticket.status != TicketStatus.OPEN or ticket.team_id is not None:
        return False, "Not applied: a person already started on this ticket"
    if confidence < threshold:
        return False, f"Not applied: confidence {confidence:.2f} is below {threshold:.2f}; left for a manager"

    ticket.category = category
    ticket.priority = priority
    steps = [f"Set {category} / {priority}"]

    team_name = TEAM_FOR_CATEGORY[category]
    team = db.execute(select(Team).where(Team.name == team_name, Team.is_active.is_(True))).scalar_one_or_none()
    if team is not None:
        ticket.team_id = team.id
        steps.append(f"routed to {team_name}")
    else:
        steps.append(f"no active team named '{team_name}', left unrouted")

    if priority == TicketPriority.CRITICAL or category == TicketCategory.SECURITY:
        record_escalation(
            db, ticket, None, f"AI triage: {category} / {priority} needs a manager now", source="ai_triage"
        )
        steps.append("escalated")

    return True, "; ".join(steps)


def _save(db: Session, record: AIInteraction, status: AIStatus, *, decision: str, error: str | None = None) -> None:
    record.status = status
    record.decision = decision
    record.error = error
    db.add(record)
    db.commit()


def ai_history(db: Session, ticket_id: uuid.UUID) -> list[AIInteraction]:
    query = select(AIInteraction).where(AIInteraction.ticket_id == ticket_id).order_by(AIInteraction.created_at)
    return list(db.execute(query).scalars())


def suggest_reply(db: Session, ai: AIService, ticket: Ticket) -> RagResult:
    """Draft an answer to the customer from the knowledge base (RAG), for STAFF to review.

    Never sent automatically: a person reads it, checks the sources, and decides. Saved in
    ai_interactions so we can later measure how often suggestions were useful.
    """
    description = (
        db.execute(
            select(TicketMessage.body).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at)
        )
        .scalars()
        .first()
        or ""
    )
    question = f"{ticket.subject}\n{description}"

    record = AIInteraction(
        ticket_id=ticket.id, kind="reply_suggestion", model=ai.chat_model, prompt_version=RAG_PROMPT_VERSION
    )
    try:
        result = answer_question(ai, question, search(db, ai, question))
    except AIUnavailableError as exc:
        _save(db, record, AIStatus.UNAVAILABLE, error=str(exc), decision="AI unavailable")
        raise
    except AIInvalidOutputError as exc:
        _save(db, record, AIStatus.INVALID_OUTPUT, error=str(exc), decision="Answer was invalid")
        raise

    record.result = {
        "answerable": result.answerable,
        "answer": result.answer,
        "sources": [
            {"title": h.title, "chunk_index": h.chunk_index, "similarity": h.similarity} for h in result.sources
        ],
    }
    record.latency_ms = result.latency_ms
    _save(db, record, AIStatus.OK, decision=f"Suggestion for staff ({result.reason}); not sent to the customer")
    return result
