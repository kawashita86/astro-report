"""``find_stations()`` -- one test per row of the story's I/O & Edge-Case
Matrix, plus the properties those rows imply: determinism, and the two
``Always`` bullets a synthetic-body integration test alone doesn't cover
(unsupported body names, malformed UTC boundaries).

Mirrors ``tests/test_transit_aspects.py``'s own structure and synthetic-
ephemeris technique almost exactly (Story 3.2's own Code Map names that file
as this one's precedent): most rows need precise control over a transiting
body's longitude as a function of time (a parabola for a single station, a
sine wave for two stations in one month) that real ephemeris data cannot be
relied on to produce inside a short, fast-running test. A synthetic
``swe.calc_ut`` is monkeypatched at ``core.ephemeris.positions.swe.calc_ut``
(where ``_calc_body`` -- shared with natal computation and
``core/transits/aspects.py`` -- actually calls it), with speed derived
numerically by the same tiny finite difference ``test_transit_aspects.py``
already uses. Real ephemeris conformance (the retrograde-station-month
fixture's bracketed Mercury station) is exercised end to end in
``tests/test_conformance.py``, not duplicated here.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import swisseph as swe

from core.ephemeris.identity import verify_ephemeris_identity
from core.transits.stations import find_stations
from core.types.computation import Bodies, ComputationConfig
from core.types.transits import StandingRetrograde, Station
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
#: like ``tests/test_transit_aspects.py``'s own reference point.
_MONTH_START_JD = swe.utc_to_jd(2024, 6, 1, 0, 0, 0.0, swe.GREG_CAL)[1]


def _config_with_single_transiting_body(body: str) -> ComputationConfig:
    return dataclasses.replace(_BASE_CONFIG, bodies=Bodies(fast=(body,), slow=()))


def _wrap_degrees(value: float) -> float:
    return value % 360.0


def _patch_calc_ut(monkeypatch: pytest.MonkeyPatch, longitude_fn) -> None:
    """Replace ``swe.calc_ut`` (as seen from ``core.ephemeris.positions``,
    where ``_calc_body`` calls it) with a synthetic body whose longitude is
    ``longitude_fn(days_since_month_start)``. Speed is derived numerically
    (a tiny finite difference) -- ``find_stations()`` reads this ``speed``
    value directly (it *is* the retrograde test), unlike
    ``find_transit_aspects()``, which never reads it -- mirrors
    ``tests/test_transit_aspects.py``'s own ``_patch_calc_ut``."""

    def fake_calc_ut(jd_ut: float, body_id: int, flags: int) -> tuple[tuple[float, ...], int]:
        days = jd_ut - _MONTH_START_JD
        longitude = _wrap_degrees(longitude_fn(days))
        epsilon = 1e-6
        speed = (_wrap_degrees(longitude_fn(days + epsilon)) - longitude + 540.0) % 360.0 - 180.0
        speed = speed / epsilon
        xx = (longitude, 0.0, 1.0, speed, 0.0, 0.0)
        retflag = swe.FLG_SWIEPH | swe.FLG_SPEED
        return xx, retflag

    monkeypatch.setattr("core.ephemeris.positions.swe.calc_ut", fake_calc_ut)


def _stations_of(
    records: tuple[Station | StandingRetrograde, ...], body: str
) -> list[Station]:
    return [record for record in records if isinstance(record, Station) and record.body == body]


def _standing_retrogrades_of(
    records: tuple[Station | StandingRetrograde, ...], body: str
) -> list[StandingRetrograde]:
    return [
        record
        for record in records
        if isinstance(record, StandingRetrograde) and record.body == body
    ]


# --- Matrix row: direct-to-retrograde turn inside the month ---------------------


def test_a_direct_to_retrograde_turn_is_recorded_with_the_bisected_instant_and_longitude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config_with_single_transiting_body("mercury")

    # An upward parabola peaking (speed crossing from + to -) at day 15,
    # well clear of both month boundaries.
    peak_longitude = 100.0
    peak_day = 15.0
    curvature = 0.05

    def longitude_fn(days: float) -> float:
        return peak_longitude - curvature * (days - peak_day) ** 2

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_stations(_MONTH_START, _MONTH_END, config)
    stations = _stations_of(records, "mercury")

    assert len(stations) == 1
    station = stations[0]
    assert station.direction == "retrograde"
    assert station.body == "mercury"
    assert _MONTH_START < station.station_at < _MONTH_END

    station_day = (station.station_at - _MONTH_START).total_seconds() / 86400.0
    assert station_day == pytest.approx(peak_day, abs=0.01)
    assert station.longitude == Decimal(str(_wrap_degrees(longitude_fn(station_day)))).quantize(
        Decimal("0.0001")
    )

    # No standing condition recorded alongside a located turn.
    assert _standing_retrogrades_of(records, "mercury") == []


