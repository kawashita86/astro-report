"""Story 11.2: the noon chart for an unknown birth time, as a pure computation."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.time_unknown import compute_time_unknown_chart
from core.types.chart import TimeUnknownChart
from shell.computation import load_computation_config

CONFIG = load_computation_config()


def _day(year: int, month: int, day: int) -> tuple[datetime, datetime, datetime]:
    """A UTC calendar day as (noon, start, next start)."""
    start = datetime(year, month, day, tzinfo=UTC)
    return start + timedelta(hours=12), start, start + timedelta(days=1)


def _chart(year: int, month: int, day: int) -> TimeUnknownChart:
    return compute_time_unknown_chart(*_day(year, month, day), CONFIG)


def test_the_type_has_no_angle_or_house_fields() -> None:
    names = {field.name for field in dataclasses.fields(TimeUnknownChart)}
    planet_names = {field.name for field in dataclasses.fields(_chart(2024, 3, 25).planets[0])}

    assert names == {"planets", "aspects"}
    assert "house" not in planet_names and "ascendant" not in names


def test_noon_positions_equal_the_exact_time_chart_at_noon() -> None:
    noon, start, end = _day(1985, 3, 12)

    unknown = compute_time_unknown_chart(noon, start, end, CONFIG)
    exact = compute_natal_chart(noon, Decimal(45), Decimal(9), CONFIG)

    exact_by_name = {planet.name: planet for planet in exact.planets}
    assert [planet.name for planet in unknown.planets] == [p.name for p in exact.planets]
    for planet in unknown.planets:
        assert planet.longitude == exact_by_name[planet.name].longitude
        assert planet.sign == exact_by_name[planet.name].sign
        assert planet.degree == exact_by_name[planet.name].degree
        assert planet.retrograde == exact_by_name[planet.name].retrograde


def test_every_body_carries_its_range_across_the_day() -> None:
    chart = _chart(1985, 3, 12)

    for planet in chart.planets:
        assert planet.range_from != planet.range_to or planet.name == "south_node"
    sun = next(planet for planet in chart.planets if planet.name == "sun")
    assert sun.range_to > sun.range_from  # the Sun moves about a degree a day, forward


def test_aspects_exclude_the_moon_and_match_the_exact_chart_otherwise() -> None:
    noon, start, end = _day(1985, 3, 12)

    unknown = compute_time_unknown_chart(noon, start, end, CONFIG)
    exact = compute_natal_chart(noon, Decimal(45), Decimal(9), CONFIG)

    assert any("moon" in (a.body1, a.body2) for a in exact.aspects), "fixture day must test this"
    assert all("moon" not in (a.body1, a.body2) for a in unknown.aspects)
    assert unknown.aspects == tuple(a for a in exact.aspects if "moon" not in (a.body1, a.body2))


def test_a_body_crossing_a_sign_during_the_day_is_sign_uncertain() -> None:
    # The Sun entered Aries at 03:06 UTC on 2024-03-20.
    ingress_day = {p.name: p for p in _chart(2024, 3, 20).planets}
    quiet_day = {p.name: p for p in _chart(2024, 3, 25).planets}

    assert ingress_day["sun"].sign_uncertain is True
    assert ingress_day["sun"].range_from > ingress_day["sun"].range_to  # 359.x -> 0.x
    assert quiet_day["sun"].sign_uncertain is False


def test_a_moon_ingress_day_spans_both_signs_and_is_uncertain() -> None:
    from core.ephemeris.chart import sign_and_degree

    found_changing = found_steady = False
    for day in range(1, 29):
        moon = next(p for p in _chart(2024, 3, day).planets if p.name == "moon")
        first = sign_and_degree(moon.range_from)[0]
        last = sign_and_degree(moon.range_to)[0]
        assert moon.sign_uncertain is (first != last or moon.sign != first)
        if first != last:
            found_changing = True
            assert moon.sign in {first, last}
        else:
            found_steady = found_steady or not moon.sign_uncertain

    assert found_changing and found_steady


def test_south_node_mirrors_the_true_node() -> None:
    chart = {p.name: p for p in _chart(2024, 3, 25).planets}

    assert (chart["true_node"].longitude + 180) % 360 == chart["south_node"].longitude


def test_a_naive_instant_is_refused() -> None:
    noon, start, end = _day(2024, 3, 25)

    with pytest.raises(ValueError, match="UTC"):
        compute_time_unknown_chart(noon.replace(tzinfo=None), start, end, CONFIG)


def test_misordered_instants_are_refused() -> None:
    noon, start, end = _day(2024, 3, 25)

    with pytest.raises(ValueError, match="ordered|<="):
        compute_time_unknown_chart(noon, end, start, CONFIG)
