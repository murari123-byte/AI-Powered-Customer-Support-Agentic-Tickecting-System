"""Putting jobs on the queue from the API.

If Redis is down, the ticket must still be created: AI is a bonus, not a requirement.
So a failed enqueue is logged and ignored, never shown to the customer.
"""

import logging
import uuid

from kombu.exceptions import OperationalError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def enqueue_triage(ticket_id: uuid.UUID) -> bool:
    """Ask a worker to classify this ticket. Returns False if AI triage is off or Redis is down."""
    if not get_settings().ai_triage_enabled:
        return False
    from app.workers.tasks import triage  # imported here so the API starts even without Celery config

    try:
        # retry=False: don't make the customer wait while Celery retries a dead Redis.
        triage.apply_async(args=[str(ticket_id)], retry=False)
    except OperationalError:
        logger.warning("Could not queue AI triage for ticket %s (is Redis running?)", ticket_id)
        return False
    return True


def enqueue_document(document_id: uuid.UUID) -> bool:
    """Ask a worker to chunk and embed an uploaded document. Returns False if Redis is down
    (the document stays PROCESSING; run `python -m app.cli process-documents` later)."""
    from app.workers.tasks import process_document

    try:
        process_document.apply_async(args=[str(document_id)], retry=False)
    except OperationalError:
        logger.warning("Could not queue processing for document %s (is Redis running?)", document_id)
        return False
    return True


def enqueue_agent(ticket_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
    """Ask a worker to run the AI agent on a ticket, acting with this staff member's rights."""
    from app.workers.tasks import run_agent

    try:
        run_agent.apply_async(args=[str(ticket_id), str(actor_id)], retry=False)
    except OperationalError:
        logger.warning("Could not queue the AI agent for ticket %s (is Redis running?)", ticket_id)
        return False
    return True
