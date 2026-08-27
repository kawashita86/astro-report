"""export_record: an immutable record of one Report export, PDF today,
Markdown a deferred follow-up (Story 6.2).

Written once per export by ``store_export_record()``
(``shell/adapters/postgres/export_record.py``), never updated --
``ExportRecord``'s ``before_update`` listener enforces that at the ORM
layer, not this migration. The index on ``report_id`` is **not** unique,
unlike ``0011_report.py``'s own index on ``report.report_run_id`` -- a
``Report`` may be exported more than once, so many ``export_record`` rows
may point at the same ``report`` row. Joins the FR-29 Client-deletion
cascade (``shell/adapters/postgres/client.py``'s
``_CLIENT_CASCADE_TABLES``).

Revision ID: 0015_export_record
Revises: 0014_bound_string_columns
Create Date: 2026-08-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_export_record"
down_revision: str | None = "0014_bound_string_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client.id"),
            nullable=False,
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("report.id"),
            nullable=False,
        ),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_export_record_client_id", "export_record", ["client_id"])
    # Not unique: many export_record rows may share one report_id (this
    # migration's own docstring) -- unlike 0011_report.py's unique index on
    # report.report_run_id.
    op.create_index(
        "ix_export_record_report_id",
        "export_record",
        ["report_id"],
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
