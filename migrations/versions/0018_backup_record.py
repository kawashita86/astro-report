"""backup_record: the timestamp of one completed ``GET /backup`` download
(Story 6.6).

Global/versionless, mirroring ``0007_style_guide.py``'s table shape -- no
``client_id``, so it is correctly excluded from the FR-29 Client-deletion
cascade (``shell/adapters/postgres/client.py``) automatically. Written by
``store_backup_record()`` (``shell/adapters/postgres/backup_record.py``),
called from ``shell/http/routes/backup.py``'s ``download_backup`` right
before the response is returned. Not added to ``download_backup``'s own
``_BACKUP_MODELS`` export set -- a restored database with no ``backup_record``
row simply shows stale until the next backup, the safe default.

Revision ID: 0018_backup_record
Revises: 0017_report_run_natal_chart
Create Date: 2026-08-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_backup_record"
down_revision: str | None = "0017_report_run_natal_chart"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
