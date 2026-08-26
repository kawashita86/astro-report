"""report_run_natal_chart: records which ``StoredNatalChart`` a
``ReportRun`` was generated against (Story 6.4).

Adds ``report_run.natal_chart_id``, nullable, set exactly once by
``shell/runner/driver.py::drive()`` the first time ``natal_ready`` succeeds
for a run -- never touched by any later stage or regeneration. This is what
lets ``GET /clients/{client_id}/reports`` (``shell/http/routes/clients.py``)
mark a listed Report as belonging to a chart that has since been superseded
by a correction (Story 2.7).

Add-column only, nullable, no ``server_default``, no backfill -- every
``ReportRun`` row written before this migration simply has
``natal_chart_id = NULL`` and cannot be marked superseded, mirroring
``0012_bounded_regeneration.py``'s and ``0016_export_record_disposition.py``'s
own add-column shape.

Revision ID: 0017_report_run_natal_chart
Revises: 0016_export_record_disposition
Create Date: 2026-08-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_report_run_natal_chart"
down_revision: str | None = "0016_export_record_disposition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_run",
        sa.Column("natal_chart_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_report_run_natal_chart_id_natal_chart",
        "report_run",
        "natal_chart",
        ["natal_chart_id"],
        ["id"],
    )
    op.create_index("ix_report_run_natal_chart_id", "report_run", ["natal_chart_id"])


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
