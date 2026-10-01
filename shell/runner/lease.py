"""The claim lease on a Section row: how two writers never write the same Section (AD-21).

A claim is one atomic conditional ``UPDATE`` -- take the lease only if the row is
still ``pending`` and nobody holds a live lease -- committed on its own short
session, so it is visible to every other loop and every other process the moment
it is taken. A caller that cannot take the claim is told so and changes nothing:
it never waits, queues or retries in-process. The lease expires by itself
(``LEASE_TTL``), so a process that dies mid-call leaves a Section that is
reclaimable, not stuck.

``section_claim`` yields the claim's token -- the ``claimed_at`` it wrote -- or ``None``
when refused. The token fences every later write for that claim (outcome writes apply only
while the row still carries it), so a writer whose lease expired and was reclaimed by
another cannot overwrite the new holder's work.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, or_, update
from sqlmodel import Session

from core.draft_state import STATUS_PENDING
from shell.adapters.postgres.report_draft_section import ReportDraftSection

__all__ = ["LEASE_TTL", "section_claim"]

#: One Section call is bounded well inside this (adapter timeout plus backoff); a
#: lease outlives it comfortably and an expired one is reclaimable.
LEASE_TTL = timedelta(minutes=3)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@contextmanager
def section_claim(
    engine: Engine,
    section_id: UUID,
    *,
    now: Callable[[], datetime] = _utc_now,
    ttl: timedelta = LEASE_TTL,
) -> Iterator[datetime | None]:
    """Try one Section's claim once; yield its token if held (else ``None``), release it
    on exit if held.

    The body must write nothing when ``None`` is yielded. The lease is released
    only when this call took it, so a refused caller never frees another's claim.
    """
    taken_at = now()
    with Session(engine) as session:
        granted = session.execute(
            update(ReportDraftSection)
            .where(ReportDraftSection.id == section_id)  # type: ignore[arg-type]
            .where(ReportDraftSection.status == STATUS_PENDING)  # type: ignore[arg-type]
            .where(
                or_(
                    ReportDraftSection.claim_expires_at.is_(None),  # type: ignore[union-attr]
                    ReportDraftSection.claim_expires_at <= taken_at,  # type: ignore[arg-type,operator]
                )
            )
            .values(claimed_at=taken_at, claim_expires_at=taken_at + ttl)
        )
        session.commit()
        held = granted.rowcount == 1  # type: ignore[attr-defined]
    try:
        yield taken_at if held else None
    finally:
        if held:
            _release(engine, section_id, taken_at)


def _release(engine: Engine, section_id: UUID, taken_at: datetime) -> None:
    """Free the lease this claim took -- and only that one: a lease another writer
    took after this one expired carries a different ``claimed_at`` and is left alone.
    A claim an outcome write already freed or converted into a retry hold-off
    (``claimed_at`` cleared) is likewise left alone."""
    with Session(engine) as session:
        session.execute(
            update(ReportDraftSection)
            .where(ReportDraftSection.id == section_id)  # type: ignore[arg-type]
            .where(ReportDraftSection.claimed_at == taken_at)  # type: ignore[arg-type]
            .values(claimed_at=None, claim_expires_at=None)
        )
        session.commit()
