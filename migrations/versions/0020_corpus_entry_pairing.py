"""corpus_entry_pairing: two new columns on ``corpus_entry`` so an entry can
be marked paired -- Francesco knows the chart behind it -- and optionally
linked to a month (Story 7.2).

``paired`` (``Boolean``, ``NOT NULL``, ``server_default`` false) backfills
every Story 7.1 row to unpaired during the ``ALTER`` -- all of them are
genuinely unpaired, there being no marking UI before this story -- mirroring
``0010_report_run_failure.py``'s own ``server_default`` add-column.
``month`` (``String``, nullable, no ``server_default``) is add-column only:
a row written before this migration simply has no recorded month, mirroring
``0016_export_record_disposition.py``. The existing nullable ``client_id``
column (``0019_corpus_entry.py``) already carries the Client link; this
story only adds the UI that sets it.

Read and validated by ``shell/http/routes/corpus.py``'s ``POST /corpus``,
not by anything in this migration itself.

Revision ID: 0020_corpus_entry_pairing
Revises: 0019_corpus_entry
Create Date: 2026-08-27

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_corpus_entry_pairing"
down_revision: str | None = "0019_corpus_entry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "corpus_entry",
        sa.Column("paired", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "corpus_entry",
        sa.Column("month", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
