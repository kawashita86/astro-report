"""Find every Station (direction-change instant) and standing retrograde
condition for each configured transiting body across an analyzed month
(Story 3.2).

Pure (AD-1): no I/O, clock, network or randomness -- only ``swisseph`` (via
``core/ephemeris/positions.py``'s shared helpers) and what is passed in (the
month's UTC interval, ``ComputationConfig``). Unlike
``core/transits/aspects.py``, no ``NatalChart`` is threaded through this
module at all: retrograde motion is a fact about the transiting body alone,
never about its relationship to a natal point.

**Retrograde condition is read straight off ``_calc_body``'s existing
``speed`` value.** ``core/ephemeris/positions.py``'s ``_calc_body`` already
returns ``(longitude, speed)`` with ``FLG_SPEED`` requested on every call --
Story 3.1 (``core/transits/aspects.py``) never reads that second value, so
this module is its first real consumer. A body is retrograde exactly where
``speed`` (dλ/dt) is negative; a Station is the instant that sign changes.

**The same coarse-grid-plus-bisection method as ``aspects.py``, mirrored
rather than imported.** ``_GRID_STEP`` and ``_BISECTION_ITERATIONS`` below
carry the same values and the same justification as
``core/transits/aspects.py``'s own constants of the same name (see that
module's Design Notes for the full argument: the fastest configured body's
sweep rate stays well above the grid's cadence, so no direction change is
ever hidden inside a single grid step, and a fixed halving count bounds both
runtime and precision regardless of the input interval's width). They are
mirrored locally, not imported, since finding a *zero* of ``speed`` itself
(no target-angle offset, unlike ``aspects.py``'s ``_signed_offset``) is a
simpler root than what ``aspects.py`` bisects -- the two modules' bisection
loops share their fixed-halving *shape*, not a common target function.

**Body-id lookup is reused, not redefined.** ``_TRANSIT_BODY_IDS``
(``core/transits/aspects.py``) is imported directly -- a private
cross-module import, the same accepted pattern
``tests/test_conformance.py`` already relies on for that same name -- rather
than keeping a second swisseph-constant table in sync by hand.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from core.ephemeris.positions import _calc_body, _julian_day_ut
from core.transits.aspects import _TRANSIT_BODY_IDS
from core.types.computation import ComputationConfig
from core.types.transits import StandingRetrograde, Station

__all__ = ["find_stations"]

#: Sampling cadence for the coarse pre-scan -- mirrors
#: ``core/transits/aspects.py``'s own ``_GRID_STEP`` (see this module's
#: docstring for why the value is safe to reuse unchanged here).
_GRID_STEP = timedelta(hours=6)

#: Fixed halving count for every bisection -- mirrors
#: ``core/transits/aspects.py``'s own ``_BISECTION_ITERATIONS``.
_BISECTION_ITERATIONS = 40

_ZERO_OFFSET = timedelta(0)

_RETROGRADE = "retrograde"
_DIRECT = "direct"


def find_stations(
    month_start_utc: datetime,
    month_end_utc: datetime,
    config: ComputationConfig,
) -> tuple[Station | StandingRetrograde, ...]:
    """Every Station and standing-retrograde condition within
    ``[month_start_utc, month_end_utc)``.

    Scans ``config.bodies.fast`` then ``config.bodies.slow`` (in that
    configured order, matching ``find_transit_aspects()``'s own scan order)
    -- the transiting Moon is never a valid entry there (see
    ``ComputationConfig.bodies``'s own docstring) and so is never scanned
    here either; it never stations.

    For each body: samples ``speed`` on the same coarse grid
    ``core/transits/aspects.py`` uses, bisects each sign change to
    sub-second precision into a :class:`Station`, and -- only when the body
    turned zero times across the whole interval -- emits a
    :class:`StandingRetrograde` if that unchanging sign was negative. A body
    direct the entire month (also zero turns, but positive throughout) is
    not recorded at all.

    Deterministic: identical arguments produce an identical output tuple
    every call -- no clock, I/O or randomness is consulted.

    Raises:
        ValueError: either boundary is not timezone-aware UTC,
            ``month_start_utc`` is not strictly before ``month_end_utc``, or
            ``config.bodies.fast``/``slow`` names a body this module does
            not support scanning (see ``_TRANSIT_BODY_IDS`` -- the
            transiting Moon is deliberately never one of them).
        EphemerisIntegrityError: a transiting body's position was not
            confirmed as coming from the Swiss Ephemeris (propagated from
            ``core.ephemeris.positions._calc_body``).
    """
    _require_utc_interval(month_start_utc, month_end_utc)

    transiting_bodies = tuple(config.bodies.fast) + tuple(config.bodies.slow)
    grid_times = _build_grid(month_start_utc, month_end_utc)

    records: list[Station | StandingRetrograde] = []
    for body_name in transiting_bodies:
        if body_name not in _TRANSIT_BODY_IDS:
            raise ValueError(
                f"config.bodies names {body_name!r}, which is not a body "
                "find_stations() supports scanning as a transiting body "
                f"(supported: {sorted(_TRANSIT_BODY_IDS)})."
            )
        body_id = _TRANSIT_BODY_IDS[body_name]
        speeds = [_speed_at(body_id, instant) for instant in grid_times]

        def speed_fn(instant: datetime, body_id: int = body_id) -> Decimal:
            return _speed_at(body_id, instant)

        turns_found = 0
        for index in range(len(grid_times) - 1):
            t0, t1 = grid_times[index], grid_times[index + 1]
            s0, s1 = speeds[index], speeds[index + 1]

            station_at: datetime | None = None
            if s1 == 0:
                station_at = t1
            elif s0 != 0 and (s0 > 0) != (s1 > 0):
                station_at = _bisect(speed_fn, t0, t1)

            # `grid_times` (``_build_grid``) appends ``month_end_utc`` itself
            # as a final probe point, purely to catch a turn hiding in the
            # last partial grid step -- but the analyzed interval is
            # half-open, ``[month_start_utc, month_end_utc)``, and
            # ``month_end_utc`` itself is never inside it. The ``s1 == 0``
            # branch above can otherwise set ``station_at`` to that excluded
            # final probe point verbatim (``_bisect`` itself never returns
            # its own ``hi`` argument unless ``f(hi) == 0``, which is
            # exactly this case) -- guarded out here rather than never
            # detected: a genuine crossing whose speed is only exactly zero
            # at that excluded instant never actually flips sign anywhere
            # *inside* the half-open interval, so it is correctly not a
            # turn "in" this month at all (it falls through to the
            # standing-retrograde check below like any other non-turn).
            if station_at is not None and station_at < month_end_utc:
                turns_found += 1
                direction = _RETROGRADE if s0 > 0 else _DIRECT
                longitude = _calc_body(_julian_day_ut(station_at), body_id)[0]
                records.append(
                    Station(
                        body=body_name,
                        direction=direction,
                        station_at=station_at,
                        longitude=longitude,
                    )
                )

        if turns_found == 0 and speeds[0] < 0:
            records.append(
                StandingRetrograde(
                    body=body_name,
                    retrograde_start_utc=month_start_utc,
                    retrograde_end_utc=month_end_utc,
                )
            )

    return tuple(records)


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


def _build_grid(start: datetime, end: datetime) -> list[datetime]:
    """Sample instants covering ``[start, end)`` at ``_GRID_STEP`` cadence,
    plus ``end`` itself as a final probe point -- mirrors
    ``core/transits/aspects.py``'s own ``_build_grid`` (a turn in the last
    partial grid step before the month closes must not be missed)."""
    times = []
    instant = start
    while instant < end:
        times.append(instant)
        instant += _GRID_STEP
    times.append(end)
    return times


def _speed_at(body_id: int, instant: datetime) -> Decimal:
    return _calc_body(_julian_day_ut(instant), body_id)[1]


def _bisect(f: Callable[[datetime], Decimal], lo: datetime, hi: datetime) -> datetime:
    """Standard bisection for a continuous, sign-changing ``f`` on
    ``[lo, hi]`` -- mirrors ``core/transits/aspects.py``'s own ``_bisect``.
    The caller guarantees ``f(lo)`` and ``f(hi)`` either are zero or have
    opposite signs -- that guarantee is the sign-change checks in
    ``find_stations`` before this is ever called."""
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
