"""``ReportDraft``: the immutable, persisted form of one ``ReportRun``'s
Generator output (Story 4.6, AD-3/AD-6).

Written by ``store_report_draft()`` from ``shell/runner/driver.py``'s
``draft_ready`` stage -- never updated, never deleted except as part of the
FR-29 Client-deletion cascade (``shell/adapters/postgres/client.py``).
``draft`` stores the raw ``GeneratedDraft`` verbatim (eight Sections of cited
sentences, ``entry_ids`` intact) -- rendering it into prose/list form happens
only in ``shell/http/draft_view.py``, at view time, never baked into storage
(this story's Boundaries).

One row per ``(ReportRun, attempt)`` as of Story 5.4, not one row per
``ReportRun``: a Groundedness Gate failure regenerates the whole Report,
producing a new ``ReportDraft`` tagged with the next ``attempt`` from the
same stored Payload -- append-only-per-attempt, never updated or replaced.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, Index, event
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel
from uuid6 import uuid7

from core.types.generation import GeneratedDraft
from shell.adapters.postgres.columns import _UTCDateTime
from shell.adapters.postgres.report_run import ReportRun

__all__ = ["ReportDraft", "store_report_draft"]


class ReportDraft(SQLModel, table=True):
    """One frozen, persisted ``GeneratedDraft``
    (``shell/ports/generator.py::Generator.generate()``'s return), one row
    per ``(ReportRun, attempt)`` (Story 5.4 loosened this from one row per
    ``ReportRun``), tagged with the Style Guide version and the
    Section-composition (``SectionsConfig``) version that produced it -- so a
    persisted draft is traceable back to what generated it, mirroring
    ``ReportPayload``'s own traceability shape.

    ``draft`` stores the whole ``GeneratedDraft`` verbatim as JSON (each of
    the eight Sections as a list of ``{"text": ..., "entry_ids": [...]}``
    objects) -- mirrors ``StoredReportTheme.theme``'s own whole-value-as-JSON
    shape.
    """

    __tablename__ = "report_draft"
    # "Exactly one ReportDraft per (ReportRun, attempt)", enforced at the
    # schema level (Story 5.4) -- not merely by `store_report_draft()`'s own
    # call discipline. Replaces the old unique-on-`report_run_id`-alone
    # index: a second draft for the same run is no longer a bug once
    # regeneration is real, but a second draft at the same attempt still is.
    # A plain unique `Index`, not a `UniqueConstraint` -- named and shaped to
    # match `migrations/versions/0012_bounded_regeneration.py`'s own
    # `ix_report_draft_report_run_id_attempt` exactly (same name, same
    # object type: a unique index, not a table constraint), mirroring how
    # `0009_report_draft.py`'s `ix_report_draft_report_run_id` already
    # mirrored this table's old `Field(unique=True, index=True)`. Keeping
    # the ORM metadata and the migrated schema in exact agreement avoids
    # spurious `alembic --autogenerate` drift.
    __table_args__ = (
        Index(
            "ix_report_draft_report_run_id_attempt", "report_run_id", "attempt", unique=True
        ),
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    report_run_id: UUID = Field(foreign_key="report_run.id", index=True)
    # Which regeneration attempt produced this row (Story 5.4) -- `0` for
    # the first, never-regenerated draft, incrementing by one each time
    # `shell/runner/driver.py::advance()` regenerates after a Groundedness
    # Gate failure. Tagged by `_run_draft_ready` with `run.regeneration_count`
    # at persist time.
    attempt: int = Field(default=0)
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
    attempt: int = 0,
) -> ReportDraft:
    """Persist ``draft`` (the ``Generator`` port's return) for ``run`` at
    ``attempt``, in one flush.

    ``attempt`` defaults to ``0`` (the first, never-regenerated draft);
    ``shell/runner/driver.py``'s ``_run_draft_ready`` always passes
    ``run.regeneration_count`` explicitly (Story 5.4). A second call for the
    same ``(run, attempt)`` pair raises ``IntegrityError`` at the schema
    level (``ReportDraft.__table_args__``'s unique constraint), not here.

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``store_report_theme()``
    (``shell/adapters/postgres/report_theme.py``), so it never decides the
    caller's transaction boundary. ``shell/runner/driver.py::advance()``
    commits once this and the rest of the ``draft_ready`` stage have
    succeeded.
    """
    report_draft = ReportDraft(
        client_id=run.client_id,
        report_run_id=run.id,
        attempt=attempt,
        style_guide_version=style_guide_version,
        sections_config_version=sections_config_version,
        draft=_json_safe(draft),
    )
    session.add(report_draft)
    session.flush()
    return report_draft
