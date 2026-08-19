"""report_run: the persisted execution frame driving a Client-month's
computation through AD-10's six named stages (Story 3.5).

Written once per Client-month, then advanced forward-only by
``shell/runner/driver.py::drive()`` -- enforced by that function, not by
anything in this migration itself. Joins the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``'s ``_CLIENT_CASCADE_TABLES``).

Revision ID: 0005_report_run
Revises: 0004_supersede_natal_chart
Create Date: 2026-08-19

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_report_run"
down_revision: str | None = "0004_supersede_natal_chart"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client.id"),
            nullable=False,
        ),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=True),
        sa.Column("month_start_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("month_end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transit_events", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_run_client_id", "report_run", ["client_id"])


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
