"""``ReportPayload``: the immutable, persisted form of one ``ReportRun``'s
frozen Report Payload (Story 3.8, PRD FR-14).

Written exactly once per ``ReportRun``, by ``store_report_payload()`` from
``shell/runner/driver.py``'s ``payload_ready`` stage -- never updated, never
deleted except as part of the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``). This is what makes a citation into a
Report mean the same thing years later: the row it points at cannot change
underneath it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, event
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel
from uuid6 import uuid7

from shell.adapters.postgres.columns import _UTCDateTime
from shell.adapters.postgres.report_run import ReportRun

__all__ = ["ReportPayload", "store_report_payload"]


class ReportPayload(SQLModel, table=True):
    """One frozen, versioned Report Payload (``core/payload/freeze.py::freeze_payload()``'s
    return), tagged with exactly what produced it: the schema version, the
    ``computation.toml``/``sections.toml`` version and content hash, and the
    verified ephemeris file identity -- mirrors ``StoredNatalChart``'s own
    traceability shape.

    ``payload`` stores ``freeze_payload()``'s whole return dict verbatim
    through the ``JSON`` column. With no custom ``json_serializer`` on the
    engine that is ``json.dumps``'s default output -- unsorted keys, default
    ``", "``/``": "`` whitespace -- *not* the sorted, whitespace-free form of
    ``core/payload/freeze.py::canonical_json_bytes`` (which is used only for
    the content hashes and the Generator prompt). ``Decimal`` values are
    already fixed-precision strings by the time they arrive, because
    ``freeze_payload``'s ``_json_safe`` converts them. Every field this table
    also carries as its own typed column is present again inside it, so the
    row is self-describing even read outside this table's own columns.
    """

    __tablename__ = "report_payload"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    # `unique=True` is PRD FR-14's "every stored Report has exactly one
    # stored Report Payload", enforced at the schema level -- not merely by
    # `store_report_payload()` only ever being called once per `ReportRun`
    # in `shell/runner/driver.py`'s `payload_ready` stage.
    report_run_id: UUID = Field(foreign_key="report_run.id", unique=True, index=True)
    schema_version: int
    computation_config_version: int
    computation_config_content_hash: str
    sections_config_version: int
    sections_config_content_hash: str
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of
    # `nullable` from the type annotation, so `nullable=False` must be given
    # explicitly here -- matching `StoredNatalChart`'s own JSON columns.
    ephemeris_files: list[dict[str, str]] = Field(sa_column=Column(JSON, nullable=False))
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


@event.listens_for(ReportPayload, "before_update")
def _forbid_update(
    mapper: Mapper[ReportPayload], connection: object, target: ReportPayload
) -> None:
    """A persisted ``ReportPayload`` row is immutable, unconditionally --
    FR-14 reads "immutable once its Report is generated," but nothing in this
    codebase yet produces a Report, so "immutable from the moment it is
    persisted" is the only implementable reading (see Story 3.8's Design
    Notes). No code path updates a row; this makes an accidental one fail
    loudly rather than silently corrupting a citation."""
    del mapper, connection, target
    raise RuntimeError(
        "ReportPayload rows are immutable once persisted -- no code path may update one."
    )


def store_report_payload(
    session: Session, *, run: ReportRun, frozen: dict[str, Any]
) -> ReportPayload:
    """Persist ``frozen`` (``core/payload/freeze.py::freeze_payload()``'s
    return) for ``run``, in one flush.

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``create_client_with_chart()``
    (``shell/adapters/postgres/client.py``), so it never decides the caller's
    transaction boundary. ``shell/runner/driver.py::drive()`` commits once
    this and the rest of the ``payload_ready`` stage have succeeded.
    """
    report_payload = ReportPayload(
        client_id=run.client_id,
        report_run_id=run.id,
        schema_version=frozen["schema_version"],
        computation_config_version=frozen["computation_config_version"],
        computation_config_content_hash=frozen["computation_config_content_hash"],
        sections_config_version=frozen["sections_config_version"],
        sections_config_content_hash=frozen["sections_config_content_hash"],
        ephemeris_files=frozen["ephemeris_files"],
        payload=frozen,
    )
    session.add(report_payload)
    session.flush()
    return report_payload
