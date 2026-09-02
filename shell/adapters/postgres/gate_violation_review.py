"""``GateViolationReview``: the immutable, append-only record that Francesco
accepted one Groundedness Gate violation after review (Story 5.7), so a
``Report`` can complete despite it.

Written exactly once per ``(gate_result_id, violation_index)`` pair, by
``store_gate_violation_review()`` from
``shell/http/routes/report_runs.py``'s accept route. Never updated, never
deleted except as part of the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``). ``kind``/``section``/``sentence``/
``entry_ids``/``detail`` are denormalized off the reviewed
``StoredGateResult.violations`` entry at write time -- mirrors
``StoredGateResult``'s own shape -- so this row stands alone as an audit
record, readable without joining back to the (JSON) violations list it was
reviewed from.

``gate_result_id`` + ``violation_index`` together identify exactly which
entry was reviewed: ``GateResult.violations`` is documented as a fixed,
deterministic order for a given ``(draft, payload, vocabulary)`` triple
(``core/types/gate.py``), and ``StoredGateResult.violations`` is the
immutable JSON snapshot of exactly that tuple, so a plain list position is
already a stable, sufficient key for one persisted result (this story's
Design Notes).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import JSON, Column, Index, event
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel
from uuid6 import uuid7

from shell.adapters.postgres.columns import _UTCDateTime
from shell.adapters.postgres.gate_result import StoredGateResult
from shell.adapters.postgres.report_run import ReportRun

__all__ = ["GateViolationReview", "store_gate_violation_review"]


class GateViolationReview(SQLModel, table=True):
    """One accept decision against one violation in one ``StoredGateResult``.

    ``(gate_result_id, violation_index)`` is unique at the schema level
    (``ix_gate_violation_review_gate_result_id_violation_index``, matching
    ``migrations/versions/0023_gate_violation_review.py``): the accept route
    (``shell/http/routes/report_runs.py``) still checks for an existing row
    before writing one as its primary idempotency path, but two
    near-simultaneous submits of the same violation index could otherwise
    both pass that check and each insert a row before either commits -- this
    constraint is the DB-level backstop, and the route catches the resulting
    ``IntegrityError`` and treats the loser exactly like a double-submit.
    """

    __tablename__ = "gate_violation_review"
    __table_args__ = (
        Index(
            "ix_gate_violation_review_gate_result_id_violation_index",
            "gate_result_id",
            "violation_index",
            unique=True,
        ),
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    report_run_id: UUID = Field(foreign_key="report_run.id", index=True)
    # No `index=True` here: the composite unique index above (leftmost
    # column `gate_result_id`) already serves a "every reviewed index for
    # this result" lookup, so a separate single-column index would be
    # redundant -- mirrors the migration's own choice not to create both.
    gate_result_id: UUID = Field(foreign_key="gate_result.id")
    violation_index: int
    kind: str
    section: str
    sentence: str
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of
    # `nullable` from the type annotation, so `nullable=False` must be given
    # explicitly here -- matching `StoredGateResult.violations`'s own JSON
    # column.
    entry_ids: list[str] = Field(sa_column=Column(JSON, nullable=False))
    detail: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


@event.listens_for(GateViolationReview, "before_update")
def _forbid_update(
    mapper: Mapper[GateViolationReview], connection: object, target: GateViolationReview
) -> None:
    """A persisted ``GateViolationReview`` row is immutable, unconditionally
    -- mirrors ``StoredGateResult``/``Report``/``ReportDraft``'s own guard
    (``shell/adapters/postgres/gate_result.py``,
    ``shell/adapters/postgres/report.py``,
    ``shell/adapters/postgres/report_draft.py``). No code path updates a
    row; this makes an accidental one fail loudly rather than silently
    rewriting a review decision Francesco already made."""
    del mapper, connection, target
    raise RuntimeError(
        "GateViolationReview rows are immutable once persisted -- no code path may update one."
    )


def store_gate_violation_review(
    session: Session,
    *,
    run: ReportRun,
    gate_result: StoredGateResult,
    violation_index: int,
    kind: str,
    section: str,
    sentence: str,
    entry_ids: list[str] | tuple[str, ...],
    detail: str,
) -> GateViolationReview:
    """Persist one accept decision against ``gate_result``'s violation at
    ``violation_index``, in one flush.

    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like ``store_gate_result()``
    (``shell/adapters/postgres/gate_result.py``), so it never decides the
    caller's transaction boundary. The caller
    (``shell/http/routes/report_runs.py``'s accept route) is responsible for
    checking that no review row already exists for this
    ``(gate_result.id, violation_index)`` pair before calling this -- this
    function itself does not deduplicate, mirroring every other
    ``store_*()`` function in this package staying a thin, unconditional
    write.
    """
    review = GateViolationReview(
        client_id=run.client_id,
        report_run_id=run.id,
        gate_result_id=gate_result.id,
        violation_index=violation_index,
        kind=kind,
        section=section,
        sentence=sentence,
        entry_ids=list(entry_ids),
        detail=detail,
    )
    session.add(review)
    session.flush()
    return review
