"""Locate every new moon and full moon across an analyzed month (Story 3.4).

Pure (AD-1): no I/O, clock, network or randomness -- only ``swisseph`` (via
``core/ephemeris/positions.py``'s shared helpers) and what is passed in
(``NatalChart``, the month's UTC interval). Unlike
``aspects.py``/``stations.py``/``ingresses.py``, no ``ComputationConfig`` is
threaded through this module at all: the body pair (Sun, Moon) and both
targets (0 degrees for a new moon, 180 degrees for a full moon) are fixed,
never configurable -- there is nothing in ``ComputationConfig`` a Lunation
scan would ever need to read.

**Delta-lambda, not a per-body offset.** ``core/transits/ingresses.py``
tracks one transiting body's offset from a fixed cusp; this module instead
tracks the *relative* angle between two transiting bodies, Delta-lambda =
(Moon longitude - Sun longitude) mod 360 degrees. A new moon is the instant
Delta-lambda crosses 0 degrees; a full moon is the instant it crosses 180
degrees. The Moon's angular speed always exceeds the Sun's and neither body
is ever retrograde against this measure, so Delta-lambda increases
monotonically all month -- every crossing is a simple forward (0 to +) sign
change, unlike ``Ingress``, which has no direction/departed-entered concept
to track here.

**The same coarse-grid-plus-bisection method as ``aspects.py``/``stations.py``/
``ingresses.py``, mirrored rather than imported.** ``_GRID_STEP`` and
``_BISECTION_ITERATIONS`` below carry the same values and the same
justification as those modules' own constants of the same name (the Moon's
sweep rate, the fastest of any body this project scans, stays well above the
grid's cadence, so no crossing is ever hidden inside a single grid step, and
a fixed halving count bounds both runtime and precision regardless of the
input interval's width).

**A signed offset from each target, wrapped to ``(-180, 180]``, mirrors
``aspects.py``'s/``ingresses.py``'s own ``_normalize_signed``.** Both targets
(0 and 180 degrees) need the same antipodal-wrap guard
(``abs(d1 - d0) < HALF_CIRCLE``) ``ingresses.py`` applies to its own cusp
scan: scanning target 0 (new moon) would otherwise misfire at the true
full-moon instant, where the wrapped offset jumps +180 to -180, and
vice versa for target 180 (full moon) at the true new-moon instant.

**Body-id lookup reads ``swisseph`` directly, never ``_TRANSIT_BODY_IDS``.**
``core/transits/aspects.py``'s ``_TRANSIT_BODY_IDS`` table deliberately never
carries the Moon (the transiting Moon is never a valid
``config.bodies.fast``/``slow`` entry) -- this module needs the Moon
specifically, so it imports ``swisseph`` and reads ``swe.SUN``/``swe.MOON``
directly instead.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

import swisseph as swe

from core.ephemeris.chart import _house_for_longitude
from core.ephemeris.positions import FULL_CIRCLE, HALF_CIRCLE, _calc_body, _julian_day_ut
from core.types.chart import NatalChart
from core.types.transits import Lunation

__all__ = ["find_lunations"]

#: Sampling cadence for the coarse pre-scan -- mirrors
#: ``core/transits/aspects.py``/``core/transits/stations.py``/
#: ``core/transits/ingresses.py``'s own ``_GRID_STEP`` (see this module's
#: docstring for why the value is safe to reuse unchanged here).
_GRID_STEP = timedelta(hours=6)

#: Fixed halving count for every bisection -- mirrors
#: ``core/transits/aspects.py``/``core/transits/stations.py``/
#: ``core/transits/ingresses.py``'s own ``_BISECTION_ITERATIONS``.
_BISECTION_ITERATIONS = 40

_ZERO_OFFSET = timedelta(0)

_NEW_MOON = "new_moon"
_FULL_MOON = "full_moon"

#: The two fixed Delta-lambda targets this module ever scans, and the
#: Lunation ``kind`` each one produces -- never configurable (see the module
#: docstring).
_TARGETS: tuple[tuple[str, Decimal], ...] = (
    (_NEW_MOON, Decimal(0)),
    (_FULL_MOON, Decimal(180)),
)


def find_lunations(
    natal_chart: NatalChart,
    month_start_utc: datetime,
    month_end_utc: datetime,
) -> tuple[Lunation, ...]:
    """Every new moon and full moon within ``[month_start_utc, month_end_utc)``.

    Tracks Delta-lambda = (Moon longitude - Sun longitude) mod 360 degrees on
    the same coarse grid ``aspects.py``/``stations.py``/``ingresses.py`` use,
    bisecting each forward crossing of 0 degrees (new moon) or 180 degrees
    (full moon) to sub-second precision. Each located instant's Moon
    longitude is resolved to a natal house via
    ``core/ephemeris/chart.py``'s ``_house_for_longitude``, against
    ``natal_chart.houses``.

    Zero or two Lunations of one kind in a month is a normal outcome,
    recorded as found, never an error.

    Deterministic: identical arguments produce an identical output tuple
    every call -- no clock, I/O or randomness is consulted.

    Raises:
        ValueError: either boundary is not timezone-aware UTC, or
            ``month_start_utc`` is not strictly before ``month_end_utc``.
        EphemerisIntegrityError: the Sun's or Moon's position was not
            confirmed as coming from the Swiss Ephemeris (propagated from
            ``core.ephemeris.positions._calc_body``).
    """
    _require_utc_interval(month_start_utc, month_end_utc)

    cusp_longitudes = [cusp.longitude for cusp in natal_chart.houses]
    grid_times = _build_grid(month_start_utc, month_end_utc)
    delta_lambdas = [_delta_lambda_at(instant) for instant in grid_times]

    records: list[Lunation] = []
    for kind, target in _TARGETS:
        offsets = [_signed_offset(delta_lambda, target) for delta_lambda in delta_lambdas]

        def offset_at(instant: datetime, target: Decimal = target) -> Decimal:
            return _signed_offset(_delta_lambda_at(instant), target)

        for index in range(len(grid_times) - 1):
            t0, t1 = grid_times[index], grid_times[index + 1]
            d0, d1 = offsets[index], offsets[index + 1]

            crossed_at: datetime | None = None
            if d1 == 0:
                crossed_at = t1
            elif d0 != 0 and (d0 > 0) != (d1 > 0) and abs(d1 - d0) < HALF_CIRCLE:
                # The ``abs(d1 - d0) < HALF_CIRCLE`` guard rules out the
                # *other* place a wrapped ``(-180, 180]`` signed offset flips
                # sign between two samples: the point antipodal to this
                # target, which every month passes through once per synodic
                # month relative to a given target. A genuine crossing moves
                # the offset only a small amount (bounded by Delta-lambda's
                # motion over one ``_GRID_STEP``) across zero; the antipodal
                # wrap jumps by nearly 360 degrees instead -- mirrors the
                # same guard ``ingresses.py`` documents, needed here for
                # BOTH targets (see the module docstring: scanning target 0
                # would otherwise misfire at the true full-moon instant, and
                # vice versa for target 180 at the true new-moon instant).
                crossed_at = _bisect(offset_at, t0, t1)

            # `grid_times` (``_build_grid``) appends ``month_end_utc`` itself
            # as a final probe point, purely to catch a crossing hiding in
            # the last partial grid step -- but the analyzed interval is
            # half-open, ``[month_start_utc, month_end_utc)``, and
            # ``month_end_utc`` itself is never inside it. Guarded out here
            # exactly like ``stations.py``/``ingresses.py``'s own boundary
            # fix.
            if crossed_at is not None and crossed_at < month_end_utc:
                moon_longitude = _calc_body(_julian_day_ut(crossed_at), swe.MOON)[0]
                natal_house = _house_for_longitude(moon_longitude, cusp_longitudes)
                records.append(
                    Lunation(
                        kind=kind,
                        occurred_at=crossed_at,
                        longitude=moon_longitude,
                        natal_house=natal_house,
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
    ``core/transits/aspects.py``/``core/transits/stations.py``/
    ``core/transits/ingresses.py``'s own ``_build_grid`` (a crossing in the
    last partial grid step before the month closes must not be missed)."""
    times = []
    instant = start
    while instant < end:
        times.append(instant)
        instant += _GRID_STEP
    times.append(end)
    return times


