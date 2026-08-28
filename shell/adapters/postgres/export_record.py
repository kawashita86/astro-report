"""``ExportRecord``: the immutable, persisted record of one Report export
(Story 6.2) -- PDF today, Markdown a deferred follow-up (``deferred-work.md``).

Written once per export, by ``store_export_record()`` from
``shell/http/routes/report_runs.py``'s ``download_report_pdf`` route: every
successful export writes one row, whether or not it is the first export for
its ``Report`` -- unlike ``Report`` (Story 5.3), which is written at most
once per ``ReportRun``. Never updated by the ORM, never deleted except as
part of the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``).

``elapsed_seconds``/``disposition`` (Story 6.3) capture how a Report went
out: ``elapsed_seconds`` is computed and stored at export time (Client
selection to export, ``download_report_pdf``); ``disposition`` starts
``NULL`` and is set later, exactly once, by ``record_send_disposition()``'s
Core-level ``UPDATE`` -- the one deliberate, narrow bypass of the
``before_update`` immutability guard below, since that guard only fires for
ORM unit-of-work flushes, never for a Core ``update()`` statement (this
story's Design Notes).

Named ``ExportRecord``, not ``StoredExportRecord`` -- mirrors ``Report``'s
own bare naming (``shell/adapters/postgres/report.py``), not
``StoredGateResult``/``StoredNatalChart``'s ``Stored*`` naming, since there
is no ``core/`` type named ``ExportRecord`` to collide with.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Column, event
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel, select, update
from uuid6 import uuid7

from shell.adapters.postgres.columns import _UTCDateTime
from shell.adapters.postgres.report import Report

__all__ = ["ExportRecord", "record_send_disposition", "store_export_record"]


class ExportRecord(SQLModel, table=True):
    """One export of one passed ``Report`` -- ``format`` is a plain string
    (``"pdf"`` today) so a later Markdown follow-up needs no schema change to
    add ``"markdown"`` as a value (this story's Design Notes).

    ``report_id`` (not ``report_run_id``) matches the ERD (``REPORT ||--o{
    EXPORT_RECORD``, ``ARCHITECTURE-SPINE.md``) and keeps one ``ExportRecord``
    tied to exactly the ``Report`` it came from.
    """

    __tablename__ = "export_record"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    report_id: UUID = Field(foreign_key="report.id", index=True)
    #: Never user-typed -- passed by the caller as a fixed literal (``"pdf"``
    #: today, ``"markdown"`` a deferred follow-up) -- but still bounded to an
    #: explicit length, mirroring deferred-work item 41's fix to
    #: ``Client``/``StoredNatalChart``'s own previously-unbounded string
    #: columns (``shell/adapters/postgres/client.py``). 16 is generous for
    #: either value.
    format: str = Field(max_length=16)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )
    #: Whole seconds from the owning ``ReportRun.created_at`` (Client
    #: selection) to this export (``created_at`` above) -- computed once, at
    #: export time, by ``download_report_pdf``, never estimated later
    #: (Story 6.3's Boundaries). ``None`` for rows written before this
    #: column existed (the migration backfills nothing).
    elapsed_seconds: int | None = Field(default=None)
    #: How this export actually went out -- ``"as_generated"`` or
    #: ``"edited"``, never a third value or free text (Story 6.3's
    #: Boundaries). Starts ``NULL``; set at most once, only through
    #: ``record_send_disposition()``'s Core-level ``UPDATE`` below, never
    #: through this ORM object -- the ``before_update`` guard forbids that
    #: unconditionally.
    disposition: str | None = Field(default=None, max_length=16)


@event.listens_for(ExportRecord, "before_update")
def _forbid_update(mapper: Mapper[ExportRecord], connection: object, target: ExportRecord) -> None:
    """A persisted ``ExportRecord`` row is immutable, unconditionally --
    mirrors ``Report``/``StoredGateResult``'s own guard. No code path
    updates a row; this makes an accidental one fail loudly rather than
    silently rewriting what export actually happened."""
    del mapper, connection, target
    raise RuntimeError(
        "ExportRecord rows are immutable once persisted -- no code path may update one."
    )


def store_export_record(
    session: Session, *, report: Report, format: str, elapsed_seconds: int
) -> ExportRecord:
    """Persist one export of ``report``, in one flush.

    ``elapsed_seconds`` is computed by the caller (``download_report_pdf``)
    from that run's own ``created_at`` -- this function only stores it,
    never computes or estimates it (Story 6.3's Boundaries).

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``store_report()``/``store_gate_result()``, so
    it never decides the caller's transaction boundary.
    """
    stored = ExportRecord(
        client_id=report.client_id,
        report_id=report.id,
        format=format,
        elapsed_seconds=elapsed_seconds,
    )
    session.add(stored)
    session.flush()
    return stored


def record_send_disposition(session: Session, *, run_id: UUID, disposition: str) -> bool:
    """Set ``disposition`` on the latest ``ExportRecord`` for ``run_id``'s
    ``Report``, exactly once (Story 6.3).

    Finds the latest row (by ``created_at`` descending, ``id`` descending as
    a deterministic tiebreaker for two rows created within the same
    timestamp resolution -- mirrors ``shell/http/routes/report_runs.py``'s
    own ``_latest_export_record``) via ``Report.report_run_id == run_id`` ->
    ``ExportRecord.report_id``, then updates it through a Core-level
    ``UPDATE ... WHERE disposition IS NULL`` -- never through the ORM
    object, which ``ExportRecord``'s own ``before_update`` listener
    unconditionally forbids. The ``WHERE disposition IS NULL`` clause is
    what makes "set exactly once" atomic:
    a second call for the same run matches zero rows and is a no-op, not an
    error (this story's Design Notes).

    Returns whether a row was actually updated -- ``False`` covers both "no
    ``ExportRecord`` exists at all for ``run_id``" and "the latest one
    already has a ``disposition``"; the caller (the HTTP route) tells those
    two apart itself, by checking for the row's existence before calling
    this function.

    This function only executes the ``UPDATE`` -- it never commits or rolls
    back, exactly like ``store_export_record()``, so it never decides the
    caller's transaction boundary.
    """
    latest_id = session.exec(
        select(ExportRecord.id)
        .join(Report, Report.id == ExportRecord.report_id)
        .where(Report.report_run_id == run_id)
        .order_by(ExportRecord.created_at.desc(), ExportRecord.id.desc())
    ).first()
    if latest_id is None:
        return False

    result: CursorResult[Any] = session.exec(
        update(ExportRecord)
        .where(ExportRecord.id == latest_id, ExportRecord.disposition.is_(None))
        .values(disposition=disposition)
    )
    return result.rowcount > 0
