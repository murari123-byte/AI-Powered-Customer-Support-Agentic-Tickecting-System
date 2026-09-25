"""Background tasks. Each one is thin: open a database session, call a service, log the result.

The real logic lives in app/services/, so it can be tested without Celery or Redis.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import OperationalError

from app.ai.dependencies import get_ai_service
from app.ai.errors import AIUnavailableError
from app.db.session import session_factory
from app.models import User
from app.services import agent_service, knowledge_service
from app.services.sla_service import escalate_overdue_tickets
from app.services.triage_service import triage_ticket
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


# If the database is briefly unreachable, try again: after 30 s, then 60 s, then 120 s.
@celery.task(
    name="tickets.check_sla",
    autoretry_for=(OperationalError,),
    retry_backoff=30,
    max_retries=3,
)
def check_sla() -> list[int]:
    with session_factory()() as db:
        escalated = escalate_overdue_tickets(db, now=datetime.now(UTC))
    if escalated:
        logger.warning("SLA breached, escalated tickets: %s", escalated)
    else:
        logger.info("SLA check: no overdue tickets")
    return escalated


@celery.task(
    name="tickets.triage",
    # Ollama down or too slow: try again after 30 s, 60 s, 120 s, then give up (a person handles it).
    autoretry_for=(AIUnavailableError,),
    retry_backoff=30,
    max_retries=3,
)
def triage(ticket_id: str) -> str | None:
    with session_factory()() as db:
        record = triage_ticket(db, get_ai_service(), uuid.UUID(ticket_id))
    return record.decision if record else None


@celery.task(
    name="knowledge.process_document",
    autoretry_for=(AIUnavailableError,),
    retry_backoff=30,
    max_retries=3,
)
def process_document(document_id: str) -> str | None:
    with session_factory()() as db:
        document = knowledge_service.process_document(db, get_ai_service(), uuid.UUID(document_id))
    return f"{document.status}: {document.chunk_count} chunks" if document else None


@celery.task(
    name="agent.run",
    autoretry_for=(AIUnavailableError,),
    retry_backoff=30,
    max_retries=2,
    # An agent run is several model calls; stop it if it takes more than 10 minutes.
    time_limit=600,
)
def run_agent(ticket_id: str, actor_id: str) -> str | None:
    with session_factory()() as db:
        actor = db.get(User, uuid.UUID(actor_id))
        if actor is None or not actor.is_active:
            return "skipped: the staff member who started the run is no longer active"
        record = agent_service.run_agent(db, get_ai_service(), uuid.UUID(ticket_id), actor)
    return record.decision
