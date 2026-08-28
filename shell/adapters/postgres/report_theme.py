"""``StoredReportTheme``: the immutable, persisted form of one ``ReportRun``'s
purely-derived ``ReportTheme`` (Story 4.3, AD-14).

Written exactly once per ``ReportRun``, by ``store_report_theme()`` from
``shell/runner/driver.py``'s ``payload_ready`` stage, right after
``store_report_payload()`` -- never updated, never deleted except as part of
the FR-29 Client-deletion cascade (``shell/adapters/postgres/client.py``).
Mirrors ``ReportPayload``'s own shape and immutability guard: a Client's
continuity input for their next month's Report must never change underneath
an already-generated Report.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, event
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel, select
from uuid6 import uuid7

from core.types.memory import ReportTheme
from shell.adapters.postgres.columns import _UTCDateTime
from shell.adapters.postgres.report_run import ReportRun

__all__ = ["StoredReportTheme", "most_recent_prior_report_theme", "store_report_theme"]


class StoredReportTheme(SQLModel, table=True):
    """One frozen, persisted ``ReportTheme``
    (``core/memory/derive.py::derive_theme()``'s return), one row per
    ``ReportRun``.

    ``theme`` stores the whole ``ReportTheme`` verbatim as JSON (``Decimal``
    and ``datetime`` fields serialized to strings, since JSON has neither
    type natively) -- mirrors ``ReportPayload.payload``'s own
    whole-value-as-JSON shape.
    """

    __tablename__ = "report_theme"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    # `unique=True` is this story's "exactly one StoredReportTheme per
    # ReportRun", enforced at the schema level -- not merely by
    # `store_report_theme()` only ever being called once per `ReportRun` in
    # `shell/runner/driver.py`'s `payload_ready` stage.
    report_run_id: UUID = Field(foreign_key="report_run.id", unique=True, index=True)
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of
    # `nullable` from the type annotation, so `nullable=False` must be given
    # explicitly here -- matching `ReportPayload.payload`'s own JSON column.
    theme: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


@event.listens_for(StoredReportTheme, "before_update")
def _forbid_update(
    mapper: Mapper[StoredReportTheme], connection: object, target: StoredReportTheme
) -> None:
    """A persisted ``StoredReportTheme`` row is immutable, unconditionally --
    mirrors ``ReportPayload``'s own guard (``shell/adapters/postgres/report_payload.py``).
    No code path updates a row; this makes an accidental one fail loudly
    rather than silently corrupting a later month's continuity input."""
    del mapper, connection, target
    raise RuntimeError(
        "StoredReportTheme rows are immutable once persisted -- no code path may update one."
    )


def _json_safe(value: Any) -> Any:
    """``Decimal`` -> ``str``, ``datetime`` -> ISO 8601, a frozen dataclass ->
    its fields recursively converted the same way, a tuple/list -> a list of
    converted items -- everything else passes through unchanged.

    Recursive, like ``core/payload/freeze.py``'s own ``_json_safe`` (not
    imported -- that module lives in ``core/``; this small serializer lives
    here instead, matching how ``shell/adapters/postgres/client.py`` and
    ``shell/runner/driver.py`` each already own a small ``_json_safe`` of
    their own rather than sharing one).
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in dataclass_fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def most_recent_prior_report_theme(
    session: Session, client_id: UUID, *, before_month: str
) -> StoredReportTheme | None:
    """The most recent ``StoredReportTheme`` for ``client_id`` whose
    ``ReportRun.month`` is strictly less than ``before_month`` (Story 4.7,
    AD-14) -- "most recent", not "the immediately preceding calendar month":
    a skipped month must not reset a genuinely still-active slow transit
    back to "first Report" behavior (see this story's Design Notes).

    Ordered by ``ReportRun.month`` (string comparison, correct because the
    format is always zero-padded ``"YYYY-MM"``), not by row-creation order --
    multiple ``ReportRun``s can be persisted out of creation order (this
    story's own I/O & Edge-Case Matrix). Two ``StoredReportTheme`` rows for the
    same Client and the same month are broken by ``created_at`` then ``id``,
    both descending, so the row returned is deterministic regardless of
    insertion order. Returns ``None`` when no such row exists (the Client's
    first Report, or no prior run ever reached ``payload_ready``).
    """
    return session.exec(
        select(StoredReportTheme)
        .join(ReportRun, StoredReportTheme.report_run_id == ReportRun.id)
        .where(ReportRun.client_id == client_id, ReportRun.month < before_month)
        .order_by(
            ReportRun.month.desc(),
            StoredReportTheme.created_at.desc(),
            StoredReportTheme.id.desc(),
        )
        .limit(1)
    ).first()


def store_report_theme(
    session: Session, *, run: ReportRun, theme: ReportTheme
) -> StoredReportTheme:
    """Persist ``theme`` (``core/memory/derive.py::derive_theme()``'s return)
    for ``run``, in one flush.

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``store_report_payload()``
    (``shell/adapters/postgres/report_payload.py``), so it never decides the
    caller's transaction boundary. ``shell/runner/driver.py::drive()``
    commits once this and the rest of the ``payload_ready`` stage have
    succeeded.
    """
    stored_report_theme = StoredReportTheme(
        client_id=run.client_id,
        report_run_id=run.id,
        theme=_json_safe(theme),
    )
    session.add(stored_report_theme)
    session.flush()
    return stored_report_theme
