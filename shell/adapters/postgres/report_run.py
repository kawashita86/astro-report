"""``ReportRun``: the persisted execution frame driving a Client-month's
computation through AD-10's six named stages (Story 3.5).

A row is created once, then advanced forward-only by
``shell/runner/driver.py::drive()`` -- never re-created, never rewound.
Persisting each stage's output before the next begins (rather than holding
run state only in memory) means a spin-down or redeploy never loses a whole
run: the next call to ``drive()``, from either the start route or the poll
route, resumes exactly where the row left off. A persistent rate-limit
stall on the Generator (``draft_ready``) is handled the same way, plus its
own bounded failure counter (``stage_failure_count``/``failed_at``/
``failure_reason``, Story 4.8): once too many consecutive attempts exhaust
``with_backoff``, the run is marked terminally failed instead of being
retried by every future poll forever.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column
from sqlalchemy import DateTime as _DateTime
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

__all__ = ["ReportRun"]


class _UTCDateTime(TypeDecorator):
    """A timezone-aware UTC ``datetime`` that round-trips identically on
    Postgres (production) and SQLite (the Postgres stand-in every test in
    this codebase uses, ``tests/test_client_store.py`` onward).

    Plain ``DateTime(timezone=True)`` is enough on Postgres -- ``psycopg``
    always returns a ``tzinfo``-aware value for a ``TIMESTAMPTZ`` column.
    SQLite has no native timezone-aware storage, so the same column reads
    back *naive* there, and every value this table ever stores is UTC by
    construction (``client_month_interval_utc``, ``datetime.now(UTC)``) --
    so a naive value read back is unambiguously UTC, re-attached here rather
    than left to trip ``core/transits/*``'s strict UTC-awareness check
    (``core/`` itself is never modified, per this story's Boundaries).
    """

    impl = _DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class ReportRun(SQLModel, table=True):
    """One Client-month's execution frame.

    ``stage`` is ``None`` until ``natal_ready`` first completes -- "nothing
    has advanced yet", not a seventh named state. ``month_start_utc``/
    ``month_end_utc`` are set by ``natal_ready``; ``transit_events`` is set
    by ``transits_ready``. Both stay ``NULL`` until their producing stage
    runs, which is exactly how a partially-driven row is told apart from a
    fully-driven one after a restart.

    ``transit_events`` holds every result from the four Story 3.1-3.4 scan
    functions as one JSON list, each entry tagged ``"kind"``
    (``aspect``/``station``/``standing_retrograde``/``ingress``/``lunation``)
    since the four scan functions return different dataclasses -- see
    ``shell/runner/driver.py``'s Design Notes for why this is one column
    rather than four new tables.

    ``stage_failure_count``/``failed_at``/``failure_reason`` (Story 4.8)
    track consecutive ``with_backoff`` exhaustions on the current stage
    across separate ``drive()`` calls, and the terminal-failure state that
    accumulating enough of them produces -- see each field's own comment
    below for its exact semantics.
    """

    __tablename__ = "report_run"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
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
