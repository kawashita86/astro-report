"""``find_ingresses()`` -- one test per row of the story's I/O & Edge-Case
Matrix, plus the properties those rows imply: determinism, and the two
``Always`` bullets a synthetic-body integration test alone doesn't cover
(unsupported body names, malformed UTC boundaries).

Mirrors ``tests/test_stations.py``'s own structure and synthetic-ephemeris
technique almost exactly (Story 3.3's own Code Map names ``test_stations.py``
as this one's precedent): most rows need precise control over a transiting
body's longitude as a function of time (a straight-line approach for a
single crossing, a sine wave for a there-and-back pair) that real ephemeris
data cannot be relied on to produce inside a short, fast-running test. A
synthetic ``swe.calc_ut`` is monkeypatched at
``core.ephemeris.positions.swe.calc_ut`` (where ``_calc_body`` -- shared
with natal computation and ``core/transits/aspects.py``/``core/transits/stations.py``
-- actually calls it), exactly like those two modules' own test suites. Real
ephemeris conformance (the month fixture's bracketed Ingress) is exercised
end to end in ``tests/test_conformance.py``, not duplicated here.

A synthetic ``NatalChart`` is built by hand with twelve house cusps evenly
spaced 30 degrees apart -- ``find_ingresses()`` only ever reads
``natal_chart.houses``, so a minimal chart exercises it exactly as fully as
a real Placidus one. Each test's synthetic body longitude stays well clear
of every cusp except the one under test (see ``_minimal_natal_chart``'s own
docstring), so a crossing of an unrelated cusp is never a confound.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import swisseph as swe

from core.ephemeris.identity import verify_ephemeris_identity
from core.transits.ingresses import find_ingresses
from core.types.chart import HouseCusp, NatalChart
from core.types.computation import Bodies, ComputationConfig
from core.types.transits import Ingress
from shell.computation import load_computation_config

verify_ephemeris_identity()
_BASE_CONFIG = load_computation_config()

# The autouse fixture re-pinning the real vendored ephemeris before every
# test in the session lives in tests/conftest.py (shared across modules).

_MONTH_START = datetime(2024, 6, 1, tzinfo=UTC)
_MONTH_END = datetime(2024, 7, 1, tzinfo=UTC)

#: Real Julian Day (via the un-mocked ``swe.utc_to_jd``) of ``_MONTH_START``
#: -- Julian Day increases by exactly 1.0 per UTC day, so every synthetic
#: formula below is expressed simply in "days since this reference," exactly
#: like ``tests/test_stations.py``'s own reference point.
_MONTH_START_JD = swe.utc_to_jd(2024, 6, 1, 0, 0, 0.0, swe.GREG_CAL)[1]

#: House 4's cusp -- the one cusp under test in most rows below. The other
#: eleven cusps sit 30 degrees apart around it (house 3's cusp at 70, house
#: 5's at 130), well clear of every synthetic body path used below (each
#: kept strictly inside (70, 130)) so no unrelated cusp is ever crossed.
_TARGET_HOUSE_NUMBER = 4
_TARGET_CUSP_LONGITUDE = Decimal("100.0000")
_PREVIOUS_HOUSE_NUMBER = 3
_NEXT_HOUSE_NUMBER = 5


def _minimal_natal_chart() -> NatalChart:
    """Twelve house cusps, evenly spaced 30 degrees apart, house 4's cusp
    fixed at ``_TARGET_CUSP_LONGITUDE`` -- see the module docstring."""
    houses = tuple(
        HouseCusp(number=n, longitude=Decimal(str((n - 1) * 30)) + Decimal("10.0000"))
        for n in range(1, 13)
    )
    return NatalChart(
        ascendant=Decimal("15.0000"),
        midheaven=Decimal("225.0000"),
        planets=(),
        houses=houses,
        aspects=(),
    )


def _config_with_single_transiting_body(body: str) -> ComputationConfig:
    return dataclasses.replace(_BASE_CONFIG, bodies=Bodies(fast=(body,), slow=()))


def _wrap_degrees(value: float) -> float:
    return value % 360.0


def _patch_calc_ut(monkeypatch: pytest.MonkeyPatch, longitude_fn) -> None:
    """Replace ``swe.calc_ut`` (as seen from ``core.ephemeris.positions``,
    where ``_calc_body`` actually calls it) with a synthetic body whose
    longitude is ``longitude_fn(days_since_month_start)``. Speed is
    irrelevant to ``find_ingresses()`` (it never reads it, unlike
    ``stations.py``), so a fixed placeholder is returned -- mirrors
    ``tests/test_transit_aspects.py``'s own ``_patch_calc_ut``."""

    def fake_calc_ut(jd_ut: float, body_id: int, flags: int) -> tuple[tuple[float, ...], int]:
        days = jd_ut - _MONTH_START_JD
        longitude = _wrap_degrees(longitude_fn(days))
        xx = (longitude, 0.0, 1.0, 0.0, 0.0, 0.0)
        retflag = swe.FLG_SWIEPH | swe.FLG_SPEED
        return xx, retflag

    monkeypatch.setattr("core.ephemeris.positions.swe.calc_ut", fake_calc_ut)


