"""``ExportRecord``: the immutable, persisted record of one Report export
(Story 6.2) -- PDF today, Markdown a deferred follow-up (``deferred-work.md``).

Written once per export, by ``store_export_record()`` from
``shell/http/routes/report_runs.py``'s ``download_report_pdf`` route: every
successful export writes one row, whether or not it is the first export for
its ``Report`` -- unlike ``Report`` (Story 5.3), which is written at most
once per ``ReportRun``. Never updated, never deleted except as part of the
FR-29 Client-deletion cascade (``shell/adapters/postgres/client.py``).

Named ``ExportRecord``, not ``StoredExportRecord`` -- mirrors ``Report``'s
own bare naming (``shell/adapters/postgres/report.py``), not
``StoredGateResult``/``StoredNatalChart``'s ``Stored*`` naming, since there
is no ``core/`` type named ``ExportRecord`` to collide with.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Column, event
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel
from uuid6 import uuid7

from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_run import _UTCDateTime

__all__ = ["ExportRecord", "store_export_record"]


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


def store_export_record(session: Session, *, report: Report, format: str) -> ExportRecord:
    """Persist one export of ``report``, in one flush.

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``store_report()``/``store_gate_result()``, so
    it never decides the caller's transaction boundary.
    """
    stored = ExportRecord(
        client_id=report.client_id,
        report_id=report.id,
        format=format,
    )
    session.add(stored)
    session.flush()
    return stored
