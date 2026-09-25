"""ai interactions

New table `ai_interactions`: one row per AI call about a ticket (what the model answered,
how confident it was, what our code did with it, how long it took). Used for auditing and
for measuring AI quality. Deleting a ticket deletes its rows (ON DELETE CASCADE).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25 18:23:02.846930

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_interactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum("OK", "INVALID_OUTPUT", "UNAVAILABLE", name="aistatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("applied", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.CheckConstraint("status IN ('OK', 'INVALID_OUTPUT', 'UNAVAILABLE')", name=op.f("ck_ai_interactions_status")),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_ai_interactions_ticket_id_tickets"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_interactions")),
    )
    op.create_index(op.f("ix_ai_interactions_ticket_id"), "ai_interactions", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_interactions_ticket_id"), table_name="ai_interactions")
    op.drop_table("ai_interactions")
