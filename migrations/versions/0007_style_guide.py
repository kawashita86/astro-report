"""style_guide: append-only versioned rows behind the Generator's register
(Story 4.2).

Version 1 is seeded inside this same ``upgrade()``, from
``data/style-guide.seed.md`` via ``shell/style_guide_seed.py::
load_style_guide_seed()``. Alembic's own revision tracking -- this migration
runs exactly once, ever, across any number of deploys -- is what makes that
seed idempotent, matching this story's Design Notes: seeding at
``docker-entrypoint.sh``'s ``alembic upgrade head`` step, not lazily at app
startup. Every row after version 1 is inserted by
``shell/adapters/postgres/style_guide.py::create_style_guide_version()``, via
the ``/style-guide/edit`` route -- never by a later migration.

Revision ID: 0007_style_guide
Revises: 0006_report_payload
Create Date: 2026-08-20

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from uuid6 import uuid7

from shell.style_guide_seed import load_style_guide_seed

revision: str = "0007_style_guide"
down_revision: str | None = "0006_report_payload"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "style_guide",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # unique=True: "version int unique monotonic from 1" (this story's
    # Boundaries) enforced at the schema level, not merely by
    # create_style_guide_version() always inserting max + 1.
    op.create_index("ix_style_guide_version", "style_guide", ["version"], unique=True)

    style_guide_table = sa.table(
        "style_guide",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer()),
        sa.column("content", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        style_guide_table,
        [
            {
                "id": uuid7(),
                "version": 1,
                "content": load_style_guide_seed(),
                "created_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