def _ingresses_of(records: tuple[Ingress, ...], body: str) -> list[Ingress]:
    return [record for record in records if record.body == body]


# --- Matrix row: direct crossing into the next house ----------------------------


def test_a_direct_crossing_enters_the_cusps_own_house(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("mercury")

    # Direct motion crossing house 4's cusp (100 degrees) at day 15, well
    # clear of both month boundaries and of the neighboring cusps at 70/130.
    crossing_day = 15.0

    def longitude_fn(days: float) -> float:
        return float(_TARGET_CUSP_LONGITUDE) + 1.0 * (days - crossing_day)

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_ingresses(chart, _MONTH_START, _MONTH_END, config)
    ingresses = _ingresses_of(records, "mercury")

    assert len(ingresses) == 1
    ingress = ingresses[0]
    assert ingress.house_departed == _PREVIOUS_HOUSE_NUMBER
    assert ingress.house_entered == _TARGET_HOUSE_NUMBER
    assert _MONTH_START < ingress.crossed_at < _MONTH_END

    crossed_day = (ingress.crossed_at - _MONTH_START).total_seconds() / 86400.0
    assert crossed_day == pytest.approx(crossing_day, abs=0.01)


# --- Matrix row: retrograde crossing back into the previous house ---------------


def test_a_retrograde_crossing_re_enters_the_previous_house(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("mercury")

    # Retrograde (decreasing longitude) motion crossing house 4's cusp
    # (100 degrees) at day 12, well clear of both month boundaries.
    crossing_day = 12.0

    def longitude_fn(days: float) -> float:
        return float(_TARGET_CUSP_LONGITUDE) - 1.0 * (days - crossing_day)

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_ingresses(chart, _MONTH_START, _MONTH_END, config)
    ingresses = _ingresses_of(records, "mercury")

    assert len(ingresses) == 1
    ingress = ingresses[0]
    assert ingress.house_departed == _TARGET_HOUSE_NUMBER
    assert ingress.house_entered == _PREVIOUS_HOUSE_NUMBER
    assert _MONTH_START < ingress.crossed_at < _MONTH_END

    crossed_day = (ingress.crossed_at - _MONTH_START).total_seconds() / 86400.0
    assert crossed_day == pytest.approx(crossing_day, abs=0.01)


# --- Matrix row: house-1 wraparound (previous house is house 12) ----------------


def test_a_direct_crossing_into_house_1_departs_house_12(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """House numbering wraps: the house before house 1 is house 12, not
    house 0 -- exercised separately since ``_TARGET_HOUSE_NUMBER``'s own
    fixture (house 4) never touches this wraparound."""
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("mercury")

    house_1_cusp = float(chart.houses[0].longitude)
    crossing_day = 15.0

    def longitude_fn(days: float) -> float:
        return house_1_cusp + 1.0 * (days - crossing_day)

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_ingresses(chart, _MONTH_START, _MONTH_END, config)
    ingresses = _ingresses_of(records, "mercury")

    assert len(ingresses) == 1
    matches = [ingress for ingress in ingresses if ingress.house_entered == 1]
    assert len(matches) == 1
    assert matches[0].house_departed == 12


# --- Matrix row: same cusp crossed twice in one month (there and back) ----------


def test_a_cusp_crossed_twice_produces_two_distinct_never_merged_ingresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("mars")

    # A sine wave centered on house 4's cusp (100 degrees), amplitude 10
    # degrees (well clear of the neighboring cusps at 70/130) with a period
    # (30 days) equal to the month's own width and a 5-day phase offset:
    # exactly two position zero-crossings (days 5 and 20) fall inside the
    # month, with the adjacent ones on either side (days -25 and 35) safely
    # outside it -- unlike tests/test_stations.py's own two-turns row (which
    # locates *speed* zero-crossings, spaced by a quarter period), a
    # *position* sine wave's own zero-crossings are spaced by half its
    # period, so the period/phase here are chosen independently to land
    # exactly two inside [0, 30).
    amplitude = 10.0
    period_days = 30.0
    phase_days = 5.0

    def longitude_fn(days: float) -> float:
        return float(_TARGET_CUSP_LONGITUDE) + amplitude * math.sin(
            2 * math.pi * (days - phase_days) / period_days
        )

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_ingresses(chart, _MONTH_START, _MONTH_END, config)
    ingresses = _ingresses_of(records, "mars")

    assert len(ingresses) == 2
    ordered = sorted(ingresses, key=lambda ingress: ingress.crossed_at)
    first, second = ordered
    assert first.crossed_at != second.crossed_at
    assert first.house_departed == _PREVIOUS_HOUSE_NUMBER
    assert first.house_entered == _TARGET_HOUSE_NUMBER
    assert second.house_departed == _TARGET_HOUSE_NUMBER
    assert second.house_entered == _PREVIOUS_HOUSE_NUMBER


# --- Half-open interval: a crossing landing exactly on month_end_utc ------------


def test_a_crossing_landing_exactly_on_month_end_utc_is_never_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: ``_build_grid()`` appends ``month_end_utc`` itself as a
    final probe point (to catch a crossing hiding in the last partial grid
    step), but the analyzed interval is half-open,
    ``[month_start_utc, month_end_utc)`` -- ``month_end_utc`` itself is
    never inside it. A synthetic body whose longitude sits exactly on the
    cusp only at that one excluded probe instant (never crossing it
    anywhere else) must never produce an Ingress -- mirrors
    ``tests/test_stations.py``'s own boundary regression test."""
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("mercury")

    month_end_jd = swe.utc_to_jd(2024, 7, 1, 0, 0, 0.0, swe.GREG_CAL)[1]
    cusp = float(_TARGET_CUSP_LONGITUDE)

    def fake_calc_ut(jd_ut: float, body_id: int, flags: int) -> tuple[tuple[float, ...], int]:
        # Constant offset from the cusp (always 5 degrees short of it)
        # everywhere, except exactly at the month-end probe instant, where
        # the longitude lands exactly on the cusp -- forcing
        # find_ingresses()'s exact-zero (``d1 == 0``) branch to fire with
        # ``t1 == month_end_utc``.
        longitude = cusp if jd_ut == month_end_jd else cusp - 5.0
        xx = (longitude, 0.0, 1.0, 0.0, 0.0, 0.0)
        retflag = swe.FLG_SWIEPH | swe.FLG_SPEED
        return xx, retflag

    monkeypatch.setattr("core.ephemeris.positions.swe.calc_ut", fake_calc_ut)

    records = find_ingresses(chart, _MONTH_START, _MONTH_END, config)

    for record in records:
        assert record.crossed_at < _MONTH_END, (
            f"Ingress reported at or past month_end_utc (half-open interval "
            f"violation): {record!r}"
        )
    assert _ingresses_of(records, "mercury") == [], (
        f"expected nothing recorded (never actually crosses inside the half-open "
        f"interval), got {records!r}"
    )


# --- Matrix row: no body crosses a given cusp all month --------------------------


def test_a_body_that_never_crosses_any_cusp_produces_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("venus")

    # Constant longitude, parked well clear of every cusp, all month.
    def longitude_fn(days: float) -> float:
        return 5.0

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_ingresses(chart, _MONTH_START, _MONTH_END, config)

    assert records == ()


# --- Determinism -----------------------------------------------------------------


def test_identical_inputs_computed_twice_are_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("mercury")

    def longitude_fn(days: float) -> float:
        return float(_TARGET_CUSP_LONGITUDE) + 1.0 * (days - 15.0)

    _patch_calc_ut(monkeypatch, longitude_fn)

    first = find_ingresses(chart, _MONTH_START, _MONTH_END, config)
    second = find_ingresses(chart, _MONTH_START, _MONTH_END, config)

    assert first == second


# --- Always: scope (configured bodies, no Moon) ----------------------------------


def test_scans_exactly_the_configured_bodies_and_never_the_moon() -> None:
    """Uses a real (short) window against a real-shaped chart -- an
    integration-shaped smoke test that the scan's scope matches the story's
    Always bullets, complementing the synthetic per-row tests above."""
    chart = _minimal_natal_chart()
    month_start = datetime(2022, 12, 1, tzinfo=UTC)
    month_end = datetime(2023, 1, 1, tzinfo=UTC)

    records = find_ingresses(chart, month_start, month_end, _BASE_CONFIG)

    configured_bodies = set(_BASE_CONFIG.bodies.fast) | set(_BASE_CONFIG.bodies.slow)
    assert records != ()
    for record in records:
        assert record.body in configured_bodies
        assert record.body != "moon"
        assert record.house_departed in range(1, 13)
        assert record.house_entered in range(1, 13)
        assert record.crossed_at.tzinfo is not None
        assert record.crossed_at.utcoffset() == timedelta(0)
        assert month_start <= record.crossed_at < month_end


def test_an_unsupported_body_name_is_refused() -> None:
    chart = _minimal_natal_chart()
    config = dataclasses.replace(_BASE_CONFIG, bodies=Bodies(fast=("moon",), slow=()))

    with pytest.raises(ValueError, match="not a body"):
        find_ingresses(chart, _MONTH_START, _MONTH_END, config)


# --- Always: half-open UTC interval validation ----------------------------------


def test_a_naive_month_boundary_is_refused() -> None:
    chart = _minimal_natal_chart()
    naive = datetime(2024, 6, 1)
    config = _config_with_single_transiting_body("mercury")

    with pytest.raises(ValueError, match="timezone-aware"):
        find_ingresses(chart, naive, _MONTH_END, config)


def test_a_month_start_not_before_month_end_is_refused() -> None:
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("mercury")

    with pytest.raises(ValueError, match="before"):
        find_ingresses(chart, _MONTH_END, _MONTH_START, config)


def test_a_month_start_equal_to_month_end_is_refused() -> None:
    """``_require_utc_interval``'s own ``start >= end`` check is meant to
    cover both the reversed-order case above and this exact-equality case
    -- exercised separately since an empty interval is a distinct edge from
    a reversed one."""
    chart = _minimal_natal_chart()
    config = _config_with_single_transiting_body("mercury")

    with pytest.raises(ValueError, match="before"):
        find_ingresses(chart, _MONTH_START, _MONTH_START, config)


# --- Frozen dataclass ------------------------------------------------------------


def test_ingress_is_frozen() -> None:
    ingress = Ingress(
        body="mercury",
        house_departed=3,
        house_entered=4,
        crossed_at=_MONTH_START,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ingress.house_entered = 5  # type: ignore[misc]
