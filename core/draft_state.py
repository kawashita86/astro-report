"""What a draft attempt's Section rows say about the draft, decided purely (AD-21).

The driver stores one row per Section and a lease on each, but it never decides
what those rows mean: this module does, from frozen values and an explicit
``now``. Keeping the rule here means "which Sections may be written next" is a
function the tests can exercise without a database, a clock or a thread, and
means the one-Section-at-a-time protocol cannot drift between the loop that
submits work and the code that checks whether the draft is finished.

There is deliberately no in-progress status: a live lease on a ``pending`` row is
what marks a Section as being written. Sections 1-7 are claimable together;
Consiglio finale (ordinal 8) is written blind to nothing, so it waits until 1-7
are ``complete`` and is shown their text.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from datetime import datetime

from core.types.generation import GeneratedDraft

__all__ = [
    "CLOSING_ORDINAL",
    "SECTION_NAMES",
    "STATUS_COMPLETE",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "SectionRowState",
    "claimable_sections",
    "is_draft_complete",
    "is_exhausted",
    "is_lease_live",
    "live_lease_expiries",
    "regeneration_ordinals",
]

#: The eight Section names in AD-6's fixed order; ordinal ``n`` is ``SECTION_NAMES[n - 1]``.
SECTION_NAMES: tuple[str, ...] = tuple(field.name for field in fields(GeneratedDraft))

#: Consiglio finale, the one Section that waits for the others.
CLOSING_ORDINAL = len(SECTION_NAMES)

STATUS_PENDING = "pending"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class SectionRowState:
    """The fields of one ``report_draft_section`` row this module reasons about."""

    ordinal: int
    status: str
    attempts: int
    claim_expires_at: datetime | None


def is_lease_live(row: SectionRowState, now: datetime) -> bool:
    """Whether another writer currently holds ``row``'s lease."""
    return row.claim_expires_at is not None and row.claim_expires_at > now


def live_lease_expiries(rows: Sequence[SectionRowState], now: datetime) -> list[datetime]:
    """When each live lease on a still-pending row runs out."""
    return [
        row.claim_expires_at
        for row in rows
        if row.status == STATUS_PENDING
        and row.claim_expires_at is not None
        and is_lease_live(row, now)
    ]


def claimable_sections(
    rows: Sequence[SectionRowState], *, max_attempts: int, now: datetime
) -> tuple[int, ...]:
    """Ordinals that may be claimed now, ascending.

    A row is claimable when it is ``pending``, has attempts left and carries no live
    lease; Consiglio finale additionally needs every one of Sections 1-7 ``complete``.
    """
    complete = {row.ordinal for row in rows if row.status == STATUS_COMPLETE}
    others_done = all(ordinal in complete for ordinal in range(1, CLOSING_ORDINAL))
    claimable: list[int] = []
    for row in sorted(rows, key=lambda candidate: candidate.ordinal):
        if row.status != STATUS_PENDING or row.attempts >= max_attempts:
            continue
        if is_lease_live(row, now):
            continue
        if row.ordinal == CLOSING_ORDINAL and not others_done:
            continue
        claimable.append(row.ordinal)
    return tuple(claimable)


def is_draft_complete(rows: Sequence[SectionRowState]) -> bool:
    """Whether all eight Sections exist and are ``complete``."""
    return len(rows) == len(SECTION_NAMES) and all(row.status == STATUS_COMPLETE for row in rows)


def is_exhausted(rows: Sequence[SectionRowState], *, max_attempts: int) -> bool:
    """Whether some Section can never complete: it failed, or spent every attempt."""
    return any(
        row.status == STATUS_FAILED
        or (row.status == STATUS_PENDING and row.attempts >= max_attempts)
        for row in rows
    )


def regeneration_ordinals(violation_sections: Iterable[str]) -> frozenset[int]:
    """Ordinals a regeneration must rewrite after the Gate named ``violation_sections``.

    Each named Section is reset, and Consiglio finale with it whenever any of
    Sections 1-7 is (it is written from their text, so it would otherwise go stale).
    Names that match no Section are ignored; when none matches at all there is nothing
    to target, so every Section is rewritten -- the same full attempt as a first draft.
    """
    named = {SECTION_NAMES.index(name) + 1 for name in violation_sections if name in SECTION_NAMES}
    if not named:
        return frozenset(range(1, CLOSING_ORDINAL + 1))
    if any(ordinal < CLOSING_ORDINAL for ordinal in named):
        named.add(CLOSING_ORDINAL)
    return frozenset(named)
