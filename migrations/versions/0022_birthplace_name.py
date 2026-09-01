"""birthplace_name: one nullable ``String(500)`` column on each of ``client``
and ``place_cache`` so the geocoder's own name for a resolved place is
persisted alongside its coordinates (AD-16, amended 2026-09-01; correct-course
proposal `sprint-change-proposal-2026-09-01.md`).

Both columns are add-column only, no ``server_default``: a ``client`` row
written before this migration was resolved without ever capturing a place
name, and a ``place_cache`` row likewise -- ``NULL`` is the honest "not
recorded" value, not a fabricated backfill, mirroring
``0016_export_record_disposition.py`` / ``0020_corpus_entry_pairing.py``'s own
nullable add-columns. Every Client created or corrected after this migration
(`shell/adapters/postgres/client.py`'s `create_client_with_chart()` /
`correct_client_and_chart()`) and every place cached after it
(`shell/adapters/postgres/place_cache.py`'s `store_resolved_place()`)
populates its column unconditionally.

Revision ID: 0022_birthplace_name
Revises: 0021_gate_vocabulary_hash
Create Date: 2026-09-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_birthplace_name"
down_revision: str | None = "0021_gate_vocabulary_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "client",
        sa.Column("birthplace_name", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "place_cache",
        sa.Column("display_name", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
