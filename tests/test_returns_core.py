"""Story 11.5: the solar-return instant and the comparison with the natal chart.

The three Astro.com fixtures (``solar-return-*.toml``) pin the instant, planets,
angles and cusps; the invariants below hold for any input.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.positions import _angular_separation
from core.ephemeris.returns import solar_return_instant
from core.errors import EphemerisRangeError
from core.returns.comparison import compare_to_natal
from shell.computation import load_computation_config
from tests.conformance.runner import FIXTURES_DIR, load_fixture

CONFIG = load_computation_config()

#: Local midnight two days before the birthday in the requested year, in the
#: birthplace zone, per fixture (the shell derives it; the core takes it as given).
SEARCH_START = {
    "solar-return-leap-day-birthplace": datetime(2026, 2, 26, 5, tzinfo=UTC),
    "solar-return-leap-day-relocated": datetime(2026, 2, 26, 5, tzinfo=UTC),
    "solar-return-new-year": datetime(2026, 12, 30, 6, tzinfo=UTC),
}
BIRTH_INSTANT = {
    "leap-day-birth": datetime(2024, 2, 29, 10, 12, tzinfo=UTC),
    "near-midnight-birth": datetime(2026, 1, 1, 6, 0, tzinfo=UTC),
}


def _birth(name: str) -> tuple[datetime, D, D]:
    data = load_fixture(FIXTURES_DIR / f"{name}.toml").birth_data
    return BIRTH_INSTANT[name], D(data["latitude"]), D(data["longitude"])


@pytest.mark.parametrize("fixture_name", sorted(SEARCH_START))
def test_the_chart_matches_the_astro_com_solar_return(fixture_name: str) -> None:
    fixture = load_fixture(FIXTURES_DIR / f"{fixture_name}.toml")
    tolerance = D(fixture.metadata["tolerance_degrees"])
    birth, birth_lat, birth_lon = _birth(fixture.birth_data["solar_return_of"][0])
    expected = fixture.expected

    instant = solar_return_instant(birth, SEARCH_START[fixture_name])
    expected_instant = datetime.fromisoformat(expected["return_instant_utc"])
    assert abs(instant - expected_instant) <= timedelta(
        seconds=int(fixture.metadata["instant_tolerance_seconds"])
    )

    place = fixture.birth_data.get("location")
    lat, lon = (D(place["latitude"]), D(place["longitude"])) if place else (birth_lat, birth_lon)
    chart = compute_natal_chart(instant, lat, lon, CONFIG)

    assert _angular_separation(chart.ascendant, D(expected["ascendant"])) <= tolerance
    assert _angular_separation(chart.midheaven, D(expected["midheaven"])) <= tolerance
    by_name = {p.name: p for p in chart.planets}
    for planet in expected["planets"]:
        assert _angular_separation(by_name[planet["name"]].longitude, D(planet["longitude"])) <= (
            tolerance
        ), planet
    cusp_tolerance = D(fixture.metadata["cusp_tolerance_degrees"])
    for cusp in expected["houses"]:
        computed = chart.houses[cusp["number"] - 1].longitude
        assert _angular_separation(computed, D(cusp["longitude"])) <= cusp_tolerance, cusp


@pytest.mark.parametrize("fixture_name", sorted(SEARCH_START))
def test_the_return_sun_sits_on_the_natal_sun(fixture_name: str) -> None:
    fixture = load_fixture(FIXTURES_DIR / f"{fixture_name}.toml")
    birth, lat, lon = _birth(fixture.birth_data["solar_return_of"][0])

    instant = solar_return_instant(birth, SEARCH_START[fixture_name])
    natal_sun = compute_natal_chart(birth, lat, lon, CONFIG).planets[0].longitude
    return_sun = compute_natal_chart(instant, lat, lon, CONFIG).planets[0].longitude

    assert _angular_separation(natal_sun, return_sun) <= D("0.0003")


def test_the_return_is_the_first_crossing_at_or_after_the_search_start() -> None:
    birth, _, _ = _birth("leap-day-birth")
    start = SEARCH_START["solar-return-leap-day-birthplace"]

    first = solar_return_instant(birth, start)
    # A search that begins after that crossing finds the next year's, not this one.
    later = solar_return_instant(birth, first + timedelta(days=1))

    assert start <= first < first + timedelta(days=1) <= later
    assert timedelta(days=364) < later - first < timedelta(days=367)


def test_the_birth_year_search_finds_the_birth_instant() -> None:
    birth, _, _ = _birth("near-midnight-birth")

    assert solar_return_instant(birth, birth - timedelta(days=2)) == birth


def test_a_search_past_the_ephemeris_is_out_of_range() -> None:
    birth, _, _ = _birth("leap-day-birth")

    with pytest.raises(EphemerisRangeError):
        solar_return_instant(birth, datetime(2399, 12, 31, tzinfo=UTC))


@pytest.mark.parametrize(
    "bad",
    [datetime(2026, 2, 26), datetime(2026, 2, 26, tzinfo=timezone(timedelta(hours=1)))],
    ids=["naive", "offset"],
)
def test_it_rejects_a_non_utc_instant(bad: datetime) -> None:
    birth, _, _ = _birth("leap-day-birth")

    with pytest.raises(ValueError):
        solar_return_instant(birth, bad)


def test_a_fresh_thread_binds_the_ephemeris_path_itself() -> None:
    """The ephemeris path is thread-local C state; the function must bind it, not
    rely on the caller's thread having done so."""
    birth, _, _ = _birth("leap-day-birth")
    start = SEARCH_START["solar-return-leap-day-birthplace"]
    results: list[datetime] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(solar_return_instant(birth, start))
        except BaseException as error:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()

    assert not errors and results == [solar_return_instant(birth, start)]


def test_relocation_changes_the_houses_not_the_planets() -> None:
    birth, lat, lon = _birth("leap-day-birth")
    instant = solar_return_instant(birth, SEARCH_START["solar-return-leap-day-birthplace"])

    home = compute_natal_chart(instant, lat, lon, CONFIG)
    milan = compute_natal_chart(instant, D("45.4667"), D("9.2"), CONFIG)

    assert [p.longitude for p in home.planets] == [p.longitude for p in milan.planets]
    assert home.ascendant != milan.ascendant and home.houses != milan.houses


def test_the_comparison_places_the_return_in_the_natal_houses() -> None:
    birth, lat, lon = _birth("leap-day-birth")
    instant = solar_return_instant(birth, SEARCH_START["solar-return-leap-day-birthplace"])
    natal = compute_natal_chart(birth, lat, lon, CONFIG)
    rs = compute_natal_chart(instant, lat, lon, CONFIG)

    comparison = compare_to_natal(rs, natal, CONFIG.orbs.natal)

    assert 1 <= comparison.rs_ascendant_in_natal_house <= 12
    assert [e.body for e in comparison.rs_planets_in_natal_houses] == [p.name for p in rs.planets]
    assert all(1 <= e.house <= 12 for e in comparison.rs_planets_in_natal_houses)
    # The return Sun is on the natal Sun, so that conjunction is always there.
    sun_sun = next(
        a for a in comparison.rs_to_natal_aspects if (a.rs_body, a.natal_body) == ("sun", "sun")
    )
    assert sun_sun.aspect == "conjunction" and sun_sun.orb <= D("0.0003")
    assert all(a.orb <= CONFIG.orbs.natal for a in comparison.rs_to_natal_aspects)
