"""``find_lunations()`` -- one test per row of the story's I/O & Edge-Case
Matrix, plus the properties those rows imply: determinism, and the two
``Always`` bullets a synthetic-body integration test alone doesn't cover
(malformed UTC boundaries, and a real-ephemeris smoke test of the whole
scan).

Mirrors ``tests/test_ingresses.py``'s own structure and synthetic-ephemeris
technique almost exactly (Story 3.4's own Code Map names that file as this
one's precedent, with one adaptation): ``_patch_calc_ut`` here drives Sun and
Moon longitudes *independently* by ``body_id`` (this story needs two
synthetic bodies moving at different, controllable rates, not one) rather
than a single synthetic transiting body against a fixed cusp. A synthetic
``swe.calc_ut`` is monkeypatched at ``core.ephemeris.positions.swe.calc_ut``
(where ``_calc_body`` -- shared with natal computation and every other
``core/transits/`` module -- actually calls it). Real ephemeris conformance
(the ``two-lunations-month``/``no-lunations-month`` fixtures) is exercised
end to end in ``tests/test_conformance.py``, not duplicated here.

A synthetic ``NatalChart`` is built by hand with twelve house cusps evenly
spaced 30 degrees apart, starting at 10 degrees -- identical shape to
``tests/test_ingresses.py``'s own ``_minimal_natal_chart`` -- so each
crossing's expected natal house is a plain, hand-computable fact about the
Moon's longitude at that instant.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import swisseph as swe

from core.ephemeris.identity import verify_ephemeris_identity
from core.transits.lunations import find_lunations
from core.types.chart import HouseCusp, NatalChart
from core.types.transits import Lunation

verify_ephemeris_identity()

# The autouse fixture re-pinning the real vendored ephemeris before every
# test in the session lives in tests/conftest.py (shared across modules).

_MONTH_START = datetime(2024, 6, 1, tzinfo=UTC)
_MONTH_END = datetime(2024, 7, 1, tzinfo=UTC)

#: Real Julian Day (via the un-mocked ``swe.utc_to_jd``) of ``_MONTH_START``
#: -- Julian Day increases by exactly 1.0 per UTC day, so every synthetic
#: formula below is expressed simply in "days since this reference," exactly
#: like ``tests/test_ingresses.py``'s own reference point.
_MONTH_START_JD = swe.utc_to_jd(2024, 6, 1, 0, 0, 0.0, swe.GREG_CAL)[1]

#: Constant Sun longitude used by most rows below -- Delta-lambda's exact
#: value then depends only on the synthetic Moon longitude function, keeping
#: each row's arithmetic simple. House cusps sit 30 degrees apart starting
#: at 10 degrees (mirrors ``tests/test_ingresses.py``'s own
#: ``_minimal_natal_chart``): house ``n`` spans
#: ``[cusp_n, cusp_{n+1})`` -- house 7's cusp is 190, house 8's is 220, so a
#: Moon longitude of 200 degrees (Sun's own longitude, i.e. a new-moon
#: crossing) falls in house 7 (``190 <= 200 < 220``); house 1's cusp is 10,
#: house 2's is 40, so 20 degrees (Sun's longitude + 180, i.e. a full-moon
#: crossing) falls in house 1 (``10 <= 20 < 40``).
_SUN_LONGITUDE = 200.0
_NEW_MOON_CROSSING_HOUSE = 7
_FULL_MOON_CROSSING_HOUSE = 1

#: Degrees/day used by the linear-crossing rows below -- deliberately small
#: (unlike the Moon's real ~13 degree/day sweep) so Delta-lambda moves only
#: a little across the whole month and never wanders near the *other*
#: target (0 vs 180 degrees), which a faster rate could spuriously cross
#: too.
_SLOW_RATE = 1.0


def _minimal_natal_chart() -> NatalChart:
    """Twelve house cusps, evenly spaced 30 degrees apart -- see the module
    docstring."""
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


def _wrap_degrees(value: float) -> float:
    return value % 360.0


def _patch_calc_ut(monkeypatch: pytest.MonkeyPatch, sun_longitude_fn, moon_longitude_fn) -> None:
    """Replace ``swe.calc_ut`` (as seen from ``core.ephemeris.positions``,
    where ``_calc_body`` actually calls it) with two independent synthetic
    bodies: the Sun's longitude is ``sun_longitude_fn(days_since_month_start)``,
    the Moon's is ``moon_longitude_fn(days_since_month_start)``. Speed is
    irrelevant to ``find_lunations()`` (it never reads it, unlike
    ``stations.py``), so a fixed placeholder is returned -- mirrors
    ``tests/test_ingresses.py``'s own ``_patch_calc_ut``, adapted for two
    independently driven bodies instead of one."""

    def fake_calc_ut(jd_ut: float, body_id: int, flags: int) -> tuple[tuple[float, ...], int]:
        days = jd_ut - _MONTH_START_JD
        if body_id == swe.SUN:
            longitude = _wrap_degrees(sun_longitude_fn(days))
        elif body_id == swe.MOON:
            longitude = _wrap_degrees(moon_longitude_fn(days))
        else:
            raise AssertionError(
                f"find_lunations() only ever calls _calc_body for the Sun/Moon; got "
                f"body_id {body_id!r}"
            )
        xx = (longitude, 0.0, 1.0, 0.0, 0.0, 0.0)
        retflag = swe.FLG_SWIEPH | swe.FLG_SPEED
        return xx, retflag

    monkeypatch.setattr("core.ephemeris.positions.swe.calc_ut", fake_calc_ut)


def _of_kind(records: tuple[Lunation, ...], kind: str) -> list[Lunation]:
    return [record for record in records if record.kind == kind]


# --- Matrix row: Delta-lambda crosses 0 degrees (new moon) ----------------------


def test_a_delta_lambda_crossing_of_zero_degrees_is_recorded_as_a_new_moon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()

    # Delta-lambda = moon - sun crosses 0 degrees at day 15, well clear of
    # both month boundaries and (thanks to _SLOW_RATE) never near the
    # full-moon target (180 degrees) either.
    crossing_day = 15.0

    def sun_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE

    def moon_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE + _SLOW_RATE * (days - crossing_day)

    _patch_calc_ut(monkeypatch, sun_longitude_fn, moon_longitude_fn)

    records = find_lunations(chart, _MONTH_START, _MONTH_END)
    new_moons = _of_kind(records, "new_moon")

    assert len(new_moons) == 1
    lunation = new_moons[0]
    assert _MONTH_START < lunation.occurred_at < _MONTH_END
    assert lunation.natal_house == _NEW_MOON_CROSSING_HOUSE

    crossed_day = (lunation.occurred_at - _MONTH_START).total_seconds() / 86400.0
    assert crossed_day == pytest.approx(crossing_day, abs=0.01)
    assert lunation.longitude == Decimal(str(_wrap_degrees(_SUN_LONGITUDE))).quantize(
        Decimal("0.0001")
    )

    # No full moon recorded from this scenario.
    assert _of_kind(records, "full_moon") == []


# --- Precision: occurred_at is never truncated to a whole minute ----------------


def test_occurred_at_retains_sub_minute_precision_for_a_non_trivial_crossing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for the precision-truncation discussion documented in
    ``tests/test_conformance.py``'s ``_lunations_for_month_fixture`` docstring
    (real bisected instants land ~38-40 seconds past the published minute):
    this module's own scan must never round/truncate ``occurred_at`` to
    whole-minute (or whole-second) precision.

    ``crossing_day`` is deliberately a fractional day (0.271 of a day past
    day 9, i.e. 06:30:14.4 UTC) rather than a round number like the other
    rows' ``15.0``/``10.0`` -- a round crossing day would land exactly on
    midnight (second/microsecond both trivially zero) and prove nothing
    about truncation. The bisected instant is only asserted to land within
    the same day (``abs=0.01`` on the day-fraction, matching every other
    row's tolerance in this module) rather than pinned to the second: the
    Sun/Moon longitudes ``_calc_body`` returns are themselves quantized (see
    ``core/ephemeris/positions.py``'s ``QUANTUM``), so the bisected crossing
    is only ever exact up to that quantization step, not to arbitrary
    precision -- the same reason the real-ephemeris fixtures land ~38-40
    seconds past the published minute rather than exactly on it.
    """
    chart = _minimal_natal_chart()

    crossing_day = 9.271

    def sun_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE

    def moon_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE + _SLOW_RATE * (days - crossing_day)

    _patch_calc_ut(monkeypatch, sun_longitude_fn, moon_longitude_fn)

    records = find_lunations(chart, _MONTH_START, _MONTH_END)
    new_moons = _of_kind(records, "new_moon")

    assert len(new_moons) == 1
    lunation = new_moons[0]

    crossed_day = (lunation.occurred_at - _MONTH_START).total_seconds() / 86400.0
    assert crossed_day == pytest.approx(crossing_day, abs=0.01)
    assert lunation.occurred_at.second != 0 or lunation.occurred_at.microsecond != 0, (
        f"occurred_at {lunation.occurred_at!r} landed exactly on a whole minute -- "
        f"either crossing_day was accidentally round, or the scan truncated precision"
    )


