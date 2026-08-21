"""``ReportDraft``: the immutable, persisted form of one ``ReportRun``'s
Generator output (Story 4.6, AD-3/AD-6).

Written exactly once per ``ReportRun``, by ``store_report_draft()`` from
``shell/runner/driver.py``'s ``draft_ready`` stage -- never updated, never
deleted except as part of the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``). ``draft`` stores the raw
``GeneratedDraft`` verbatim (eight Sections of cited sentences, ``entry_ids``
intact) -- rendering it into prose/list form happens only in
``shell/http/draft_view.py``, at view time, never baked into storage (this
story's Boundaries).
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, event
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel
from uuid6 import uuid7

from core.types.generation import GeneratedDraft
from shell.adapters.postgres.report_run import ReportRun, _UTCDateTime

__all__ = ["ReportDraft", "store_report_draft"]


class ReportDraft(SQLModel, table=True):
    """One frozen, persisted ``GeneratedDraft``
    (``shell/ports/generator.py::Generator.generate()``'s return), one row
    per ``ReportRun``, tagged with the Style Guide version and the
    Section-composition (``SectionsConfig``) version that produced it -- so a
    persisted draft is traceable back to what generated it, mirroring
    ``ReportPayload``'s own traceability shape.

    ``draft`` stores the whole ``GeneratedDraft`` verbatim as JSON (each of
    the eight Sections as a list of ``{"text": ..., "entry_ids": [...]}``
    objects) -- mirrors ``StoredReportTheme.theme``'s own whole-value-as-JSON
    shape.
    """

    __tablename__ = "report_draft"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    # `unique=True` is this story's "exactly one ReportDraft per ReportRun",
    # enforced at the schema level -- not merely by `store_report_draft()`
    # only ever being called once per `ReportRun` in
    # `shell/runner/driver.py`'s `draft_ready` stage.
    report_run_id: UUID = Field(foreign_key="report_run.id", unique=True, index=True)
    style_guide_version: int
    sections_config_version: int
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of
    # `nullable` from the type annotation, so `nullable=False` must be given
    # explicitly here -- matching `StoredReportTheme.theme`'s own JSON column.
    draft: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


@event.listens_for(ReportDraft, "before_update")
def _forbid_update(
    mapper: Mapper[ReportDraft], connection: object, target: ReportDraft
) -> None:
    """A persisted ``ReportDraft`` row is immutable, unconditionally --
    mirrors ``ReportPayload``/``StoredReportTheme``'s own guard
    (``shell/adapters/postgres/report_payload.py``,
    ``shell/adapters/postgres/report_theme.py``). No code path updates a
    row; this makes an accidental one fail loudly rather than silently
    changing what a citation into a rendered draft points at."""
    del mapper, connection, target
    raise RuntimeError(
        "ReportDraft rows are immutable once persisted -- no code path may update one."
    )


def _json_safe(value: Any) -> Any:
    """A frozen dataclass -> its fields recursively converted the same way, a
    tuple/list -> a list of converted items -- everything else passes
    through unchanged.

    Narrower than ``StoredReportTheme.theme``'s own ``_json_safe``
    (``shell/adapters/postgres/report_theme.py``) by construction, not by
    omission: ``GeneratedDraft``/``Sentence`` (``core/types/generation.py``)
    carry neither ``Decimal`` nor ``datetime`` fields, only ``str`` and
    ``tuple[str, ...]``.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in dataclass_fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def store_report_draft(
    session: Session,
    *,
    run: ReportRun,
    style_guide_version: int,
    sections_config_version: int,
    draft: GeneratedDraft,
) -> ReportDraft:
    """Persist ``draft`` (the ``Generator`` port's return) for ``run``, in one
    flush.

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``store_report_theme()``
    (``shell/adapters/postgres/report_theme.py``), so it never decides the
    caller's transaction boundary. ``shell/runner/driver.py::drive()``
    commits once this and the rest of the ``draft_ready`` stage have
    succeeded.
    """
    report_draft = ReportDraft(
        client_id=run.client_id,
        report_run_id=run.id,
        style_guide_version=style_guide_version,
        sections_config_version=sections_config_version,
        draft=_json_safe(draft),
    )
    session.add(report_draft)
    session.flush()
    return report_draft
