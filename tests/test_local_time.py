"""Story 11.2: the shared local-civil-time to UTC conversion.

One rule, two consumers (the geocoder and the chart data API), so a DST gap or
fold is judged identically wherever a birth time is converted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

import pytest

from core.errors import LocalTimeError
from shell.local_time import local_to_utc


def test_winter_and_summer_use_the_offset_in_force_then() -> None:
    winter = local_to_utc(datetime(2026, 1, 15, 12, 0), "Europe/Rome")
    summer = local_to_utc(datetime(2026, 6, 15, 12, 0), "Europe/Rome")

    assert winter.offset == timedelta(hours=1)
    assert winter.utc == datetime(2026, 1, 15, 11, 0, tzinfo=UTC)
    assert summer.offset == timedelta(hours=2)
    assert summer.utc == datetime(2026, 6, 15, 10, 0, tzinfo=UTC)


def test_a_historical_date_uses_that_dates_rules_not_todays() -> None:
    # Italy had no DST in March 1985 before the 31st.
    instant = local_to_utc(datetime(1985, 3, 12, 14, 30), "Europe/Rome")

    assert instant.utc == datetime(1985, 3, 12, 13, 30, tzinfo=UTC)


def test_a_spring_forward_gap_is_refused_as_a_gap() -> None:
    with pytest.raises(LocalTimeError) as caught:
        local_to_utc(datetime(2026, 3, 29, 2, 30), "Europe/Rome")

    assert caught.value.kind == "gap"
    assert "does not exist" in str(caught.value)


def test_a_fall_back_fold_is_refused_as_a_fold() -> None:
    with pytest.raises(LocalTimeError) as caught:
        local_to_utc(datetime(2026, 10, 25, 2, 30), "Europe/Rome")

    assert caught.value.kind == "fold"
    assert "ambiguous" in str(caught.value)


def test_lenient_mode_gives_the_transition_instant_for_a_midnight_gap() -> None:
    # Sao Paulo's 2018 DST began at local midnight: 00:00 does not exist.
    boundary = datetime(2018, 11, 4, 0, 0)
    with pytest.raises(LocalTimeError):
        local_to_utc(boundary, "America/Sao_Paulo")

    lenient = local_to_utc(boundary, "America/Sao_Paulo", strict=False)

    assert lenient.utc == datetime(2018, 11, 4, 3, 0, tzinfo=UTC)


def test_lenient_mode_takes_the_first_occurrence_of_a_repeated_time() -> None:
    # Havana's 2018 fall-back repeated 00:00-01:00 on 4 November.
    repeated = datetime(2018, 11, 4, 0, 30)

    lenient = local_to_utc(repeated, "America/Havana", strict=False)

    assert lenient.offset == timedelta(hours=-4)


def test_an_aware_datetime_is_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        local_to_utc(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), "Europe/Rome")


def test_an_unknown_zone_raises_zone_info_not_found() -> None:
    with pytest.raises(ZoneInfoNotFoundError):
        local_to_utc(datetime(2026, 1, 1, 12, 0), "Mars/Olympus_Mons")
