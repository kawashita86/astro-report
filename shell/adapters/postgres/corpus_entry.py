"""``CorpusEntry``: one of Francesco's past hand-written reports, stored as
plain text regardless of where it came from (Story 7.1) -- the raw material
for phase-2 voice conditioning.

Mirrors ``BackupRecord``/``StyleGuide``'s own shape
(``shell/adapters/postgres/backup_record.py``,
``shell/adapters/postgres/style_guide.py``): a uuid7 PK, a ``Text``
``NOT NULL`` ``content`` column, and a ``created_at`` most-recent-first is
all :func:`list_corpus_entries` ever needs.

``client_id`` ships nullable from creation (this story's Design Notes): no
Story 7.1 code path sets it, so every entry added in 7.1 is unpaired
(``client_id IS NULL``). It exists now so ``corpus_entry`` joins the FR-29
Client-deletion cascade (``shell/adapters/postgres/client.py``) and the
durable
``test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant``
invariant exercises it.

Story 7.2 adds ``paired`` (a stored boolean, backfilled ``False`` for every
Story 7.1 row by ``0020_corpus_entry_pairing``) and ``month`` (nullable
``YYYY-MM``), plus the ``/corpus/new`` form fields that set ``paired``,
``client_id`` and ``month`` at record time. Pairing is Francesco's assertion
that he knows the chart; ``client_id``/``month`` are an optional link, so a
paired entry may still have both ``NULL``.

Written by :func:`add_corpus_entry`, called from
``shell/http/routes/corpus.py``'s ``POST /corpus``. That writer only
``add()``s and ``flush()``es, never commits or rolls back -- mirrors
``create_style_guide_version()`` -- so the route owns the transaction
boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Column, Text
from sqlmodel import Field, Session, SQLModel, select
from uuid6 import uuid7

from shell.adapters.postgres.report_run import _UTCDateTime

__all__ = ["CorpusEntry", "add_corpus_entry", "list_corpus_entries"]


class CorpusEntry(SQLModel, table=True):
    """One past report, stored as plain text, source-agnostic."""

    __tablename__ = "corpus_entry"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of column
    # type/`nullable` from the type annotation, so `Text`/`nullable=False`
    # must be given explicitly here -- matching the migration's own `Text`,
    # `NOT NULL` column (a plain `str` field would otherwise default to an
    # unbounded `VARCHAR`, a schema drift from what the migration created).
    content: str = Field(sa_column=Column(Text, nullable=False))
    #: Nullable, indexed foreign key to ``client.id``. No Story 7.1 code path
    #: sets it -- every entry added in 7.1 is unpaired -- but it is present
    #: from creation so this table joins the FR-29 cascade (this module's
    #: docstring). Story 7.2 adds the UI that sets it.
    client_id: UUID | None = Field(default=None, foreign_key="client.id", index=True)
    #: Francesco's assertion that he knows the chart behind this entry (Story
    #: 7.2), stored, not derived from ``client_id``/``month``: a paired entry
    #: may have both link fields ``NULL`` when the application does not hold
    #: the Client. ``0020_corpus_entry_pairing`` carries the ``server_default``
    #: that backfills every Story 7.1 row to ``False``; the model declares
    #: only ``default`` -- matching ``ReportRun.stage_failure_count``.
    paired: bool = Field(default=False)
    #: Optional ``YYYY-MM`` the entry belongs to (Story 7.2). Only ever set
    #: for a paired entry; validated at the HTTP boundary
    #: (``shell/http/routes/corpus.py``'s ``_MONTH_PATTERN``).
    month: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


def add_corpus_entry(
    session: Session,
    *,
    content: str,
    paired: bool = False,
    client_id: UUID | None = None,
    month: str | None = None,
) -> CorpusEntry:
    """Store one past report, in one flush.

    Only ``add()``s and ``flush()``es, never commits or rolls back --
    mirrors ``create_style_guide_version()``
    (``shell/adapters/postgres/style_guide.py``), so it never decides the
    caller's transaction boundary. ``POST /corpus`` commits immediately
    after calling this.

    ``paired`` records Francesco's knowledge of the chart (Story 7.2);
    ``client_id`` and ``month`` are the optional link, either or both of
    which may stay ``NULL`` even for a paired entry when the application
    does not hold the Client. All three are passed straight to the
    ``CorpusEntry`` constructor -- the route
    (``shell/http/routes/corpus.py``) owns their validation. Defaults
    reproduce Story 7.1's behaviour: an unpaired entry with no link.
    """
    entry = CorpusEntry(
        content=content, paired=paired, client_id=client_id, month=month
    )
    session.add(entry)
    session.flush()
    return entry


def list_corpus_entries(session: Session) -> list[CorpusEntry]:
    """Every stored entry, most-recent-first by ``created_at`` -- what
    ``GET /corpus`` renders.

    ``id`` descending is the tie-breaker: a bulk paste (or a fixed-timestamp
    test) can write several rows sharing one ``created_at``, and ``id`` is a
    uuid7, itself time-ordered, so it keeps the order deterministic and still
    newest-first within a tie.
    """
    return list(
        session.exec(
            select(CorpusEntry).order_by(
                CorpusEntry.created_at.desc(), CorpusEntry.id.desc()
            )
        )
    )