def _delta_lambda_at(instant: datetime) -> Decimal:
    """(Moon longitude - Sun longitude) mod 360 degrees at ``instant``."""
    jd_ut = _julian_day_ut(instant)
    sun_longitude = _calc_body(jd_ut, swe.SUN)[0]
    moon_longitude = _calc_body(jd_ut, swe.MOON)[0]
    normalized = (moon_longitude - sun_longitude) % FULL_CIRCLE
    if normalized < 0:
        normalized += FULL_CIRCLE
    return normalized


def _normalize_signed(value: Decimal) -> Decimal:
    """``value`` wrapped into ``(-180, 180]`` -- mirrors
    ``core/transits/aspects.py``'s own ``_normalize_signed``."""
    normalized = value % FULL_CIRCLE
    if normalized < 0:
        normalized += FULL_CIRCLE
    if normalized > HALF_CIRCLE:
        normalized -= FULL_CIRCLE
    return normalized


def _signed_offset(delta_lambda: Decimal, target: Decimal) -> Decimal:
    """The signed distance from ``target``: 0 exactly on the target, smooth
    (no kink) through 0 -- mirrors ``core/transits/aspects.py``'s/
    ``core/transits/ingresses.py``'s own ``_signed_offset``."""
    return _normalize_signed(delta_lambda - target)


def _bisect(f: Callable[[datetime], Decimal], lo: datetime, hi: datetime) -> datetime:
    """Standard bisection for a continuous, sign-changing ``f`` on
    ``[lo, hi]`` -- mirrors ``core/transits/aspects.py``/
    ``core/transits/stations.py``/``core/transits/ingresses.py``'s own
    ``_bisect``. The caller guarantees ``f(lo)`` and ``f(hi)`` either are
    zero or have opposite signs -- that guarantee is the sign-change checks
    in ``find_lunations`` before this is ever called."""
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
