"""supersede_natal_chart: lets a Natal Chart be corrected without destroying
the one work already depended on (Story 2.7).

Adds a nullable ``superseded_at`` to ``natal_chart``: ``NULL`` marks the
current chart for a Client, a timestamp marks one a correction replaced.
Enforced by ``shell/adapters/postgres/client.py``'s ``correct_client_and_chart()``,
not by anything in this migration itself.

Revision ID: 0004_supersede_natal_chart
Revises: 0003_client_and_natal_chart
Create Date: 2026-08-17

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_supersede_natal_chart"
down_revision: str | None = "0003_client_and_natal_chart"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "natal_chart", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
