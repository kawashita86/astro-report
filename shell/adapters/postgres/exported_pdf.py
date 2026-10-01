"""``ExportedPdf``: the stored PDF bytes of a Report's last export, keyed by a
fingerprint of everything that PDF depends on.

It exists because rendering a PDF through WeasyPrint is the slowest thing the
app does, and a repeat download of an unchanged Report would otherwise pay
that cost again. It is a derived cache, rebuilt on demand, so it is
deliberately left out of backup/restore (``_BACKUP_MODELS``) and holds one row
per Report (a miss replaces the row) to keep storage bounded.

Like the other stores here, ``store_pdf`` and ``get_stored_pdf`` never commit
or roll back the caller's transaction; a failed store must never fail the
download, so the insert runs inside a savepoint whose ``IntegrityError`` (a
race on the unique ``report_id``) is swallowed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Column, LargeBinary
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, delete, select
from uuid6 import uuid7

from shell.adapters.postgres.columns import _UTCDateTime

_LOGGER = logging.getLogger(__name__)

__all__ = ["ExportedPdf", "pdf_fingerprint", "get_stored_pdf", "store_pdf"]


class ExportedPdf(SQLModel, table=True):
    """The PDF bytes last exported for one ``Report`` and the fingerprint of
    the inputs they were rendered from."""

    __tablename__ = "exported_pdf"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    report_id: UUID = Field(foreign_key="report.id", unique=True, index=True)
    fingerprint: str = Field(max_length=64)
    pdf_bytes: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


def pdf_fingerprint(
    *,
    rendered: dict[str, Any],
    client_name: str,
    birth_date: object,
    birth_time: object,
    birthplace_name: str | None,
    month: str,
    chart_id: UUID,
    template_hash: str,
    natal_orbs: Decimal,
) -> str:
    """SHA-256 hex over a canonical JSON of every input the PDF depends on.

    The wheel SVG is deliberately not an input: it is a pure function of
    ``chart_id`` and ``natal_orbs``, both hashed, so a cache hit costs no
    Kerykeion work.
    """
    canonical = json.dumps(
        {
            "rendered": rendered,
            "client_name": client_name,
            "birth_date": str(birth_date),
            "birth_time": str(birth_time),
            "birthplace_name": birthplace_name,
            "month": month,
            "chart_id": str(chart_id),
            "template_hash": template_hash,
            "natal_orbs": str(natal_orbs),
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_stored_pdf(session: Session, report_id: UUID, fingerprint: str) -> bytes | None:
    """The stored bytes for ``report_id`` when its fingerprint matches, else
    ``None``."""
    row = session.exec(select(ExportedPdf).where(ExportedPdf.report_id == report_id)).first()
    if row is None or row.fingerprint != fingerprint:
        return None
    return row.pdf_bytes


def store_pdf(session: Session, report_id: UUID, fingerprint: str, pdf_bytes: bytes) -> None:
    """Replace the row for ``report_id`` with ``pdf_bytes``, inside a
    savepoint; an ``IntegrityError`` (concurrent first export) is swallowed
    because the cache is best-effort."""
    try:
        with session.begin_nested():
            session.exec(delete(ExportedPdf).where(ExportedPdf.report_id == report_id))
            session.add(
                ExportedPdf(report_id=report_id, fingerprint=fingerprint, pdf_bytes=pdf_bytes)
            )
            session.flush()
    except IntegrityError:
        _LOGGER.warning("exported_pdf store skipped for report %s (concurrent write)", report_id)
