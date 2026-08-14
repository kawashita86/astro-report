"""baseline: establish the forward-only migration chain

This revision creates no schema. It exists so that every later migration has a
parent, and so that a fresh database records a revision before the application
is asked to serve. Domain tables arrive with the stories that need them.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-14

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nothing to create: this revision establishes the chain only."""


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
