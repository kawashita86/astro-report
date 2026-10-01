"""``ReportDraftSection``: one Section of one draft attempt, written on its own (AD-21).

The row exists so a draft can be written piece by piece: Sections 1-7 in parallel,
Consiglio finale last, each saved the moment it is complete, so a restart or a
failure loses at most the Section in flight. ``status`` is ``pending`` until the
Section is written (``complete``) or has spent every attempt (``failed``); there is
no in-progress status, because a live lease (``claim_expires_at`` in the future)
is what says someone is writing it right now -- the lease lives in
``shell/runner/lease.py``. What the rows *mean* is decided in ``core/draft_state.py``.

The composite unique index leads with ``report_run_id``, so it also serves lookups by run.
Rows are keyed by ``(report_run_id, attempt, ordinal)`` with ``attempt`` numbered
exactly like ``ReportDraft.attempt``, so a draft attempt's Sections and the one
``ReportDraft`` assembled from them share a coordinate. They are cascade-deleted
with their Client (``delete_client_and_derived``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, Index
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select
from uuid6 import uuid7

from core.draft_state import (
    SECTION_NAMES,
    STATUS_PENDING,
    SectionRowState,
)
from core.types.generation import Sentence
from shell.adapters.postgres.columns import _UTCDateTime

__all__ = [
    "ReportDraftSection",
    "open_section_rows",
    "section_rows",
    "section_state",
    "sentences_from_json",
    "sentences_to_json",
]


class ReportDraftSection(SQLModel, table=True):
    """One Section of one ``(ReportRun, attempt)``."""

    __tablename__ = "report_draft_section"
    __table_args__ = (
        Index(
            "ix_report_draft_section_run_attempt_ordinal",
            "report_run_id",
            "attempt",
            "ordinal",
            unique=True,
        ),
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    report_run_id: UUID = Field(foreign_key="report_run.id")
    attempt: int
    ordinal: int
    name: str = Field(max_length=32)
    status: str = Field(default=STATUS_PENDING, max_length=16)
    # The written sentences as ``[{"text": ..., "entry_ids": [...]}]``; ``None`` until complete.
    sentences: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    attempts: int = Field(default=0)
    last_error: str | None = Field(default=None)
    claimed_at: datetime | None = Field(default=None, sa_column=Column(_UTCDateTime, nullable=True))
    claim_expires_at: datetime | None = Field(
        default=None, sa_column=Column(_UTCDateTime, nullable=True)
    )


def sentences_to_json(sentences: tuple[Sentence, ...]) -> list[dict[str, Any]]:
    """Sentences -> their stored JSON form."""
    return [
        {"text": sentence.text, "entry_ids": list(sentence.entry_ids)} for sentence in sentences
    ]


def sentences_from_json(raw: list[dict[str, Any]]) -> tuple[Sentence, ...]:
    """The reverse of :func:`sentences_to_json`."""
    return tuple(Sentence(text=item["text"], entry_ids=tuple(item["entry_ids"])) for item in raw)


def section_state(row: ReportDraftSection) -> SectionRowState:
    """The frozen view ``core/draft_state.py`` reasons about."""
    return SectionRowState(
        ordinal=row.ordinal,
        status=row.status,
        attempts=row.attempts,
        claim_expires_at=row.claim_expires_at,
    )


def section_rows(session: Session, run_id: UUID, attempt: int) -> list[ReportDraftSection]:
    """Every row of one draft attempt, by ordinal."""
    return list(
        session.exec(
            select(ReportDraftSection)
            .where(ReportDraftSection.report_run_id == run_id)
            .where(ReportDraftSection.attempt == attempt)
            .order_by(ReportDraftSection.ordinal)  # type: ignore[arg-type]
        ).all()
    )


def open_section_rows(session: Session, run_id: UUID, attempt: int) -> bool:
    """Create the eight ``pending`` rows of ``attempt``; ``False`` if they already exist.

    Runs in a savepoint so a concurrent opener's unique-index conflict leaves the
    caller's transaction usable. Flushes, never commits.
    """
    try:
        with session.begin_nested():
            for ordinal, name in enumerate(SECTION_NAMES, start=1):
                session.add(
                    ReportDraftSection(
                        report_run_id=run_id, attempt=attempt, ordinal=ordinal, name=name
                    )
                )
            session.flush()
    except IntegrityError:
        return False
    return True
