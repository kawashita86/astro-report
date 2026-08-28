"""``Report``: the immutable, structural record that a ``ReportRun``'s draft
passed the Groundedness Gate (Story 5.3, AD-1).

Written exactly once per ``ReportRun``, by ``store_report()`` from
``shell/runner/driver.py``'s ``gate_passed`` stage -- and only on a passing
``GateResult`` (``core/gate/run.py::run_gate()``), never before, never
updated, never deleted except as part of the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``). A ``Report`` row's mere existence
for a given id is the whole of what ``shell/export.py::export_report()``
reads to decide whether an export is allowed: no row for an id means the
Gate has never passed for whatever produced it (this story's Boundaries).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Column, event
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel
from uuid6 import uuid7

from shell.adapters.postgres.columns import _UTCDateTime
from shell.adapters.postgres.report_run import ReportRun

__all__ = ["Report", "store_report"]


class Report(SQLModel, table=True):
    """One passed Groundedness Gate outcome for one ``ReportRun``.

    Records exactly which versions of the Style Guide, the Report Payload
    schema and the Gate vocabulary produced this pass -- mirrors
    ``ReportDraft``/``ReportPayload``'s own traceability shape, so a
    ``Report`` row is traceable back to exactly what generated and checked
    it, even though it stores no content of its own (the content stays in
    the already-persisted ``ReportDraft``/``ReportPayload`` rows it points
    at via ``report_run_id``).
    """

    __tablename__ = "report"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    # `unique=True`: exactly one `Report` per `ReportRun` -- a run only ever
    # reaches `gate_passed` once (`drive()`'s forward-only stage advance),
    # enforced at the schema level too, not merely by `store_report()` only
    # ever being called once per `ReportRun` in `shell/runner/driver.py`'s
    # `gate_passed` stage. Mirrors `ReportDraft.report_run_id`.
    report_run_id: UUID = Field(foreign_key="report_run.id", unique=True, index=True)
    style_guide_version: int
    payload_schema_version: int
    gate_vocabulary_version: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


@event.listens_for(Report, "before_update")
def _forbid_update(mapper: Mapper[Report], connection: object, target: Report) -> None:
    """A persisted ``Report`` row is immutable, unconditionally -- mirrors
    ``ReportDraft``/``ReportPayload``'s own guard
    (``shell/adapters/postgres/report_draft.py``,
    ``shell/adapters/postgres/report_payload.py``). No code path updates a
    row; this makes an accidental one fail loudly rather than silently
    changing what a passed Gate outcome recorded."""
    del mapper, connection, target
    raise RuntimeError("Report rows are immutable once persisted -- no code path may update one.")


def store_report(
    session: Session,
    *,
    run: ReportRun,
    style_guide_version: int,
    payload_schema_version: int,
    gate_vocabulary_version: int,
) -> Report:
    """Persist a passed Groundedness Gate outcome for ``run``, in one flush.

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``store_report_draft()``
    (``shell/adapters/postgres/report_draft.py``), so it never decides the
    caller's transaction boundary. ``shell/runner/driver.py::drive()``
    commits once this and the rest of the ``gate_passed`` stage have
    succeeded. Called only after a passing ``GateResult`` -- never on
    failure (Story 5.3's Boundaries).
    """
    report = Report(
        client_id=run.client_id,
        report_run_id=run.id,
        style_guide_version=style_guide_version,
        payload_schema_version=payload_schema_version,
        gate_vocabulary_version=gate_vocabulary_version,
    )
    session.add(report)
    session.flush()
    return report
