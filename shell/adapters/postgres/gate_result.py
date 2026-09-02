"""``StoredGateResult``: the immutable, persisted record of one Groundedness
Gate check (Story 5.6) -- pass or fail, unlike ``Report`` (Story 5.3), which
only ever records a pass.

Written exactly once per Gate check, by ``store_gate_result()`` from
``shell/runner/driver.py``: on a pass, inside ``_run_gate_passed`` alongside
the existing ``store_report(...)`` call; on a failure, inside ``advance()``'s
``except GateFailedError`` block, before ``run.regeneration_count`` is
incremented. Never updated, never deleted except as part of the FR-29
Client-deletion cascade (``shell/adapters/postgres/client.py``).

Named ``Stored*`` to avoid colliding with ``core/types/gate.py``'s
``GateResult`` dataclass -- mirrors ``StoredNatalChart``/``StoredReportTheme``'s
own naming (``shell/adapters/postgres/client.py``,
``shell/adapters/postgres/report_theme.py``).

No query or dashboard code lives here: per ``ARCHITECTURE-SPINE.md``'s
Deferred section, first-generation pass rate and regeneration count as a
series are meant to be answered by querying this table directly, not through
new production code -- ``tests/test_gate_result_store.py`` demonstrates both
queries work against stored rows.
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

from core.types.gate import GateViolation
from shell.adapters.postgres.columns import _UTCDateTime
from shell.adapters.postgres.report_run import ReportRun

__all__ = ["StoredGateResult", "store_gate_result"]


class StoredGateResult(SQLModel, table=True):
    """One Groundedness Gate outcome for one ``ReportRun`` -- pass or fail.

    ``report_run_id`` is indexed but **not** unique: a run may regenerate
    (Story 5.4), and each attempt's Gate check gets its own row, so many
    rows may point at the same ``ReportRun`` -- unlike ``Report.report_run_id``
    (Story 5.3), which is unique because only a pass ever produces a
    ``Report`` row and a run reaches ``gate_passed`` only once.
    ``regeneration_count`` is the value in force when this check ran (the
    pre-increment value on a failure, so row N's ``regeneration_count``
    matches how many automatic regenerations preceded it). ``violations`` is
    a JSON list of every flagged Claim, empty when ``passed`` is ``True``.

    Story 5.8 amendment: a hand-correction can also mint a new, failing
    ``StoredGateResult`` row for a run without ever incrementing
    ``regeneration_count`` (mirrors ``ReportRun.regeneration_count``'s own
    updated comment, ``shell/adapters/postgres/report_run.py``) -- so two
    failing rows for the same run can now share one ``regeneration_count``
    value, and that column no longer uniquely orders a run's rows by
    recency. ``created_at`` is the only reliable "most recent" ordering
    across both minting paths (``shell/http/routes/report_runs.py``'s
    ``_current_cycle_gate_failure``).
    """

    __tablename__ = "gate_result"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    report_run_id: UUID = Field(foreign_key="report_run.id", index=True)
    passed: bool
    regeneration_count: int
    vocabulary_version: int
    # Nullable, no `server_default`: a row written before migration `0021`
    # honestly has no recorded hash (mirrors `0020`'s `month` add-column).
    # Every write after `0021` populates it. `max_length=64` mirrors
    # `StoredNatalChart.computation_config_content_hash`'s width -- a sha256
    # hex digest -- though that precedent is NOT NULL, whereas this column
    # is deliberately nullable (pre-`0021` rows have no recorded hash).
    vocabulary_content_hash: str | None = Field(default=None, max_length=64)
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of
    # `nullable` from the type annotation, so `nullable=False` must be given
    # explicitly here -- matching `ReportDraft.draft`'s own JSON column.
    violations: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


@event.listens_for(StoredGateResult, "before_update")
def _forbid_update(
    mapper: Mapper[StoredGateResult], connection: object, target: StoredGateResult
) -> None:
    """A persisted ``StoredGateResult`` row is immutable, unconditionally --
    mirrors ``Report``/``ReportDraft``'s own guard
    (``shell/adapters/postgres/report.py``,
    ``shell/adapters/postgres/report_draft.py``). No code path updates a
    row; this makes an accidental one fail loudly rather than silently
    rewriting what a Gate check actually found."""
    del mapper, connection, target
    raise RuntimeError(
        "StoredGateResult rows are immutable once persisted -- no code path may update one."
    )


def _json_safe(value: Any) -> Any:
    """A frozen dataclass -> its fields recursively converted the same way, a
    tuple/list -> a list of converted items -- everything else passes
    through unchanged.

    Identical in shape to ``ReportDraft.draft``'s own ``_json_safe``
    (``shell/adapters/postgres/report_draft.py``): ``GateViolation``
    (``core/types/gate.py``) carries only ``str`` and ``tuple[str, ...]``
    fields, the same narrow shape ``GeneratedDraft``/``Sentence`` do.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in dataclass_fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def store_gate_result(
    session: Session,
    *,
    run: ReportRun,
    passed: bool,
    regeneration_count: int,
    vocabulary_version: int,
    vocabulary_content_hash: str,
    violations: tuple[GateViolation, ...],
) -> StoredGateResult:
    """Persist one Groundedness Gate outcome for ``run``, in one flush.

    ``regeneration_count`` is always passed explicitly by the caller, never
    read from ``run.regeneration_count`` here: the fail-path caller
    (``shell/runner/driver.py::advance()``'s ``except GateFailedError`` block)
    must record the count in force *before* its own subsequent
    ``run.regeneration_count += 1``, so this function trusts whatever value
    it is given rather than reading the row itself.

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``store_report()``
    (``shell/adapters/postgres/report.py``), so it never decides the
    caller's transaction boundary.
    """
    stored = StoredGateResult(
        client_id=run.client_id,
        report_run_id=run.id,
        passed=passed,
        regeneration_count=regeneration_count,
        vocabulary_version=vocabulary_version,
        vocabulary_content_hash=vocabulary_content_hash,
        violations=_json_safe(violations),
    )
    session.add(stored)
    session.flush()
    return stored
