"""report_run_failure: lets a persistently rate-limited or failing
``ReportRun`` reach a terminal state instead of being retried forever
(Story 4.8).

Adds three nullable/defaulted columns to ``report_run``:
``stage_failure_count`` (consecutive ``with_backoff`` exhaustions on the
current stage, reset to 0 by a successful stage advance),
``failed_at`` (``NULL`` until the run is marked terminally failed, mirroring
``natal_chart.superseded_at``'s nullable-timestamp pattern) and
``failure_reason`` (the reason shown to Francesco in the poll fragment).
Enforced by ``shell/runner/driver.py::drive()``, not by anything in this
migration itself.

Revision ID: 0010_report_run_failure
Revises: 0009_report_draft
Create Date: 2026-08-22

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_report_run_failure"
down_revision: str | None = "0009_report_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_run",
        sa.Column("stage_failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "report_run", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("report_run", sa.Column("failure_reason", sa.String(), nullable=True))


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
