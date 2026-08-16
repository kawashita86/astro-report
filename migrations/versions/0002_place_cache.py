"""place_cache: a lookup accelerator for birthplace resolution (FR-2)

Never a source of truth once a Client has persisted its own immutable
lat/lon/zone snapshot (AD-16) -- consulted before geocoding and written
through after a fresh unambiguous resolution only.

Revision ID: 0002_place_cache
Revises: 0001_baseline
Create Date: 2026-08-16

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_place_cache"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "place_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("normalized_query", sa.String(), nullable=False),
        sa.Column("latitude", sa.Numeric(), nullable=False),
        sa.Column("longitude", sa.Numeric(), nullable=False),
        sa.Column("iana_zone", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_place_cache_normalized_query",
        "place_cache",
        ["normalized_query"],
        unique=True,
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
