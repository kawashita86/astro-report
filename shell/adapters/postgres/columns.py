"""Shared SQLAlchemy column types for the Postgres adapters
(epic-6-retro-item-52).

``_UTCDateTime`` began life in ``shell/adapters/postgres/report_run.py`` and
grew to nine sibling importers -- a module that also defines an unrelated
table is the wrong home for a type they all depend on. It lives here now;
``report_run.py`` re-exports it for backward compatibility.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime as _DateTime
from sqlalchemy.types import TypeDecorator

__all__ = ["_UTCDateTime"]


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
