"""Drafting-view Section states and the seen diff, tested with no database or clock (Story 10.6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.draft_state import SectionRowState
from shell.http.section_rail import (
    build_rail,
    changed_ordinals,
    format_seen,
    parse_seen,
    rail_summary,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
LIVE = NOW + timedelta(minutes=2)
STALE = NOW - timedelta(minutes=2)


def _row(
    ordinal: int, status: str = "pending", attempts: int = 0, lease: datetime | None = None
) -> SectionRowState:
    return SectionRowState(
        ordinal=ordinal, status=status, attempts=attempts, claim_expires_at=lease
    )


def _states(rows: list[SectionRowState], *, prior: bool = False) -> dict[int, str]:
    return {row.ordinal: row.label for row in build_rail(rows, prior_draft_exists=prior, now=NOW)}


def test_a_missing_row_reads_as_pending() -> None:
    labels = _states([])

    assert set(labels.values()) == {"In attesa"}


def test_complete_failed_and_leased_rows_read_scritta_non_riuscita_in_scrittura() -> None:
    labels = _states(
        [
            _row(1, "complete"),
            _row(2, "failed", attempts=3),
            _row(3, lease=LIVE, attempts=1),
            _row(4, attempts=1, lease=STALE),
            _row(5),
        ]
    )

    assert labels[1] == "Scritta"
    assert labels[2] == "Non riuscita"
    assert labels[3] == "In scrittura"
    assert labels[4] == "In scrittura"  # a retry in flight keeps reading as writing
    assert labels[5] == "In attesa"


def test_reset_sections_of_a_later_attempt_read_da_rifare_then_in_scrittura() -> None:
    rows = [_row(n, "complete") for n in (1, 2, 4, 5, 6, 7)] + [_row(3), _row(8)]

    waiting = _states(rows, prior=True)
    assert waiting[3] == "Da rifare"
    assert waiting[1] == "Scritta"

    leased = _states([*rows[:-2], _row(3, lease=LIVE), _row(8)], prior=True)
    assert leased[3] == "In scrittura"


def test_consiglio_finale_waits_until_sections_one_to_seven_are_written() -> None:
    assert _states([_row(n, "complete") for n in range(1, 7)] + [_row(7), _row(8)])[8] == (
        "In attesa delle altre Sezioni"
    )
    assert _states([_row(n, "complete") for n in range(1, 8)] + [_row(8)])[8] == "In attesa"
    assert _states([_row(n, "complete") for n in range(1, 8)] + [_row(8, lease=LIVE)])[8] == (
        "In scrittura"
    )


def test_the_summary_counts_written_sections() -> None:
    rail = build_rail([_row(1, "complete"), _row(2, "complete")], prior_draft_exists=False, now=NOW)

    assert rail_summary(rail) == "2 di 8 Sezioni scritte"


def test_seen_round_trips_and_only_differing_rows_are_reported_changed() -> None:
    rail = build_rail([_row(1, "complete"), _row(2, lease=LIVE)], prior_draft_exists=False, now=NOW)

    assert changed_ordinals(rail, parse_seen(format_seen(rail))) == ()
    stale = parse_seen("1:writing,2:writing")
    assert changed_ordinals(rail[:3], stale) == (1, 3)
    assert changed_ordinals(rail, {}) == tuple(range(1, 9))


def test_parse_seen_drops_malformed_entries() -> None:
    assert parse_seen("1:complete,x:y,3,4:,5:writing") == {1: "complete", 5: "writing"}
    assert parse_seen(None) == {}
