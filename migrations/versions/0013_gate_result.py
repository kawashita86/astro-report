"""gate_result: an immutable record of one Groundedness Gate check, pass or
fail (Story 5.6).

Written exactly once per Gate check by ``store_gate_result()``
(``shell/adapters/postgres/gate_result.py``), never updated --
``StoredGateResult``'s ``before_update`` listener enforces that at the ORM
layer, not this migration. The index on ``report_run_id`` is **not**
unique, unlike ``0011_report.py``'s own index on ``report`` -- a run may
regenerate (Story 5.4), and each attempt's Gate check gets its own row, so
many ``gate_result`` rows may point at the same ``report_run`` row. Joins
the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``'s ``_CLIENT_CASCADE_TABLES``).

Revision ID: 0013_gate_result
Revises: 0012_bounded_regeneration
Create Date: 2026-08-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_gate_result"
down_revision: str | None = "0012_bounded_regeneration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gate_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client.id"),
            nullable=False,
        ),
        sa.Column(
            "report_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("report_run.id"),
            nullable=False,
        ),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("regeneration_count", sa.Integer(), nullable=False),
        sa.Column("vocabulary_version", sa.Integer(), nullable=False),
        sa.Column("violations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_gate_result_client_id", "gate_result", ["client_id"])
    # Not unique: many gate_result rows may share one report_run_id (this
    # migration's own docstring) -- unlike 0011_report.py's unique index on
    # report.report_run_id.
    op.create_index(
        "ix_gate_result_report_run_id",
        "gate_result",
        ["report_run_id"],
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