# --- Matrix row: retrograde-to-direct turn inside the month ---------------------


def test_a_retrograde_to_direct_turn_is_recorded_with_direction_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config_with_single_transiting_body("mercury")

    # A downward parabola bottoming out (speed crossing from - to +) at day
    # 10, well clear of both month boundaries.
    trough_longitude = 100.0
    trough_day = 10.0
    curvature = 0.05

    def longitude_fn(days: float) -> float:
        return trough_longitude + curvature * (days - trough_day) ** 2

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_stations(_MONTH_START, _MONTH_END, config)
    stations = _stations_of(records, "mercury")

    assert len(stations) == 1
    station = stations[0]
    assert station.direction == "direct"
    assert _MONTH_START < station.station_at < _MONTH_END

    station_day = (station.station_at - _MONTH_START).total_seconds() / 86400.0
    assert station_day == pytest.approx(trough_day, abs=0.01)


# --- Matrix row: retrograde the whole month, no turn inside it ------------------


def test_a_body_retrograde_the_whole_month_is_recorded_as_a_standing_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config_with_single_transiting_body("saturn")

    # Constant negative speed throughout -- never a sign change.
    def longitude_fn(days: float) -> float:
        return 200.0 - 0.3 * days

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_stations(_MONTH_START, _MONTH_END, config)

    assert _stations_of(records, "saturn") == []
    standing = _standing_retrogrades_of(records, "saturn")
    assert len(standing) == 1
    assert standing[0] == StandingRetrograde(
        body="saturn",
        retrograde_start_utc=_MONTH_START,
        retrograde_end_utc=_MONTH_END,
    )


# --- Matrix row: direct the whole month -----------------------------------------


def test_a_body_direct_the_whole_month_is_not_recorded_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config_with_single_transiting_body("venus")

    # Constant positive speed throughout -- never a sign change.
    def longitude_fn(days: float) -> float:
        return 50.0 + 1.2 * days

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_stations(_MONTH_START, _MONTH_END, config)

    assert records == ()


# --- Matrix row: two turns for the same body in one month -----------------------


def test_two_turns_for_the_same_body_produce_two_distinct_never_merged_stations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config_with_single_transiting_body("mars")

    # A sine wave whose period (24 days) is deliberately wider than the
    # 30-day month: exactly two zero-derivative crossings fall inside it --
    # a peak (day 10, speed + to -) and a trough (day 22, speed - to +) --
    # with the adjacent crossings on either side (days -2 and 34) safely
    # outside the month, unlike a period that evenly divides the month
    # width (which would place a third crossing exactly on the boundary).
    amplitude = 10.0
    period_days = 24.0
    phase_days = 4.0

    def longitude_fn(days: float) -> float:
        return 100.0 + amplitude * math.sin(2 * math.pi * (days - phase_days) / period_days)

    _patch_calc_ut(monkeypatch, longitude_fn)

    records = find_stations(_MONTH_START, _MONTH_END, config)
    stations = _stations_of(records, "mars")

    assert len(stations) == 2
    ordered = sorted(stations, key=lambda station: station.station_at)
    first, second = ordered

    first_day = (first.station_at - _MONTH_START).total_seconds() / 86400.0
    second_day = (second.station_at - _MONTH_START).total_seconds() / 86400.0
    assert first_day == pytest.approx(10.0, abs=0.01)
    assert second_day == pytest.approx(22.0, abs=0.01)
    assert first.direction == "retrograde"
    assert second.direction == "direct"
    assert first.station_at != second.station_at

    # Never merged: no standing condition recorded when real turns exist.
    assert _standing_retrogrades_of(records, "mars") == []


# --- Half-open interval: a sign change landing exactly on month_end_utc ---------


