"""report_payload: the immutable, persisted form of one report_run's frozen
Report Payload (Story 3.8).

Written exactly once per ``report_run``, by ``store_report_payload()``,
never updated -- ``shell/adapters/postgres/report_payload.py``'s
``before_update`` listener enforces that at the ORM layer, not this
migration. The unique index on ``report_run_id`` enforces "exactly once"
(PRD FR-14) at the schema layer instead. Joins the FR-29 Client-deletion
cascade (``shell/adapters/postgres/client.py``'s ``_CLIENT_CASCADE_TABLES``).

Revision ID: 0006_report_payload
Revises: 0005_report_run
Create Date: 2026-08-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_report_payload"
down_revision: str | None = "0005_report_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_payload",
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
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("computation_config_version", sa.Integer(), nullable=False),
        sa.Column("computation_config_content_hash", sa.String(), nullable=False),
        sa.Column("sections_config_version", sa.Integer(), nullable=False),
        sa.Column("sections_config_content_hash", sa.String(), nullable=False),
        sa.Column("ephemeris_files", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_payload_client_id", "report_payload", ["client_id"])
    # unique=True: PRD FR-14's "every stored Report has exactly one stored
    # Report Payload", enforced at the schema level.
    op.create_index(
        "ix_report_payload_report_run_id",
        "report_payload",
        ["report_run_id"],
        unique=True,
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
