"""gate_vocabulary_hash: one nullable ``String(64)`` column on each of
``report`` and ``gate_result`` so a persisted Gate outcome records the
``GateVocabulary.content_hash`` (a sha256 hex digest) it was checked
against, not only the hand-bumped ``version`` int (epic-5-retro item 45).

``report.gate_vocabulary_content_hash`` and
``gate_result.vocabulary_content_hash`` are both nullable, no
``server_default``: a row written before this migration honestly has no
recorded hash -- NULL is the correct "unknown" value, not a fabricated or
empty digest -- mirroring ``0016_export_record_disposition.py`` /
``0020_corpus_entry_pairing.py``'s ``month`` add-column. Every write after
this migration populates both columns unconditionally
(``shell/runner/driver.py``'s three Gate write-sites).

Read back by nothing in this migration itself: ``store_report()`` /
``store_gate_result()`` (``shell/adapters/postgres/``) write it, and a
direct SQL query can now distinguish two rows with equal
``vocabulary_version`` but different content -- the forgotten-version-bump
failure mode item 45 exists to catch.

Revision ID: 0021_gate_vocabulary_hash
Revises: 0020_corpus_entry_pairing
Create Date: 2026-08-28

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_gate_vocabulary_hash"
down_revision: str | None = "0020_corpus_entry_pairing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report",
        sa.Column("gate_vocabulary_content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "gate_result",
        sa.Column("vocabulary_content_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
