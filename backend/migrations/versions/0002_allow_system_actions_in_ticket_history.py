"""allow system actions in ticket history

Lets the system (background jobs such as the SLA check) escalate tickets and change status
without a person behind it: `ticket_escalations.raised_by_id` and
`ticket_status_history.changed_by_id` may now be NULL, meaning "done automatically".

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("ticket_escalations", "raised_by_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column("ticket_status_history", "changed_by_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    # Rows written by the system have no person to put back, so going back would fail with a
    # confusing database error. Stop early with a clear message instead.
    connection = op.get_bind()
    system_rows = connection.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM ticket_escalations WHERE raised_by_id IS NULL)"
            " + (SELECT count(*) FROM ticket_status_history WHERE changed_by_id IS NULL)"
        )
    ).scalar()
    if system_rows:
        raise RuntimeError(
            f"{system_rows} history rows were made by the system (no user). "
            "Delete or re-assign them before downgrading below 0002."
        )
    op.alter_column("ticket_status_history", "changed_by_id", existing_type=sa.UUID(), nullable=False)
    op.alter_column("ticket_escalations", "raised_by_id", existing_type=sa.UUID(), nullable=False)
