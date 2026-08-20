"""report_theme: the immutable, persisted form of one report_run's purely
derived ReportTheme (Story 4.3, AD-14).

Written exactly once per ``report_run``, by ``store_report_theme()``, never
updated -- ``shell/adapters/postgres/report_theme.py``'s ``before_update``
listener enforces that at the ORM layer, not this migration. The unique
index on ``report_run_id`` enforces "exactly one StoredReportTheme per
ReportRun" at the schema layer instead. Joins the FR-29 Client-deletion
cascade (``shell/adapters/postgres/client.py``'s ``_CLIENT_CASCADE_TABLES``).

Revision ID: 0008_report_theme
Revises: 0007_style_guide
Create Date: 2026-08-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_report_theme"
down_revision: str | None = "0007_style_guide"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_theme",
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
        sa.Column("theme", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_theme_client_id", "report_theme", ["client_id"])
    # unique=True: "exactly one StoredReportTheme per ReportRun" (this
    # story's Boundaries) enforced at the schema level, not merely by
    # store_report_theme() only ever being called once per ReportRun.
    op.create_index(
        "ix_report_theme_report_run_id",
        "report_theme",
        ["report_run_id"],
        unique=True,
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