# --- Matrix row: Delta-lambda crosses 180 degrees (full moon) -------------------


def test_a_delta_lambda_crossing_of_180_degrees_is_recorded_as_a_full_moon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()

    # Delta-lambda crosses 180 degrees at day 10, well clear of both month
    # boundaries and (thanks to _SLOW_RATE) never near the new-moon target
    # (0/360 degrees) either.
    crossing_day = 10.0

    def sun_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE

    def moon_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE + 180.0 + _SLOW_RATE * (days - crossing_day)

    _patch_calc_ut(monkeypatch, sun_longitude_fn, moon_longitude_fn)

    records = find_lunations(chart, _MONTH_START, _MONTH_END)
    full_moons = _of_kind(records, "full_moon")

    assert len(full_moons) == 1
    lunation = full_moons[0]
    assert _MONTH_START < lunation.occurred_at < _MONTH_END
    assert lunation.natal_house == _FULL_MOON_CROSSING_HOUSE

    crossed_day = (lunation.occurred_at - _MONTH_START).total_seconds() / 86400.0
    assert crossed_day == pytest.approx(crossing_day, abs=0.01)

    # No new moon recorded from this scenario.
    assert _of_kind(records, "new_moon") == []


# --- Antipodal-wrap guard: a fast crossing near the *other* target's location ---
# --- must never misfire, while the real crossing at the intended target must ---
# --- still be found. -------------------------------------------------------------


