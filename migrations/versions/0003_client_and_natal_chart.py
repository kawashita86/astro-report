"""client_and_natal_chart: a Client's identity + immutable birthplace
snapshot, and its Natal Chart (Story 2.3, AD-16)

Written together, always: no Client row without a Natal Chart row, and vice
versa -- enforced by ``shell/adapters/postgres/client.py``'s
``create_client_with_chart()``, not by anything in this migration itself.

Revision ID: 0003_client_and_natal_chart
Revises: 0002_place_cache
Create Date: 2026-08-16

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_client_and_natal_chart"
down_revision: str | None = "0002_place_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("birth_time", sa.Time(), nullable=False),
        sa.Column("latitude", sa.Numeric(), nullable=False),
        sa.Column("longitude", sa.Numeric(), nullable=False),
        sa.Column("iana_zone", sa.String(), nullable=False),
    )
    op.create_table(
        "natal_chart",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client.id"),
            nullable=False,
        ),
        sa.Column("ascendant", sa.Numeric(), nullable=False),
        sa.Column("midheaven", sa.Numeric(), nullable=False),
        sa.Column("planets", sa.JSON(), nullable=False),
        sa.Column("houses", sa.JSON(), nullable=False),
        sa.Column("aspects", sa.JSON(), nullable=False),
        sa.Column("computation_config_version", sa.Integer(), nullable=False),
        sa.Column("computation_config_content_hash", sa.String(), nullable=False),
        sa.Column("ephemeris_files", sa.JSON(), nullable=False),
    )
    op.create_index("ix_natal_chart_client_id", "natal_chart", ["client_id"])


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
