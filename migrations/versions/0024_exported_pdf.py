"""exported_pdf: the stored PDF bytes of a Report's last export, keyed by a
fingerprint of the inputs it was rendered from (Story 10.1).

A derived cache: one row per ``report`` (unique index on ``report_id``),
replaced on a fingerprint miss, excluded from backup/restore.

Revision ID: 0024_exported_pdf
Revises: 0023_gate_violation_review
Create Date: 2026-10-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_exported_pdf"
down_revision: str | None = "0023_gate_violation_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exported_pdf",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("report.id"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_exported_pdf_report_id", "exported_pdf", ["report_id"], unique=True)


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
