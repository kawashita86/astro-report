"""report: the immutable, structural record that one report_run's draft
passed the Groundedness Gate (Story 5.3).

Written exactly once per ``report_run``, by ``store_report()``, only on a
passing ``GateResult`` and never updated --
``shell/adapters/postgres/report.py``'s ``before_update`` listener enforces
that at the ORM layer, not this migration. The unique index on
``report_run_id`` enforces "exactly one Report per ReportRun" at the schema
layer instead. Joins the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``'s ``_CLIENT_CASCADE_TABLES``).

Revision ID: 0011_report
Revises: 0010_report_run_failure
Create Date: 2026-08-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_report"
down_revision: str | None = "0010_report_run_failure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report",
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
        sa.Column("style_guide_version", sa.Integer(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("gate_vocabulary_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_client_id", "report", ["client_id"])
    # unique=True: "exactly one Report per ReportRun" (this story's
    # Boundaries) enforced at the schema level, not merely by store_report()
    # only ever being called once per ReportRun.
    op.create_index(
        "ix_report_report_run_id",
        "report",
        ["report_run_id"],
        unique=True,
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
