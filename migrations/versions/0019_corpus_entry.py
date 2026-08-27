"""corpus_entry: one of Francesco's past hand-written reports, stored as
plain text regardless of where it came from (Story 7.1) -- the raw material
for phase-2 voice conditioning.

Carries a nullable ``client_id`` from creation, with a foreign key to
``client.id`` plus ``ix_corpus_entry_client_id``, so ``corpus_entry`` joins
the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``'s ``_CLIENT_CASCADE_TABLES``) now.
No Story 7.1 code path sets ``client_id`` -- every entry added in 7.1 is
unpaired (``client_id IS NULL``) and is never touched by a Client deletion.
The linking UI and the paired/unpaired marking are Story 7.2.

Written by ``add_corpus_entry()``
(``shell/adapters/postgres/corpus_entry.py``), called from
``shell/http/routes/corpus.py``'s ``POST /corpus``.

Revision ID: 0019_corpus_entry
Revises: 0018_backup_record
Create Date: 2026-08-27

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_corpus_entry"
down_revision: str | None = "0018_backup_record"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corpus_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_corpus_entry_client_id", "corpus_entry", ["client_id"])


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
