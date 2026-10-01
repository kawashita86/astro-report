"""gate_result.draft_attempt: which draft attempt a Gate check examined (Story 10.5).

Nullable with no backfill: rows written before this migration have no recorded
attempt, and a regeneration treats such a result as untargetable (a full attempt).
A plain integer, not a foreign key -- it names ``report_draft``'s
``(report_run_id, attempt)`` coordinate.

Revision ID: 0026_gate_result_draft_attempt
Revises: 0025_report_draft_section
Create Date: 2026-10-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_gate_result_draft_attempt"
down_revision: str | None = "0025_report_draft_section"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("gate_result", sa.Column("draft_attempt", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
