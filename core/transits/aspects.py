"""Find every transit-to-natal Aspect across an analyzed month, and the exact
moment each one perfects (Story 3.1).

Pure (AD-1): no I/O, clock, network or randomness -- only ``swisseph`` and
what is passed in (``NatalChart``, the month's UTC interval,
``ComputationConfig``). Reuses ``core/ephemeris/positions.py``'s shared
low-level helpers and ``core/ephemeris/chart.py``'s natal-Aspect matching
table (``_ASPECTS``) rather than reimplementing either.

**Deriving the month interval is not this module's job.** ``find_transit_aspects``
takes an already-computed half-open UTC interval ``[month_start_utc,
month_end_utc)``; converting a Client's local calendar-month boundaries
(``Client.iana_zone``) into that interval happens elsewhere (a future Report
Payload story), matching the "pass in already-resolved facts" shape
``compute_natal_chart`` itself uses for ``birth_instant_utc``.

**Root-finding uses a signed, target-centered offset, not the folded
``[0, 180]`` separation.** ``core/ephemeris/chart.py``'s ``_angular_separation``
is unsigned and has a non-differentiable kink exactly at 0 degrees
(conjunction) and 180 degrees (opposition) -- a "touch and bounce" that
never actually changes sign, which breaks ordinary sign-change bisection for
those two aspects specifically. Recentering on the target angle first
(``_signed_offset``, wrapped to ``(-180, 180]``) is smooth through zero for
all five aspects uniformly: perfection is a genuine sign change of that
offset, located by bisection; the orb boundary (entering/leaving orb) is a
sign change of ``|offset| - orb_limit``, located the same way.

**Sextile/square/trine each need two scans, not one.** The folded
separation treats "transiting body sits ``target_degrees`` ahead of the
natal point" and "...``target_degrees`` behind it" as the same aspect --
two genuinely distinct, independently timed configurations for any target
strictly between 0 and 180. ``_target_branches`` returns both raw-difference
values to scan (just one for conjunction/opposition, which are self-mirrored);
``find_transit_aspects`` scans every branch, all still labeled with the same
aspect name. Scanning only the "ahead" branch would silently miss every
"behind" occurrence.

**A coarse time grid, refined by bisection, not a continuous solve.** The
fastest configured transiting body (Mercury, up to ~2.2 degrees/day) sweeps
a full orb window (``2 * config.orbs.transit``, at most 5 degrees) in a bit
under two days -- well above ``_GRID_STEP``'s 6-hour cadence, so no orb
entry, exit or perfection is ever hidden inside a single grid step. Between
two grid samples that bracket a sign change, standard bisection
(``_BISECTION_ITERATIONS`` halvings) narrows to sub-second precision.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

import swisseph as swe

from core.ephemeris.chart import _ASPECTS
from core.ephemeris.positions import FULL_CIRCLE, HALF_CIRCLE, _calc_body, _julian_day_ut
from core.types.chart import NatalChart
from core.types.computation import ComputationConfig
from core.types.transits import TransitAspectEvent

__all__ = ["find_transit_aspects"]

#: swisseph body constants for the transiting side of a scan -- deliberately
#: excludes the Moon (PRD FR-9 / ComputationConfig.bodies' own docstring):
#: the transiting Moon never enters the Report except through Lunations
#: (Story 3.3), so it is never a valid value in ``config.bodies.fast/slow``
#: and a lookup here raises loudly (``KeyError``) rather than silently
#: scanning it if it ever were.
_TRANSIT_BODY_IDS: dict[str, int] = {
    "sun": swe.SUN,
    "mercury": swe.MERCURY,
    "venus": swe.VENUS,
    "mars": swe.MARS,
    "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
    "uranus": swe.URANUS,
    "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO,
}

#: Sampling cadence for the coarse pre-scan (see the module's Design Notes
#: for why this is fine-grained enough to never miss an in-orb window).
_GRID_STEP = timedelta(hours=6)

#: Fixed halving count for every bisection -- not a tolerance-based loop, so
#: runtime and precision are both bounded regardless of the input interval's
#: width. Over a full calendar month (~31 days) this narrows to well under a
#: second; see the module's Design Notes.
_BISECTION_ITERATIONS = 40

_ZERO_OFFSET = timedelta(0)


def find_transit_aspects(
    natal_chart: NatalChart,
    month_start_utc: datetime,
    month_end_utc: datetime,
    config: ComputationConfig,
) -> tuple[TransitAspectEvent, ...]:
    """Every transit-to-natal Aspect within ``[month_start_utc, month_end_utc)``.

    Scans ``config.bodies.fast`` then ``config.bodies.slow`` (in that
    configured order) against the ten natal planets, ascendant, midheaven,
    true node and south node -- all already present on ``natal_chart`` --
    using only the five aspects in ``core/ephemeris/chart.py``'s
    ``_ASPECTS`` table and ``config.orbs.transit`` as the orb.

    Deterministic: identical arguments produce an identical output tuple
    every call -- no clock, I/O or randomness is consulted.

    Raises:
        ValueError: either boundary is not timezone-aware UTC,
            ``month_start_utc`` is not strictly before ``month_end_utc``, or
            ``config.bodies.fast``/``slow`` names a body this module does not
            support scanning as a transiting body (see ``_TRANSIT_BODY_IDS``
            -- the transiting Moon is deliberately never one of them).
        EphemerisIntegrityError: a transiting body's position was not
            confirmed as coming from the Swiss Ephemeris (propagated from
            ``core.ephemeris.positions._calc_body``).
    """
    _require_utc_interval(month_start_utc, month_end_utc)

    natal_targets = _natal_targets(natal_chart)
    transiting_bodies = tuple(config.bodies.fast) + tuple(config.bodies.slow)
    orb_limit = config.orbs.transit

    grid_times = _build_grid(month_start_utc, month_end_utc)

    # Bodies -> natal targets -> aspects -> branches: this exact nesting
    # fixes the order events are collected (and thus emitted) in.
    # tests/test_conformance.py's fixture comparison diffs a month
    # fixture's own expected.transit_events list element-by-index, not as
    # an unordered set, so it relies on this scan producing events in this
    # same stable order -- changing it later means re-deriving the
    # fixtures' expected order too, not just re-checking which events are
    # found.
    events: list[TransitAspectEvent] = []
    for body_name in transiting_bodies:
        if body_name not in _TRANSIT_BODY_IDS:
            raise ValueError(
                f"config.bodies names {body_name!r}, which is not a body "
                "find_transit_aspects() supports scanning as a transiting "
                f"body (supported: {sorted(_TRANSIT_BODY_IDS)})."
            )
        body_id = _TRANSIT_BODY_IDS[body_name]
        longitudes = [_longitude_at(body_id, instant) for instant in grid_times]
        for natal_name, natal_longitude in natal_targets:
            for aspect_name, target_degrees in _ASPECTS:
                for branch_degrees in _target_branches(target_degrees):
                    events.extend(
                        _events_for_pair(
                            body_name=body_name,
                            body_id=body_id,
                            natal_name=natal_name,
                            natal_longitude=natal_longitude,
                            aspect_name=aspect_name,
                            target_degrees=branch_degrees,
                            grid_times=grid_times,
                            longitudes=longitudes,
                            orb_limit=orb_limit,
                        )
                    )
    return tuple(events)


def _target_branches(target_degrees: Decimal) -> tuple[Decimal, ...]:
    """The one or two raw longitude-difference values that correspond to
    ``target_degrees``'s aspect, mod 360.

    ``_angular_separation`` (the unsigned, folded ``[0, 180]`` distance
    ``core/ephemeris/chart.py``'s own natal-Aspect matching uses) treats a
    transiting body sitting ``target_degrees`` *ahead* of the natal point
    and one sitting ``target_degrees`` *behind* it as the same aspect --
    both fold to the same separation. Conjunction (0) and opposition (180)
    are self-mirrored (ahead and behind are the same point on the circle,
    one branch); sextile/square/trine (60/90/120) are not -- ahead and
    behind are two genuinely distinct configurations, each with its own,
    independently timed, perfection instant within the month. Scanning only
    one branch would silently miss every occurrence of the other.
    """
    mirror = -target_degrees % FULL_CIRCLE
    if mirror < 0:
        mirror += FULL_CIRCLE
    if mirror == target_degrees:
        return (target_degrees,)
    return (target_degrees, mirror)


def _require_utc_interval(start: datetime, end: datetime) -> None:
    for label, value in (("month_start_utc", start), ("month_end_utc", end)):
        if value.tzinfo is None or value.utcoffset() != _ZERO_OFFSET:
            raise ValueError(
                f"{label} must be timezone-aware UTC (utcoffset() == 0); got {value!r}."
            )
    if start >= end:
        raise ValueError(
            f"month_start_utc ({start!r}) must be strictly before month_end_utc ({end!r})."
        )


def _natal_targets(chart: NatalChart) -> tuple[tuple[str, Decimal], ...]:
    """The fourteen fixed natal targets a transit can aspect: the twelve
    bodies already on ``chart.planets`` (the ten planets, true node, south
    node) plus ascendant and midheaven, which are separate ``NatalChart``
    fields rather than ``planets`` entries."""
    targets = [(planet.name, planet.longitude) for planet in chart.planets]
    targets.append(("ascendant", chart.ascendant))
    targets.append(("midheaven", chart.midheaven))
    return tuple(targets)


def _build_grid(start: datetime, end: datetime) -> list[datetime]:
    """Sample instants covering ``[start, end)`` at ``_GRID_STEP`` cadence,
    plus ``end`` itself as a final probe point -- used only to tell whether
    an in-orb interval is still open as the month closes (``end`` is
    excluded from the analyzed interval itself; see ``_events_for_pair``)."""
    times = []
    instant = start
    while instant < end:
        times.append(instant)
        instant += _GRID_STEP
    times.append(end)
    return times


def _longitude_at(body_id: int, instant: datetime) -> Decimal:
    return _calc_body(_julian_day_ut(instant), body_id)[0]


def _normalize_signed(value: Decimal) -> Decimal:
    """``value`` wrapped into ``(-180, 180]``."""
    normalized = value % FULL_CIRCLE
    if normalized < 0:
        normalized += FULL_CIRCLE
    if normalized > HALF_CIRCLE:
        normalized -= FULL_CIRCLE
    return normalized


def _signed_offset(
    transiting_longitude: Decimal, natal_longitude: Decimal, target: Decimal
) -> Decimal:
    """The signed distance from exact perfection: 0 when the transiting body
    sits exactly ``target`` degrees from the natal point, smooth (no kink)
    through 0 for every aspect -- see the module's Design Notes.

    Implicit precondition: ``orb_limit`` (``config.orbs.transit``) must stay
    well under 180 degrees. ``_normalize_signed``'s own wrap-around, at
    +/-180 degrees from ``target``, is exactly where this offset stops being
    single-valued -- an orb anywhere near that boundary would let the
    in-orb/perfection sign-change checks in ``_events_for_pair`` (and the
    bisection they drive) see a spurious sign flip there instead of a real
    one. ``ComputationConfig``'s own load-time validation (permitted range
    1.5-2.5 degrees, ``shell/computation.py``) already keeps every orb this
    module ever sees far below that boundary.
    """
    return _normalize_signed(transiting_longitude - natal_longitude - target)


def _bisect(f: Callable[[datetime], Decimal], lo: datetime, hi: datetime) -> datetime:
    """Standard bisection for a continuous, sign-changing ``f`` on
    ``[lo, hi]``. The caller guarantees ``f(lo)`` and ``f(hi)`` either are
    zero or have opposite signs -- that guarantee is the sign-change checks
    in ``_events_for_pair`` before this is ever called."""
    f_lo = f(lo)
    if f_lo == 0:
        return lo
    f_hi = f(hi)
    if f_hi == 0:
        return hi

    for _ in range(_BISECTION_ITERATIONS):
        mid = lo + (hi - lo) / 2
        f_mid = f(mid)
        if f_mid == 0:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return lo + (hi - lo) / 2


def _events_for_pair(
    *,
    body_name: str,
    body_id: int,
    natal_name: str,
    natal_longitude: Decimal,
    aspect_name: str,
    target_degrees: Decimal,
    grid_times: list[datetime],
    longitudes: list[Decimal],
    orb_limit: Decimal,
) -> list[TransitAspectEvent]:
    """Walk one (transiting body, natal point, aspect) triple across the
    grid, emitting one :class:`TransitAspectEvent` per contiguous in-orb
    interval. A pair that re-enters orb after separating (a retrograde loop)
    produces a second, independent event -- never merged with the first."""

    def offset_at(instant: datetime) -> Decimal:
        return _signed_offset(_longitude_at(body_id, instant), natal_longitude, target_degrees)

    def orb_gap_at(instant: datetime) -> Decimal:
        return abs(offset_at(instant)) - orb_limit

    events: list[TransitAspectEvent] = []
    offsets = [_signed_offset(lon, natal_longitude, target_degrees) for lon in longitudes]

    in_orb = abs(offsets[0]) <= orb_limit
    entry_at: datetime | None = grid_times[0] if in_orb else None
    perfected_at: datetime | None = grid_times[0] if (in_orb and offsets[0] == 0) else None

    for index in range(len(grid_times) - 1):
        t0, t1 = grid_times[index], grid_times[index + 1]
        d0, d1 = offsets[index], offsets[index + 1]
        was_in_orb = in_orb

        if not was_in_orb and abs(d1) <= orb_limit:
            entry_at = _bisect(orb_gap_at, t0, t1)
            in_orb = True
            perfected_at = None

        if (was_in_orb or in_orb) and perfected_at is None:
            if d1 == 0:
                perfected_at = t1
            elif d0 != 0 and (d0 > 0) != (d1 > 0):
                perfected_at = _bisect(offset_at, t0, t1)

        if was_in_orb and abs(d1) > orb_limit:
            exit_at = _bisect(orb_gap_at, t0, t1)
            assert entry_at is not None
            events.append(
                TransitAspectEvent(
                    transiting_body=body_name,
                    natal_point=natal_name,
                    aspect=aspect_name,
                    perfected_at=perfected_at,
                    never_perfected=perfected_at is None,
                    orb_entry_at=entry_at,
                    orb_exit_at=exit_at,
                )
            )
            in_orb = False
            entry_at = None
            perfected_at = None

    if in_orb:
        assert entry_at is not None
        events.append(
            TransitAspectEvent(
                transiting_body=body_name,
                natal_point=natal_name,
                aspect=aspect_name,
                perfected_at=perfected_at,
                never_perfected=perfected_at is None,
                orb_entry_at=entry_at,
                orb_exit_at=None,
            )
        )

    return events
