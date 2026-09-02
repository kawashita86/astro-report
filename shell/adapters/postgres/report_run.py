"""``ReportRun``: the persisted execution frame driving a Client-month's
computation through AD-10's six named stages (Story 3.5).

A row is created once, then advanced forward-only by
``shell/runner/driver.py::advance()`` -- never re-created, never rewound.
Persisting each stage's output before the next begins (rather than holding
run state only in memory) means a spin-down or redeploy never loses a whole
run: the next poll calls ``advance()``, which resumes exactly where the row
left off (AD-20: one stage per poll, from the poll route only). A persistent
rate-limit stall on the Generator (``draft_ready``) is handled the same way,
plus its own bounded failure counter (``stage_failure_count``/``failed_at``/
``failure_reason``, Story 4.8): once too many consecutive attempts exhaust
``with_backoff``, the run is marked terminally failed instead of being
retried by every future poll forever.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

# ``_UTCDateTime`` now lives in ``shell/adapters/postgres/columns.py``
# (epic-6-retro-item-52); imported here only because ``ReportRun``'s own
# timestamp columns still use it.
from shell.adapters.postgres.columns import _UTCDateTime

__all__ = ["ReportRun"]


class ReportRun(SQLModel, table=True):
    """One Client-month's execution frame.

    ``stage`` is ``None`` until ``natal_ready`` first completes -- "nothing
    has advanced yet", not a seventh named state. ``month_start_utc``/
    ``month_end_utc`` are set by ``natal_ready``; ``transit_events`` is set
    by ``transits_ready``. Both stay ``NULL`` until their producing stage
    runs, which is exactly how a partially-advanced row is told apart from a
    fully-advanced one after a restart.

    ``transit_events`` holds every result from the four Story 3.1-3.4 scan
    functions as one JSON list, each entry tagged ``"kind"``
    (``aspect``/``station``/``standing_retrograde``/``ingress``/``lunation``)
    since the four scan functions return different dataclasses -- see
    ``shell/runner/driver.py``'s Design Notes for why this is one column
    rather than four new tables.

    ``stage_failure_count``/``failed_at``/``failure_reason`` (Story 4.8)
    track consecutive ``with_backoff`` exhaustions on the current stage
    across separate ``advance()`` calls, and the terminal-failure state that
    accumulating enough of them produces -- see each field's own comment
    below for its exact semantics.

    ``regeneration_count`` (Story 5.4) is a separate counter tracking
    ``gate_passed`` regeneration attempts across the run's current
    regeneration cycle -- distinct from ``stage_failure_count``, which a
    successful ``draft_ready`` re-run resets to 0 every cycle and so cannot
    also track a persistent Gate problem. See
    ``shell/runner/driver.py``'s Design Notes.
    """

    __tablename__ = "report_run"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    # Set exactly once, inside `advance()`'s existing per-stage success path
    # (`shell/runner/driver.py`), the first time `stage_name == "natal_ready"`
    # succeeds -- mirrors `month_start_utc`/`month_end_utc`'s own
    # forward-only assignment (Story 6.4). `NULL` for any `ReportRun` row
    # created before this column existed, and for one that never reached
    # `natal_ready` -- both cases leave "which chart produced this run"
    # undeterminable, which is exactly what the Client-history listing
    # (`shell/http/routes/clients.py`) treats as "not markable as
    # superseded."
    natal_chart_id: UUID | None = Field(default=None, foreign_key="natal_chart.id", index=True)
    month: str
    stage: str | None = Field(default=None)
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of
    # `nullable` from the type annotation, so `nullable=True` must be given
    # explicitly here -- matching `StoredNatalChart.superseded_at`'s own
    # pattern for a nullable timestamp column.
    month_start_utc: datetime | None = Field(
        default=None, sa_column=Column(_UTCDateTime, nullable=True)
    )
    month_end_utc: datetime | None = Field(
        default=None, sa_column=Column(_UTCDateTime, nullable=True)
    )
    transit_events: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    # Consecutive `with_backoff` exhaustions on the current stage (Story
    # 4.8) -- reset to 0 by a successful stage advance, incremented on each
    # exhaustion, compared against `_MAX_STAGE_FAILURES`
    # (`shell/runner/driver.py`) to decide when a run is terminally failed
    # rather than retried forever.
    stage_failure_count: int = Field(default=0)
    # Gate failures absorbed across the run's current regeneration cycle
    # (Story 5.4) -- incremented on every `GateFailedError`, compared
    # against `_MAX_REGENERATIONS` (`shell/runner/driver.py`) to decide
    # when a run is terminally failed rather than regenerated forever.
    # Never reset by a successful stage advance, unlike
    # `stage_failure_count` -- see that field's own comment above.
    #
    # Counts failures absorbed, not regenerations completed:
    # `regeneration_count == 1` means one Gate failure has just been caught
    # and one regeneration is about to run next, not that one has already
    # finished.
    #
    # Story 5.8 amendment: this no longer uniquely determines the next
    # `ReportDraft.attempt` value. Before Story 5.8, N here corresponded to
    # N+1 total `ReportDraft.attempt` values persisted for this run once that
    # Nth regeneration's own draft landed -- attempt `0` the original,
    # never-regenerated draft, attempts `1..N` the regenerations this counter
    # tracked. Once a hand-correction (Story 5.8) can also mint a new
    # `ReportDraft` row for this run without ever incrementing this counter,
    # that one-to-one correspondence no longer holds; the next attempt number
    # is instead a plain count of existing `ReportDraft` rows for the run
    # (`shell/adapters/postgres/report_draft.py::next_report_draft_attempt`),
    # which both the automatic path (`shell/runner/driver.py::_run_draft_ready`)
    # and the hand-correction route (`shell/http/routes/report_runs.py`) read
    # instead of this field.
    regeneration_count: int = Field(default=0)
    # `NULL` until a run is marked terminally failed; a timestamp then marks
    # it permanently, mirroring `StoredNatalChart.superseded_at`'s own
    # nullable-timestamp pattern for "this row's normal life is over."
    failed_at: datetime | None = Field(default=None, sa_column=Column(_UTCDateTime, nullable=True))
    # Set alongside `failed_at`, never independently -- the reason shown to
    # Francesco in the poll fragment.
    failure_reason: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )
