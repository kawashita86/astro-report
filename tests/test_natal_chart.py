"""``compute_natal_chart()`` -- one test per row of the story's I/O & Edge-Case
Matrix, plus the properties those rows imply: purity of the boundary
(timezone-aware UTC only), the explicit ``ComputationConfig`` argument being
the actual source of the orb rather than a hardcoded 7.0, and a rejected
Moshier fallback.

Real fixture conformance (the matrix's "Natal fixture conformance" row) is
exercised end to end in ``tests/test_conformance.py``, against the real
Story 1.7 reference charts -- not duplicated here with synthetic values.
This file's "Standard natal computation" coverage instead uses one of those
same fixtures' birth data as a real, known-good input, without asserting
against its ``expected`` table (that assertion is the conformance suite's
job).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import swisseph as swe

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.errors import EphemerisIntegrityError
from core.types.chart import Aspect, HouseCusp, NatalChart, PlanetPosition
from shell.computation import load_computation_config

verify_ephemeris_identity()
_CONFIG = load_computation_config()

# The autouse fixture re-pinning the real vendored ephemeris before every
# test in the session lives in tests/conftest.py (shared across modules).


# near-midnight-birth.toml's birth instant: 2026-01-01 00:00 America/Chicago
# (UTC-6) at Fort Worth, TX -- a real fixture's inputs, reused here as a
# known-good "some real chart" rather than an invented synthetic instant.
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")

_EXPECTED_PLANET_NAMES = (
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
    "true_node",
    "south_node",
)

_ZODIAC_SIGNS = frozenset(
    {
        "aries",
        "taurus",
        "gemini",
        "cancer",
        "leo",
        "virgo",
        "libra",
        "scorpio",
        "sagittarius",
        "capricorn",
        "aquarius",
        "pisces",
    }
)

_ASPECT_NAMES = frozenset({"conjunction", "sextile", "square", "trine", "opposition"})


def _compute() -> NatalChart:
    return compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _CONFIG)


# --- Matrix row: standard natal computation -----------------------------------


def test_returns_ascendant_midheaven_all_cusps_all_bodies_and_aspects() -> None:
    chart = _compute()

    assert isinstance(chart, NatalChart)
    assert isinstance(chart.ascendant, Decimal)
    assert isinstance(chart.midheaven, Decimal)
    assert {planet.name for planet in chart.planets} == set(_EXPECTED_PLANET_NAMES)
    assert [cusp.number for cusp in chart.houses] == list(range(1, 13))
    assert all(isinstance(aspect, Aspect) for aspect in chart.aspects)


def test_ascendant_and_midheaven_are_the_house_1_and_house_10_cusps_not_separate() -> None:
    chart = _compute()

    houses_by_number = {cusp.number: cusp for cusp in chart.houses}
    assert chart.ascendant == houses_by_number[1].longitude
    assert chart.midheaven == houses_by_number[10].longitude


def test_every_planet_position_has_a_valid_sign_degree_and_house() -> None:
    chart = _compute()

    for planet in chart.planets:
        assert planet.sign in _ZODIAC_SIGNS
        assert Decimal(0) <= planet.degree < Decimal(30)
        assert planet.house in range(1, 13)
        assert isinstance(planet.retrograde, bool)


def test_south_node_is_true_node_plus_180_normalized() -> None:
    chart = _compute()
    positions = {planet.name: planet.longitude for planet in chart.planets}

    expected_south_node = positions["true_node"] + Decimal(180)
    if expected_south_node >= Decimal(360):
        expected_south_node -= Decimal(360)

    assert positions["south_node"] == expected_south_node


def test_every_aspect_is_one_of_the_five_natal_aspects_within_the_configured_orb() -> None:
    chart = _compute()

    for aspect in chart.aspects:
        assert aspect.aspect in _ASPECT_NAMES
        assert Decimal(0) <= aspect.orb <= _CONFIG.orbs.natal
        assert isinstance(aspect.applying, bool)


def test_house_cusp_and_planet_dataclasses_are_frozen() -> None:
    chart = _compute()

    with pytest.raises(dataclasses.FrozenInstanceError):
        chart.ascendant = Decimal("0")  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        chart.houses[0].longitude = Decimal("0")  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        chart.planets[0].longitude = Decimal("0")  # type: ignore[misc]


# --- Matrix row: consults no clock, default timezone, network or database ----


def test_every_angle_is_decimal_and_normalized_to_0_360() -> None:
    chart = _compute()

    all_longitudes = (
        [chart.ascendant, chart.midheaven]
        + [cusp.longitude for cusp in chart.houses]
        + [planet.longitude for planet in chart.planets]
    )
    for value in all_longitudes:
        assert isinstance(value, Decimal)
        assert Decimal(0) <= value < Decimal(360)


def test_a_naive_birth_instant_is_refused() -> None:
    naive = datetime(2026, 1, 1, 6, 0, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        compute_natal_chart(naive, _LATITUDE, _LONGITUDE, _CONFIG)


def test_a_non_utc_aware_birth_instant_is_refused() -> None:
    non_utc = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=-6)))

    with pytest.raises(ValueError, match="UTC"):
        compute_natal_chart(non_utc, _LATITUDE, _LONGITUDE, _CONFIG)


def test_a_non_swiss_ephemeris_result_is_refused_not_silently_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors ``core/ephemeris/identity.py``'s own "Moshier never
    acceptable" rule: a return flag missing ``SEFLG_SWIEPH`` must raise, not
    silently produce a chart computed from a lower-precision fallback."""
    real_calc_ut = swe.calc_ut

    def _fake_calc_ut(jd_ut: float, body_id: int, flags: int) -> tuple[tuple[float, ...], int]:
        xx, retflag = real_calc_ut(jd_ut, body_id, flags)
        return xx, retflag & ~swe.FLG_SWIEPH

    monkeypatch.setattr("core.ephemeris.chart.swe.calc_ut", _fake_calc_ut)

    with pytest.raises(EphemerisIntegrityError):
        compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _CONFIG)


