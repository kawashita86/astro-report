"""gate_violation_review: an immutable, append-only record that Francesco
accepted one Groundedness Gate violation after review, so a Report can
complete despite it (Story 5.7).

Written exactly once per ``(gate_result_id, violation_index)`` pair, by
``store_gate_violation_review()`` (``shell/adapters/postgres/
gate_violation_review.py``), never updated -- ``GateViolationReview``'s
``before_update`` listener enforces that at the ORM layer, not this
migration. Mirrors ``0013_gate_result.py``'s own shape, plus a unique index
on ``(gate_result_id, violation_index)`` (review-loop fix): the accept route
(``shell/http/routes/report_runs.py``) still checks for an existing row
before writing one as its primary idempotency path, but two near-simultaneous
submits of the same violation index could otherwise both pass that check and
each insert a row before either commits -- this constraint is the DB-level
backstop, with the route catching the resulting ``IntegrityError`` and
treating the loser exactly like a double-submit. Joins the FR-29
Client-deletion cascade (``shell/adapters/postgres/client.py``'s
``_CLIENT_CASCADE_TABLES``).

Also adds two nullable ``report`` columns, both add-column only, no backfill:
``accepted_violation_count`` (``Integer``, ``NOT NULL``, ``server_default``
``'0'`` -- every existing clean-pass ``Report`` row honestly accepted zero
violations) and ``closing_gate_result_id`` (nullable FK to ``gate_result.id``,
indexed like every other new FK column here -- ``NULL`` for every existing
row, since none was ever closed via accepted exceptions before this story).

This migration has not been applied to any real database yet (Story 5.7's own
implementation), so the review-loop fixes above are amended in place here
rather than shipped as a separate follow-up migration.

Revision ID: 0023_gate_violation_review
Revises: 0022_birthplace_name
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_gate_violation_review"
down_revision: str | None = "0022_birthplace_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gate_violation_review",
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
        sa.Column(
            "gate_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gate_result.id"),
            nullable=False,
        ),
        sa.Column("violation_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("entry_ids", sa.JSON(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_gate_violation_review_client_id", "gate_violation_review", ["client_id"]
    )
    op.create_index(
        "ix_gate_violation_review_report_run_id", "gate_violation_review", ["report_run_id"]
    )
    # Unique on (gate_result_id, violation_index) -- the DB-level backstop
    # for double-submit idempotency (review-loop fix, this migration's own
    # docstring). Leftmost-column-prefix lookups by gate_result_id alone
    # (e.g. "every reviewed index for this result") are still served by this
    # same index, so no separate gate_result_id-only index is needed.
    op.create_index(
        "ix_gate_violation_review_gate_result_id_violation_index",
        "gate_violation_review",
        ["gate_result_id", "violation_index"],
        unique=True,
    )

    op.add_column(
        "report",
        sa.Column("accepted_violation_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "report",
        sa.Column(
            "closing_gate_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gate_result.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_report_closing_gate_result_id", "report", ["closing_gate_result_id"]
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
