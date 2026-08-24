"""bounded_regeneration: schema support for automatic, bounded, whole-Report
regeneration on a Groundedness Gate failure (Story 5.4).

Adds ``report_run.regeneration_count`` (attempts across the current
regeneration cycle, distinct from ``stage_failure_count`` -- see
``shell/runner/driver.py``'s Design Notes for why the two can't share a
counter) and ``report_draft.attempt`` (which regeneration produced this row,
``0`` for the first, never-regenerated draft). ``report_draft`` is no longer
"exactly one row per ``ReportRun``": the old unique index on
``report_run_id`` alone is dropped and replaced with a unique index on
``(report_run_id, attempt)`` -- more than one ``ReportDraft`` row per run is
now expected, one per regeneration attempt, but never two at the same
attempt. Enforced by ``shell/runner/driver.py::drive()`` and
``shell/adapters/postgres/report_draft.py::store_report_draft()``, not by
anything in this migration itself.

Revision ID: 0012_bounded_regeneration
Revises: 0011_report
Create Date: 2026-08-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_bounded_regeneration"
down_revision: str | None = "0011_report"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_run",
        sa.Column("regeneration_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "report_draft",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    # The old "exactly one ReportDraft per ReportRun" constraint (0009's
    # ix_report_draft_report_run_id) no longer holds -- a second draft for
    # the same run is expected once regeneration is real, replaced by
    # "exactly one ReportDraft per (ReportRun, attempt)".
    op.drop_index("ix_report_draft_report_run_id", table_name="report_draft")
    op.create_index(
        "ix_report_draft_report_run_id_attempt",
        "report_draft",
        ["report_run_id", "attempt"],
        unique=True,
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