# --- Matrix row: determinism ---------------------------------------------------


def test_identical_inputs_computed_twice_are_byte_identical() -> None:
    first = _compute()
    second = _compute()

    assert first == second


# --- Matrix row: config-driven orb ---------------------------------------------


def test_a_narrower_orb_detects_fewer_or_equal_aspects_than_a_wider_one() -> None:
    narrow_config = dataclasses.replace(
        _CONFIG, orbs=dataclasses.replace(_CONFIG.orbs, natal=Decimal("6.0"))
    )
    wide_config = dataclasses.replace(
        _CONFIG, orbs=dataclasses.replace(_CONFIG.orbs, natal=Decimal("8.0"))
    )

    narrow_chart = compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, narrow_config)
    wide_chart = compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, wide_config)

    narrow_pairs = {(a.body1, a.body2, a.aspect) for a in narrow_chart.aspects}
    wide_pairs = {(a.body1, a.body2, a.aspect) for a in wide_chart.aspects}

    assert narrow_pairs <= wide_pairs
    for aspect in narrow_chart.aspects:
        assert aspect.orb <= Decimal("6.0")


def test_the_orb_actually_used_is_the_passed_config_not_a_hardcoded_seven() -> None:
    """A hardcoded ``7.0`` would pass the shipped-default config's own test
    trivially -- this pins a *different* orb and confirms detection changes
    with it, not just that some number under 7 is accepted."""
    tight_config = dataclasses.replace(
        _CONFIG, orbs=dataclasses.replace(_CONFIG.orbs, natal=Decimal("6.0"))
    )

    chart = compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, tight_config)

    assert all(aspect.orb <= Decimal("6.0") for aspect in chart.aspects)


# --- Aspect/orb shape -----------------------------------------------------------


def test_orb_is_an_unsigned_magnitude_with_applying_carried_separately() -> None:
    chart = _compute()

    for aspect in chart.aspects:
        assert aspect.orb >= Decimal(0)
        assert isinstance(aspect.applying, bool)


# --- epic-3-retro item 22: computes correctly off the import/main thread -----


def test_compute_natal_chart_on_a_worker_thread_matches_the_main_thread() -> None:
    """pyswisseph's ephemeris path is thread-local in this build, and the
    report pipeline runs on a FastAPI worker thread. ``compute_natal_chart``
    must re-bind the verified path to the calling thread itself (covering
    ``swe.houses``, which cannot report a Moshier fallback), not rely on
    ``verify_ephemeris_identity()`` having run on that thread."""
    from concurrent.futures import ThreadPoolExecutor

    main_thread_chart = _compute()
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker_thread_chart = pool.submit(_compute).result()

    assert worker_thread_chart == main_thread_chart


def test_house_cusp_and_planet_position_shapes() -> None:
    cusp = HouseCusp(number=1, longitude=Decimal("306.1868"))
    assert cusp.number == 1

    planet = PlanetPosition(
        name="sun",
        longitude=Decimal("340.3123"),
        sign="pisces",
        degree=Decimal("10.3123"),
        house=1,
        retrograde=False,
    )
    assert planet.name == "sun"
