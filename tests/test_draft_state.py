"""``core/draft_state.py`` (Story 10.4, AD-21): which Sections of a draft attempt may be
claimed, whether the draft is finished, whether a Section has run out of attempts --
decided from frozen row values and an explicit ``now``, with no database, clock or thread."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.draft_state import (
    CLOSING_ORDINAL,
    SECTION_NAMES,
    SectionRowState,
    claimable_sections,
    is_draft_complete,
    is_exhausted,
    live_lease_expiries,
    regeneration_ordinals,
)
from core.types.generation import GeneratedDraft

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
MAX = 3


def _rows(
    *, status: str = "pending", attempts: int = 0, claim_expires_at: datetime | None = None
) -> list[SectionRowState]:
    return [
        SectionRowState(
            ordinal=ordinal, status=status, attempts=attempts, claim_expires_at=claim_expires_at
        )
        for ordinal in range(1, 9)
    ]


def _with(rows: list[SectionRowState], ordinal: int, **changes: object) -> list[SectionRowState]:
    return [
        SectionRowState(**{**row.__dict__, **changes}) if row.ordinal == ordinal else row
        for row in rows
    ]


def test_the_section_names_follow_the_generated_draft_fields_in_order() -> None:
    assert tuple(GeneratedDraft.__dataclass_fields__) == SECTION_NAMES
    assert len(SECTION_NAMES) == CLOSING_ORDINAL == 8
    assert SECTION_NAMES[-1] == "consiglio_finale"


def test_sections_one_to_seven_are_claimable_together_and_eight_waits() -> None:
    assert claimable_sections(_rows(), max_attempts=MAX, now=NOW) == (1, 2, 3, 4, 5, 6, 7)


def test_the_closing_section_becomes_claimable_only_when_one_to_seven_are_complete() -> None:
    rows = _rows(status="complete")
    rows = _with(rows, 8, status="pending")
    assert claimable_sections(rows, max_attempts=MAX, now=NOW) == (8,)

    one_missing = _with(rows, 3, status="pending")
    assert claimable_sections(one_missing, max_attempts=MAX, now=NOW) == (3,)


def test_the_closing_section_stays_blocked_while_another_is_failed() -> None:
    rows = _with(_rows(status="complete"), 8, status="pending")
    rows = _with(rows, 2, status="failed")

    assert claimable_sections(rows, max_attempts=MAX, now=NOW) == ()


def test_a_live_lease_blocks_a_claim_and_an_expired_one_does_not() -> None:
    rows = _with(_rows(), 1, claim_expires_at=NOW + timedelta(seconds=1))
    assert 1 not in claimable_sections(rows, max_attempts=MAX, now=NOW)

    expired = _with(_rows(), 1, claim_expires_at=NOW - timedelta(seconds=1))
    assert 1 in claimable_sections(expired, max_attempts=MAX, now=NOW)

    at_the_instant = _with(_rows(), 1, claim_expires_at=NOW)
    assert 1 in claimable_sections(at_the_instant, max_attempts=MAX, now=NOW)


def test_a_section_out_of_attempts_is_not_claimable() -> None:
    rows = _with(_rows(), 4, attempts=MAX)
    assert 4 not in claimable_sections(rows, max_attempts=MAX, now=NOW)
    rows = _with(_rows(), 4, attempts=MAX - 1)
    assert 4 in claimable_sections(rows, max_attempts=MAX, now=NOW)


def test_complete_and_failed_sections_are_never_claimable() -> None:
    assert claimable_sections(_rows(status="complete"), max_attempts=MAX, now=NOW) == ()
    assert claimable_sections(_rows(status="failed"), max_attempts=MAX, now=NOW) == ()


def test_a_draft_is_complete_only_with_all_eight_sections_complete() -> None:
    assert is_draft_complete(_rows(status="complete"))
    assert not is_draft_complete(_with(_rows(status="complete"), 8, status="pending"))
    assert not is_draft_complete(_rows(status="complete")[:7])
    assert not is_draft_complete([])


def test_a_draft_is_exhausted_when_a_section_failed_or_spent_every_attempt() -> None:
    assert not is_exhausted(_rows(), max_attempts=MAX)
    assert not is_exhausted(_with(_rows(), 2, attempts=MAX - 1), max_attempts=MAX)
    assert is_exhausted(_with(_rows(), 2, attempts=MAX), max_attempts=MAX)
    assert is_exhausted(_with(_rows(), 5, status="failed"), max_attempts=MAX)
    assert not is_exhausted(_with(_rows(status="complete"), 5, attempts=MAX), max_attempts=MAX)


def test_live_lease_expiries_lists_only_live_leases_on_pending_rows() -> None:
    soon = NOW + timedelta(seconds=5)
    rows = _with(_rows(), 1, claim_expires_at=soon)
    rows = _with(rows, 2, claim_expires_at=NOW - timedelta(seconds=1))
    rows = _with(rows, 3, status="complete", claim_expires_at=soon)

    assert live_lease_expiries(rows, NOW) == [soon]


def test_the_module_reads_no_clock() -> None:
    """Purity: the same inputs always give the same answer, whatever the wall clock says."""
    rows = _with(_rows(), 1, claim_expires_at=NOW + timedelta(minutes=1))

    assert claimable_sections(rows, max_attempts=MAX, now=NOW) == claimable_sections(
        rows, max_attempts=MAX, now=NOW
    )


def test_regeneration_resets_the_named_section_and_consiglio_finale() -> None:
    assert regeneration_ordinals(["amore"]) == {2, CLOSING_ORDINAL}
    assert regeneration_ordinals(["lavoro", "giorni_di_attenzione", "lavoro"]) == {
        3,
        7,
        CLOSING_ORDINAL,
    }


def test_regeneration_of_consiglio_finale_alone_resets_only_it() -> None:
    assert regeneration_ordinals(["consiglio_finale"]) == {CLOSING_ORDINAL}


def test_regeneration_with_no_resolvable_section_resets_everything() -> None:
    everything = frozenset(range(1, CLOSING_ORDINAL + 1))
    assert regeneration_ordinals([]) == everything
    assert regeneration_ordinals(["not_a_section"]) == everything
    assert regeneration_ordinals(["not_a_section", "amore"]) == {2, CLOSING_ORDINAL}
