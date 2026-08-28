"""``find_transit_aspects()`` -- one test per row of the story's I/O &
Edge-Case Matrix, plus the properties those rows imply: determinism, and a
located ``perfected_at`` landing within quantization tolerance of the exact
aspect angle (Story 3.1's Design Notes: there is no third-party "exact
perfection time" oracle, so this structural self-check stands in for one).

Most rows need precise control over a transiting body's longitude as a
function of time (a parabola for a station that never quite perfects, a sine
wave for a retrograde loop's repeated crossings) that real ephemeris data
cannot be relied on to produce inside a short, fast-running test. These use
a synthetic ``swe.calc_ut`` (monkeypatched at
``core.ephemeris.positions.swe.calc_ut``, where ``_calc_body`` -- shared
with natal computation -- actually calls it) mirroring
``tests/test_natal_chart.py``'s own pattern for the Moshier-fallback test.
Real ephemeris conformance (the fixtures' snapshot-moment orb/aspect values)
is exercised end to end in ``tests/test_conformance.py``, not duplicated
here.

A synthetic ``NatalChart`` is built by hand (a plain frozen dataclass, no
``compute_natal_chart()`` call needed) with a single named planet ("moon")
at a controlled longitude -- ``find_transit_aspects()`` only ever reads
``chart.planets``/``chart.ascendant``/``chart.midheaven``, so a minimal
chart exercises it exactly as fully as a real twelve-body one.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import swisseph as swe

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.transits.aspects import find_transit_aspects
from core.types.chart import NatalChart, PlanetPosition
from core.types.computation import Bodies, ComputationConfig
from core.types.transits import TransitAspectEvent
from shell.computation import load_computation_config

verify_ephemeris_identity()
_BASE_CONFIG = load_computation_config()

# The autouse fixture re-pinning the real vendored ephemeris before every
# test in the session lives in tests/conftest.py (shared across modules).

_MONTH_START = datetime(2024, 6, 1, tzinfo=UTC)
_MONTH_END = datetime(2024, 7, 1, tzinfo=UTC)

#: Real Julian Day (via the un-mocked ``swe.utc_to_jd``) of ``_MONTH_START``
#: -- Julian Day increases by exactly 1.0 per UTC day, so every synthetic
#: formula below is expressed simply in "days since this reference."
_MONTH_START_JD = swe.utc_to_jd(2024, 6, 1, 0, 0, 0.0, swe.GREG_CAL)[1]

_TARGET_DEGREES: dict[str, Decimal] = {
    "conjunction": Decimal(0),
    "sextile": Decimal(60),
    "square": Decimal(90),
    "trine": Decimal(120),
    "opposition": Decimal(180),
}

#: Quantization tolerance: positions are quantized to 4 decimal places
#: (``core/ephemeris/positions.py``'s ``QUANTUM``) before any Aspect math
#: runs, so a bisected ``perfected_at`` lands within a small multiple of
#: that step of the exact target angle, not exactly on it.
_QUANTIZATION_TOLERANCE = Decimal("0.001")


def _config_with_single_transiting_body(
    body: str, transit_orb: Decimal | None = None
) -> ComputationConfig:
    orbs = (
        _BASE_CONFIG.orbs
        if transit_orb is None
        else dataclasses.replace(_BASE_CONFIG.orbs, transit=transit_orb)
    )
    return dataclasses.replace(_BASE_CONFIG, orbs=orbs, bodies=Bodies(fast=(body,), slow=()))


def _minimal_natal_chart(moon_longitude: Decimal) -> NatalChart:
    """A synthetic chart with a single natal target ("moon") at a controlled
    longitude, plus ascendant/midheaven parked far away from anything the
    synthetic transiting-body formulas below touch."""
    moon = PlanetPosition(
        name="moon",
        longitude=moon_longitude,
        sign="aries",
        degree=Decimal("0"),
        house=1,
        retrograde=False,
    )
    return NatalChart(
        ascendant=Decimal("15.0000"),
        midheaven=Decimal("225.0000"),
        planets=(moon,),
        houses=(),
        aspects=(),
    )


def _events_for(
    events: tuple[TransitAspectEvent, ...], *, transiting: str, natal: str, aspect: str
) -> list[TransitAspectEvent]:
    return [
        event
        for event in events
        if event.transiting_body == transiting
        and event.natal_point == natal
        and event.aspect == aspect
    ]


def _wrap_degrees(value: float) -> float:
    return value % 360.0


def _patch_calc_ut(monkeypatch: pytest.MonkeyPatch, longitude_fn) -> None:
    """Replace ``swe.calc_ut`` (as seen from ``core.ephemeris.positions``,
    where ``_calc_body`` -- shared with natal computation -- calls it) with
    a synthetic body whose longitude is ``longitude_fn(days_since_month_start)``.
    Speed is derived numerically (a tiny finite difference) since
    ``find_transit_aspects()`` itself never reads it, only ``_calc_body``'s
    own Moshier-fallback integrity check does (via the real ``FLG_SWIEPH``
    flag, always set here)."""

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


# --- Matrix row: standard perfection + numeric-tolerance property -------------


def test_a_standard_approach_locates_the_perfection_instant_within_the_orb_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moon_longitude = Decimal("100.0000")
    config = _config_with_single_transiting_body("sun", transit_orb=Decimal("2.0"))
    chart = _minimal_natal_chart(moon_longitude)

    # Direct motion at 1 degree/day, crossing the conjunction (moon's own
    # longitude) around day 20 -- well clear of both month boundaries.
    def longitude_fn(days: float) -> float:
        return 80.0 + 1.0 * days

    _patch_calc_ut(monkeypatch, longitude_fn)

    events = find_transit_aspects(chart, _MONTH_START, _MONTH_END, config)
    matches = _events_for(events, transiting="sun", natal="moon", aspect="conjunction")

    assert len(matches) == 1
    event = matches[0]
    assert event.perfected_at is not None
    assert event.never_perfected is False
    assert _MONTH_START <= event.orb_entry_at < event.perfected_at
    assert event.orb_exit_at is not None
    assert event.perfected_at < event.orb_exit_at <= _MONTH_END

    # Numeric-tolerance property: re-evaluating the synthetic separation at
    # the located instant lands within quantization tolerance of the target.
    days = (event.perfected_at - _MONTH_START).total_seconds() / 86400.0
    longitude_at_perfection = Decimal(str(_wrap_degrees(longitude_fn(days))))
    separation = abs(longitude_at_perfection - moon_longitude)
    if separation > Decimal(180):
        separation = Decimal(360) - separation
    assert separation <= _QUANTIZATION_TOLERANCE


def test_identical_inputs_computed_twice_are_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moon_longitude = Decimal("100.0000")
    config = _config_with_single_transiting_body("sun", transit_orb=Decimal("2.0"))
    chart = _minimal_natal_chart(moon_longitude)

    def longitude_fn(days: float) -> float:
        return 80.0 + 1.0 * days

    _patch_calc_ut(monkeypatch, longitude_fn)

    first = find_transit_aspects(chart, _MONTH_START, _MONTH_END, config)
    second = find_transit_aspects(chart, _MONTH_START, _MONTH_END, config)

    assert first == second


# --- Matrix row: in orb all month, never perfects ------------------------------


def test_a_close_approach_that_never_perfects_is_recorded_with_never_perfected_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moon_longitude = Decimal("100.0000")
    config = _config_with_single_transiting_body("sun", transit_orb=Decimal("2.0"))
    chart = _minimal_natal_chart(moon_longitude)

    # A downward parabola peaking 0.5 degrees short of the conjunction
    # (moon's longitude): the body approaches, "stations" at the peak, then
    # recedes -- dipping within the 2.0-degree orb around day 15 without
    # ever touching the exact target angle.
    peak_longitude = 99.5
    peak_day = 15.0
    curvature = 0.02

    def longitude_fn(days: float) -> float:
        return peak_longitude - curvature * (days - peak_day) ** 2

    _patch_calc_ut(monkeypatch, longitude_fn)

    events = find_transit_aspects(chart, _MONTH_START, _MONTH_END, config)
    matches = _events_for(events, transiting="sun", natal="moon", aspect="conjunction")

    assert len(matches) == 1
    event = matches[0]
    assert event.perfected_at is None
    assert event.never_perfected is True
    assert event.orb_entry_at is not None
    assert event.orb_exit_at is not None
    assert _MONTH_START <= event.orb_entry_at < event.orb_exit_at <= _MONTH_END


# --- Matrix row: perfection near a month boundary ------------------------------


def test_perfection_near_a_month_boundary_is_assigned_to_exactly_one_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moon_longitude = Decimal("100.0000")
    config = _config_with_single_transiting_body("sun", transit_orb=Decimal("2.0"))
    chart = _minimal_natal_chart(moon_longitude)

    # Direct motion crossing the conjunction two hours before month end.
    crossing_days = 30.0 - (2.0 / 24.0)
    moon_longitude_float = float(moon_longitude)

    def longitude_fn(days: float) -> float:
        return moon_longitude_float + 1.0 * (days - crossing_days)

    _patch_calc_ut(monkeypatch, longitude_fn)

    this_month_events = find_transit_aspects(chart, _MONTH_START, _MONTH_END, config)
    this_month_matches = _events_for(
        this_month_events, transiting="sun", natal="moon", aspect="conjunction"
    )
    assert len(this_month_matches) == 1
    this_month_event = this_month_matches[0]
    assert this_month_event.perfected_at is not None
    assert _MONTH_START <= this_month_event.perfected_at < _MONTH_END

    # The pair is still (barely) in orb, separating, as the next month opens
    # -- it must not be reported as perfecting again there: the perfection
    # already happened before this later interval's own start.
    next_month_end = _MONTH_END + timedelta(days=1)
    next_month_events = find_transit_aspects(chart, _MONTH_END, next_month_end, config)
    next_month_matches = _events_for(
        next_month_events, transiting="sun", natal="moon", aspect="conjunction"
    )
    assert len(next_month_matches) >= 1, "the pair should still be (barely) in orb as month 2 opens"
    for event in next_month_matches:
        assert event.perfected_at is None
        assert event.orb_entry_at == _MONTH_END


# --- Matrix row: approach while retrograde -------------------------------------


def test_perfection_is_located_correctly_across_a_retrograde_speed_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moon_longitude = Decimal("100.0000")
    config = _config_with_single_transiting_body("sun", transit_orb=Decimal("2.0"))
    chart = _minimal_natal_chart(moon_longitude)

    # A downward parabola whose peak sits well above the orb window and
    # early in the month: the body stations there (speed crosses zero) long
    # before it nears the orb, then arrives at -- and descends through --
    # the whole orb window (entry, the exact conjunction, exit) already
    # moving retrograde throughout.
    peak_longitude = 110.0
    peak_day = 2.0
    curvature = 0.05

    def longitude_fn(days: float) -> float:
        return peak_longitude - curvature * (days - peak_day) ** 2

    _patch_calc_ut(monkeypatch, longitude_fn)

    events = find_transit_aspects(chart, _MONTH_START, _MONTH_END, config)
    matches = _events_for(events, transiting="sun", natal="moon", aspect="conjunction")

    assert len(matches) == 1
    event = matches[0]
    assert event.perfected_at is not None
    assert event.never_perfected is False
    assert event.orb_entry_at < event.perfected_at
    assert event.orb_exit_at is not None
    assert event.perfected_at < event.orb_exit_at

    # The crossing happens strictly after the station (retrograde phase):
    # the parabola's descending root closest to the peak.
    expected_crossing_day = peak_day + math.sqrt(
        (peak_longitude - float(moon_longitude)) / curvature
    )
    perfected_day = (event.perfected_at - _MONTH_START).total_seconds() / 86400.0
    assert perfected_day == pytest.approx(expected_crossing_day, abs=0.01)


# --- Matrix row: same pair re-enters orb (retrograde loop) ---------------------


def test_a_pair_that_re_enters_orb_produces_two_distinct_events_never_merged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moon_longitude = Decimal("100.0000")
    config = _config_with_single_transiting_body("sun", transit_orb=Decimal("2.0"))
    chart = _minimal_natal_chart(moon_longitude)

    # A sine wave oscillating around the conjunction with an amplitude (5
    # degrees) wider than the orb (2 degrees) and a 10-day period: over the
    # 30-day month this crosses the exact target angle -- and separately
    # enters/exits orb -- multiple times, never continuously. The 2.5-day
    # phase offset keeps every crossing clear of both month boundaries
    # (otherwise a crossing would land exactly at day 0, coinciding with
    # this scenario's own orb-entry clamp).
    amplitude = 5.0
    period_days = 10.0
    phase_days = 2.5

    def longitude_fn(days: float) -> float:
        return float(moon_longitude) + amplitude * math.sin(
            2 * math.pi * (days + phase_days) / period_days
        )

    _patch_calc_ut(monkeypatch, longitude_fn)

    events = find_transit_aspects(chart, _MONTH_START, _MONTH_END, config)
    matches = _events_for(events, transiting="sun", natal="moon", aspect="conjunction")

    assert len(matches) >= 2
    for event in matches:
        assert event.perfected_at is not None
        assert event.never_perfected is False
    # Never merged: every event's own interval is properly ordered, and
    # consecutive events don't overlap.
    ordered = sorted(matches, key=lambda event: event.orb_entry_at)
    for event in ordered:
        assert event.orb_entry_at < event.perfected_at
        assert event.orb_exit_at is not None
        assert event.perfected_at < event.orb_exit_at
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        assert earlier.orb_exit_at <= later.orb_entry_at


# --- Always: scope (bodies, natal targets, aspects) -----------------------------


def test_scans_exactly_the_configured_bodies_against_the_fourteen_natal_targets() -> None:
    """Uses a real (short) window against a real natal chart -- an
    integration-shaped smoke test that the scan's *scope* (which bodies,
    which natal points, which aspects) matches the story's Always bullets,
    complementing the synthetic per-row tests above."""
    birth_instant_utc = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
    chart = compute_natal_chart(
        birth_instant_utc, Decimal("32.7358"), Decimal("-97.3453"), _BASE_CONFIG
    )
    month_start = datetime(2026, 1, 1, tzinfo=UTC)
    month_end = month_start + timedelta(days=3)

    events = find_transit_aspects(chart, month_start, month_end, _BASE_CONFIG)

    configured_bodies = set(_BASE_CONFIG.bodies.fast) | set(_BASE_CONFIG.bodies.slow)
    expected_natal_points = {planet.name for planet in chart.planets} | {"ascendant", "midheaven"}
    expected_aspects = {"conjunction", "sextile", "square", "trine", "opposition"}

    assert events != ()
    for event in events:
        assert event.transiting_body in configured_bodies
        assert event.transiting_body != "moon"
        assert event.natal_point in expected_natal_points
        assert event.aspect in expected_aspects
        assert event.orb_entry_at.tzinfo is not None
        assert event.orb_entry_at.utcoffset() == timedelta(0)
        if event.orb_exit_at is not None:
            assert event.orb_entry_at <= event.orb_exit_at
        assert event.never_perfected == (event.perfected_at is None)


# --- Always: half-open UTC interval validation ----------------------------------


def test_a_naive_month_boundary_is_refused() -> None:
    naive = datetime(2024, 6, 1)
    chart = _minimal_natal_chart(Decimal("100.0000"))

    with pytest.raises(ValueError, match="timezone-aware"):
        find_transit_aspects(chart, naive, _MONTH_END, _BASE_CONFIG)


def test_a_month_start_not_before_month_end_is_refused() -> None:
    chart = _minimal_natal_chart(Decimal("100.0000"))

    with pytest.raises(ValueError, match="before"):
        find_transit_aspects(chart, _MONTH_END, _MONTH_START, _BASE_CONFIG)


def test_transit_aspect_event_is_frozen() -> None:
    event = TransitAspectEvent(
        transiting_body="sun",
        natal_point="moon",
        aspect="conjunction",
        perfected_at=_MONTH_START,
        never_perfected=False,
        orb_entry_at=_MONTH_START,
        orb_exit_at=_MONTH_END,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.perfected_at = None  # type: ignore[misc]


# --- epic-3-retro item 22: runs correctly off the import/main thread ---------


def test_find_transit_aspects_on_a_worker_thread_matches_the_main_thread() -> None:
    """The real report pipeline runs ``find_transit_aspects`` on a FastAPI
    worker thread (``poll_report_run`` is a sync route). pyswisseph's ephemeris
    path is thread-local in this build, so ``_calc_body`` must re-bind the
    verified path on the calling thread; without that, the scan on the worker
    thread gets a Moshier fallback and every ``_calc_body`` raises. This uses
    the real ephemeris (no ``swe.calc_ut`` patch)."""
    from concurrent.futures import ThreadPoolExecutor

    # Sun crosses ~85 deg in mid-June 2024, so a real scan yields a conjunction.
    chart = _minimal_natal_chart(Decimal("85.0000"))
    config = _config_with_single_transiting_body("sun")

    def run() -> tuple[TransitAspectEvent, ...]:
        return find_transit_aspects(chart, _MONTH_START, _MONTH_END, config)

    main_thread_events = run()
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker_thread_events = pool.submit(run).result()

    assert worker_thread_events == main_thread_events
    assert _events_for(
        main_thread_events, transiting="sun", natal="moon", aspect="conjunction"
    ), "real-ephemeris scan should have produced the mid-June Sun-conjunct-Moon event"