def test_a_sign_change_landing_exactly_on_month_end_utc_is_never_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: ``_build_grid()`` appends ``month_end_utc`` itself as a
    final probe point (to catch a turn hiding in the last partial grid
    step), but the analyzed interval is half-open,
    ``[month_start_utc, month_end_utc)`` -- ``month_end_utc`` itself is
    never inside it. A synthetic body whose speed is exactly zero only at
    that one excluded probe instant (constant positive/direct everywhere
    else) must never produce a Station -- and, since the sign never
    actually flips *inside* the half-open interval, must not be recorded as
    a standing condition either (it is positive throughout, i.e. direct the
    whole month)."""
    config = _config_with_single_transiting_body("mercury")

    month_end_jd = swe.utc_to_jd(2024, 7, 1, 0, 0, 0.0, swe.GREG_CAL)[1]

    def fake_calc_ut(jd_ut: float, body_id: int, flags: int) -> tuple[tuple[float, ...], int]:
        # Constant positive (direct) speed everywhere, except exactly at the
        # month-end probe instant, where speed is exactly zero -- forcing
        # find_stations()'s exact-zero (``s1 == 0``) branch to fire with
        # ``t1 == month_end_utc``.
        speed = 0.0 if jd_ut == month_end_jd else 0.5
        days = jd_ut - _MONTH_START_JD
        longitude = _wrap_degrees(50.0 + 0.5 * days)
        xx = (longitude, 0.0, 1.0, speed, 0.0, 0.0)
        retflag = swe.FLG_SWIEPH | swe.FLG_SPEED
        return xx, retflag

    monkeypatch.setattr("core.ephemeris.positions.swe.calc_ut", fake_calc_ut)

    records = find_stations(_MONTH_START, _MONTH_END, config)

    for record in records:
        if isinstance(record, Station):
            assert record.station_at < _MONTH_END, (
                f"Station reported at or past month_end_utc (half-open interval "
                f"violation): {record!r}"
            )
    assert records == (), (
        f"expected nothing recorded (direct the whole half-open interval), got {records!r}"
    )


# --- Determinism -----------------------------------------------------------------


def test_identical_inputs_computed_twice_are_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config_with_single_transiting_body("mercury")

    def longitude_fn(days: float) -> float:
        return 100.0 - 0.05 * (days - 15.0) ** 2

    _patch_calc_ut(monkeypatch, longitude_fn)

    first = find_stations(_MONTH_START, _MONTH_END, config)
    second = find_stations(_MONTH_START, _MONTH_END, config)

    assert first == second


# --- Always: scope (configured bodies, no Moon) ----------------------------------


def test_scans_exactly_the_configured_bodies_and_never_the_moon() -> None:
    """Uses a real (short) window -- an integration-shaped smoke test that
    the scan's scope matches the story's Always bullets, complementing the
    synthetic per-row tests above."""
    month_start = datetime(2022, 12, 1, tzinfo=UTC)
    month_end = datetime(2023, 1, 1, tzinfo=UTC)

    records = find_stations(month_start, month_end, _BASE_CONFIG)

    configured_bodies = set(_BASE_CONFIG.bodies.fast) | set(_BASE_CONFIG.bodies.slow)
    assert records != ()
    for record in records:
        assert record.body in configured_bodies
        assert record.body != "moon"
        if isinstance(record, Station):
            assert record.direction in ("retrograde", "direct")
            assert record.station_at.tzinfo is not None
            assert record.station_at.utcoffset() == timedelta(0)
        else:
            assert record.retrograde_start_utc >= month_start
            assert record.retrograde_end_utc <= month_end


def test_an_unsupported_body_name_is_refused() -> None:
    config = dataclasses.replace(_BASE_CONFIG, bodies=Bodies(fast=("moon",), slow=()))

    with pytest.raises(ValueError, match="not a body"):
        find_stations(_MONTH_START, _MONTH_END, config)


# --- Always: half-open UTC interval validation ----------------------------------


def test_a_naive_month_boundary_is_refused() -> None:
    naive = datetime(2024, 6, 1)
    config = _config_with_single_transiting_body("mercury")

    with pytest.raises(ValueError, match="timezone-aware"):
        find_stations(naive, _MONTH_END, config)


def test_a_month_start_not_before_month_end_is_refused() -> None:
    config = _config_with_single_transiting_body("mercury")

    with pytest.raises(ValueError, match="before"):
        find_stations(_MONTH_END, _MONTH_START, config)


def test_a_month_start_equal_to_month_end_is_refused() -> None:
    """``_require_utc_interval``'s own ``start >= end`` check is meant to
    cover both the reversed-order case above and this exact-equality case
    -- exercised separately since an empty interval is a distinct edge from
    a reversed one."""
    config = _config_with_single_transiting_body("mercury")

    with pytest.raises(ValueError, match="before"):
        find_stations(_MONTH_START, _MONTH_START, config)


# --- Frozen dataclasses ------------------------------------------------------------


def test_station_is_frozen() -> None:
    station = Station(
        body="mercury",
        direction="retrograde",
        station_at=_MONTH_START,
        longitude=Decimal("100.0000"),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        station.direction = "direct"  # type: ignore[misc]


def test_standing_retrograde_is_frozen() -> None:
    standing = StandingRetrograde(
        body="saturn",
        retrograde_start_utc=_MONTH_START,
        retrograde_end_utc=_MONTH_END,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        standing.body = "mars"  # type: ignore[misc]
