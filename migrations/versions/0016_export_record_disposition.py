"""export_record_disposition: two new nullable columns on ``export_record``
capturing how a Report actually went out (Story 6.3).

``elapsed_seconds`` (whole seconds, ``ExportRecord.created_at`` minus that
run's ``ReportRun.created_at``) is computed and stored at export time by
``download_report_pdf`` (``shell/http/routes/report_runs.py``).
``disposition`` (``"as_generated"`` or ``"edited"``) starts ``NULL`` and is
set later, at most once, by ``record_send_disposition()``
(``shell/adapters/postgres/export_record.py``) through a Core-level
``UPDATE ... WHERE disposition IS NULL`` -- never through the ORM, which
``ExportRecord``'s ``before_update`` listener still forbids unconditionally.

Both columns are add-column only, nullable, no ``server_default`` -- rows
written before this migration simply have no recorded value for either,
mirroring ``0012_bounded_regeneration.py``'s own add-column shape.

Revision ID: 0016_export_record_disposition
Revises: 0015_export_record
Create Date: 2026-08-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_export_record_disposition"
down_revision: str | None = "0015_export_record"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "export_record",
        sa.Column("elapsed_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "export_record",
        sa.Column("disposition", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
