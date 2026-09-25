"""Every table model is imported here, so Alembic and SQLAlchemy see all tables."""

from app.models.ai_interaction import AIInteraction, AIStatus
from app.models.knowledge import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from app.models.refresh_token import RefreshToken
from app.models.team import Team, TeamMember
from app.models.ticket import (
    Ticket,
    TicketCategory,
    TicketEscalation,
    TicketMessage,
    TicketPriority,
    TicketStatus,
    TicketStatusHistory,
)
from app.models.user import User

__all__ = [
    "AIInteraction",
    "AIStatus",
    "DocumentStatus",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "RefreshToken",
    "Team",
    "TeamMember",
    "Ticket",
    "TicketCategory",
    "TicketEscalation",
    "TicketMessage",
    "TicketPriority",
    "TicketStatus",
    "TicketStatusHistory",
    "User",
]