def test_the_antipodal_wrap_guard_suppresses_a_spurious_crossing_at_the_other_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the ``abs(d1 - d0) < HALF_CIRCLE`` guard documented in
    both ``core/transits/lunations.py``'s module docstring and its inline
    comment at the sign-change check: without it, scanning target 0 degrees
    (new moon) would misfire at the true full-moon instant (where the
    wrapped signed offset from 0 jumps +180 to -180 between two samples),
    and vice versa for target 180 degrees (full moon) at the true new-moon
    instant.

    Unlike every other row in this module, ``_FAST_RATE`` here is
    deliberately much faster than ``_SLOW_RATE`` -- fast enough that
    Delta-lambda actually reaches and passes through 180 degrees (the point
    antipodal to the new-moon target, and simultaneously the full-moon
    target's own location) within the month, and specifically within a
    single ``_GRID_STEP`` (6 hours): at 10 degrees/day, Delta-lambda moves
    2.5 degrees per 6-hour grid step, so the two grid samples bracketing day
    22.1 (days 22.0 and 22.25) land at 178.0 and 180.5 degrees -- straddling
    180 within that one step, exactly the shape the guard exists to catch.
    ``_FAST_RATE`` is deliberately kept below 12 degrees/day (360 degrees /
    30-day month) so Delta-lambda sweeps under one full circle across the
    whole month -- fast enough to reach both targets, but not so fast it
    wraps back around and produces a second, genuine crossing of either one.

    ``crossing_day`` (4.1) and the antipodal offset (180 / 10 deg/day = 18
    days, landing at day 22.1) are both deliberately non-multiples of the
    0.25-day grid step, so neither crossing lands exactly on a sampled grid
    instant.
    """
    chart = _minimal_natal_chart()

    crossing_day = 4.1
    _FAST_RATE = 10.0
    antipodal_day = crossing_day + (180.0 / _FAST_RATE)  # 22.1

    def sun_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE

    def moon_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE + _FAST_RATE * (days - crossing_day)

    _patch_calc_ut(monkeypatch, sun_longitude_fn, moon_longitude_fn)

    records = find_lunations(chart, _MONTH_START, _MONTH_END)
    new_moons = _of_kind(records, "new_moon")
    full_moons = _of_kind(records, "full_moon")

    # Exactly one new moon (the real crossing at day 4.1) -- the antipodal
    # wrap at day 22.1 must never produce a second, spurious new_moon entry.
    assert len(new_moons) == 1, f"expected exactly one new_moon, got {new_moons!r}"
    new_moon_day = (new_moons[0].occurred_at - _MONTH_START).total_seconds() / 86400.0
    assert new_moon_day == pytest.approx(crossing_day, abs=0.01)

    # Exactly one full moon (the real crossing at day 22.1) -- the antipodal
    # wrap at day 4.1 (target 180's own antipodal point is 0 degrees) must
    # never produce a spurious full_moon entry there either.
    assert len(full_moons) == 1, f"expected exactly one full_moon, got {full_moons!r}"
    full_moon_day = (full_moons[0].occurred_at - _MONTH_START).total_seconds() / 86400.0
    assert full_moon_day == pytest.approx(antipodal_day, abs=0.01)


# --- Both kinds in the same scan: no cross-contamination between targets --------


def test_a_new_moon_and_a_full_moon_in_the_same_month_are_both_found_without_cross_contamination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single steady, real-ish rate (close to the Moon's true ~12.19
    degree/day synodic rate) carries Delta-lambda through more than 180
    degrees of travel within one synthetic month -- crossing both targets,
    unlike every other row in this module, which isolates one kind at a
    time. Asserts exactly one ``new_moon`` and one ``full_moon`` are
    recorded, each attributed to the correct target (via both timing and
    longitude/natal-house), correctly ordered, and never duplicated or
    misclassified as the other kind.
    """
    chart = _minimal_natal_chart()

    new_moon_day = 8.0
    _REALISTIC_RATE = 12.19
    full_moon_day = new_moon_day + (180.0 / _REALISTIC_RATE)  # ~ day 22.77

    def sun_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE

    def moon_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE + _REALISTIC_RATE * (days - new_moon_day)

    _patch_calc_ut(monkeypatch, sun_longitude_fn, moon_longitude_fn)

    records = find_lunations(chart, _MONTH_START, _MONTH_END)
    new_moons = _of_kind(records, "new_moon")
    full_moons = _of_kind(records, "full_moon")

    assert len(new_moons) == 1, f"expected exactly one new_moon, got {new_moons!r}"
    assert len(full_moons) == 1, f"expected exactly one full_moon, got {full_moons!r}"

    new_moon = new_moons[0]
    full_moon = full_moons[0]

    # Correct chronological ordering, no swap between the two kinds.
    assert new_moon.occurred_at < full_moon.occurred_at

    new_moon_measured_day = (new_moon.occurred_at - _MONTH_START).total_seconds() / 86400.0
    full_moon_measured_day = (full_moon.occurred_at - _MONTH_START).total_seconds() / 86400.0
    assert new_moon_measured_day == pytest.approx(new_moon_day, abs=0.01)
    assert full_moon_measured_day == pytest.approx(full_moon_day, abs=0.01)

    # Each record's own longitude/house confirms it was attributed to the
    # right target, not merged or cross-contaminated with the other kind:
    # at the new moon, Moon longitude equals the Sun's (house 7); at the
    # full moon, it equals the Sun's + 180 (house 1) -- same fixed facts the
    # single-kind rows above rely on.
    assert new_moon.natal_house == _NEW_MOON_CROSSING_HOUSE
    assert full_moon.natal_house == _FULL_MOON_CROSSING_HOUSE

    # No duplicate/misclassified records of either kind beyond the one each.
    assert records == (new_moon, full_moon) or records == (full_moon, new_moon)


# --- Matrix row: two Lunations of one kind in a month ---------------------------


def test_two_lunations_of_one_kind_produce_two_distinct_never_merged_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()

    # A sine wave centered on Delta-lambda = 0 (new moon), amplitude 10
    # degrees (well clear of 180, the full-moon target) with a period (30
    # days) equal to the month's own width and a 5-day phase offset --
    # mirrors tests/test_ingresses.py's own two-crossing sine wave exactly:
    # position zero-crossings at days 5 and 20 fall inside the month, with
    # the adjacent ones on either side (days -25 and 35) safely outside it.
    amplitude = 10.0
    period_days = 30.0
    phase_days = 5.0

    def sun_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE

    def moon_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE + amplitude * math.sin(
            2 * math.pi * (days - phase_days) / period_days
        )

    _patch_calc_ut(monkeypatch, sun_longitude_fn, moon_longitude_fn)

    records = find_lunations(chart, _MONTH_START, _MONTH_END)
    new_moons = _of_kind(records, "new_moon")

    assert len(new_moons) == 2
    ordered = sorted(new_moons, key=lambda lunation: lunation.occurred_at)
    first, second = ordered
    assert first.occurred_at != second.occurred_at

    first_day = (first.occurred_at - _MONTH_START).total_seconds() / 86400.0
    second_day = (second.occurred_at - _MONTH_START).total_seconds() / 86400.0
    assert first_day == pytest.approx(5.0, abs=0.01)
    assert second_day == pytest.approx(20.0, abs=0.01)

    assert _of_kind(records, "full_moon") == []


# --- Matrix row: a month with no Lunation of a given kind -----------------------


def test_a_month_with_no_lunation_of_a_given_kind_records_nothing_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()

    # Delta-lambda parked at a constant 90 degrees all month -- never near
    # either target (0 or 180 degrees).
    def sun_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE

    def moon_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE + 90.0

    _patch_calc_ut(monkeypatch, sun_longitude_fn, moon_longitude_fn)

    records = find_lunations(chart, _MONTH_START, _MONTH_END)

    assert records == ()


# --- Half-open interval: a crossing landing exactly on month_end_utc ------------


def test_a_crossing_landing_exactly_on_month_end_utc_is_never_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: ``_build_grid()`` appends ``month_end_utc`` itself as a
    final probe point (to catch a crossing hiding in the last partial grid
    step), but the analyzed interval is half-open,
    ``[month_start_utc, month_end_utc)`` -- ``month_end_utc`` itself is
    never inside it. A synthetic Moon whose longitude equals the Sun's
    (Delta-lambda = 0, the new-moon target) only at that one excluded probe
    instant -- constantly 5 degrees short of it everywhere else -- must
    never produce a Lunation -- mirrors ``tests/test_ingresses.py``'s own
    boundary regression test."""
    chart = _minimal_natal_chart()

    month_end_jd = swe.utc_to_jd(2024, 7, 1, 0, 0, 0.0, swe.GREG_CAL)[1]

    def fake_calc_ut(jd_ut: float, body_id: int, flags: int) -> tuple[tuple[float, ...], int]:
        if body_id == swe.SUN:
            longitude = _SUN_LONGITUDE
        elif body_id == swe.MOON:
            longitude = _SUN_LONGITUDE if jd_ut == month_end_jd else _SUN_LONGITUDE - 5.0
        else:
            raise AssertionError(f"unexpected body_id {body_id!r}")
        xx = (longitude, 0.0, 1.0, 0.0, 0.0, 0.0)
        retflag = swe.FLG_SWIEPH | swe.FLG_SPEED
        return xx, retflag

    monkeypatch.setattr("core.ephemeris.positions.swe.calc_ut", fake_calc_ut)

    records = find_lunations(chart, _MONTH_START, _MONTH_END)

    for record in records:
        assert record.occurred_at < _MONTH_END, (
            f"Lunation reported at or past month_end_utc (half-open interval violation): {record!r}"
        )
    assert records == (), (
        f"expected nothing recorded (never actually crosses inside the half-open "
        f"interval), got {records!r}"
    )


# --- Determinism -----------------------------------------------------------------


def test_identical_inputs_computed_twice_are_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = _minimal_natal_chart()

    def sun_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE

    def moon_longitude_fn(days: float) -> float:
        return _SUN_LONGITUDE + _SLOW_RATE * (days - 15.0)

    _patch_calc_ut(monkeypatch, sun_longitude_fn, moon_longitude_fn)

    first = find_lunations(chart, _MONTH_START, _MONTH_END)
    second = find_lunations(chart, _MONTH_START, _MONTH_END)

    assert first == second


# --- Always: real ephemeris smoke test --------------------------------------------


def test_a_real_month_produces_plausible_lunations() -> None:
    """Uses a real (un-mocked) month against a real-shaped chart -- an
    integration-shaped smoke test that the whole scan behaves sanely end to
    end, complementing the synthetic per-row tests above. Real ephemeris
    conformance against a corroborated public reference (exact kind/date/
    UTC time) is exercised in ``tests/test_conformance.py``, not duplicated
    here."""
    chart = _minimal_natal_chart()
    month_start = datetime(2023, 8, 1, tzinfo=UTC)
    month_end = datetime(2023, 9, 1, tzinfo=UTC)

    records = find_lunations(chart, month_start, month_end)

    assert records != ()
    for record in records:
        assert record.kind in ("new_moon", "full_moon")
        assert record.occurred_at.tzinfo is not None
        assert record.occurred_at.utcoffset() == timedelta(0)
        assert month_start <= record.occurred_at < month_end
        assert record.natal_house in range(1, 13)


# --- Always: half-open UTC interval validation ------------------------------------


def test_a_naive_month_boundary_is_refused() -> None:
    chart = _minimal_natal_chart()
    naive = datetime(2024, 6, 1)

    with pytest.raises(ValueError, match="timezone-aware"):
        find_lunations(chart, naive, _MONTH_END)


def test_a_month_start_not_before_month_end_is_refused() -> None:
    chart = _minimal_natal_chart()

    with pytest.raises(ValueError, match="before"):
        find_lunations(chart, _MONTH_END, _MONTH_START)


def test_a_month_start_equal_to_month_end_is_refused() -> None:
    """``_require_utc_interval``'s own ``start >= end`` check is meant to
    cover both the reversed-order case above and this exact-equality case
    -- exercised separately since an empty interval is a distinct edge from
    a reversed one."""
    chart = _minimal_natal_chart()

    with pytest.raises(ValueError, match="before"):
        find_lunations(chart, _MONTH_START, _MONTH_START)


# --- Frozen dataclass --------------------------------------------------------------


def test_lunation_is_frozen() -> None:
    lunation = Lunation(
        kind="new_moon",
        occurred_at=_MONTH_START,
        longitude=Decimal("200.0000"),
        natal_house=7,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        lunation.kind = "full_moon"  # type: ignore[misc]
