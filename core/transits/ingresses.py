"""Find every crossing of a natal house cusp for each configured transiting
body across an analyzed month (Story 3.3).

Pure (AD-1): no I/O, clock, network or randomness -- only ``swisseph`` (via
``core/ephemeris/positions.py``'s shared helpers) and what is passed in
(``NatalChart``, the month's UTC interval, ``ComputationConfig``).

**The same coarse-grid-plus-bisection method as ``aspects.py``/``stations.py``,
shared via ``core/transits/_month_grid.py``.** ``_GRID_STEP``,
``_BISECTION_ITERATIONS`` and the ``_build_grid`` / ``_require_utc_interval``
/ ``_bisect`` helpers are imported from that module -- see its docstring for
why the 6-hour cadence never hides a cusp crossing and why a fixed halving
count bounds runtime and precision. Only the generic scaffolding is shared;
the per-cusp offset stays this module's own.

**A signed offset from the cusp, wrapped to ``(-180, 180]``, mirrors
``aspects.py``'s own ``_normalize_signed``.** The target is always 0 (the
cusp's own longitude), so none of ``_signed_offset``/``_target_branches``'
machinery (built for a nonzero target angle, and for aspects with a mirror
branch) is needed here -- a crossing is simply this offset's own sign
change.

**Body-id lookup is reused, not redefined.** ``_TRANSIT_BODY_IDS``
(``core/transits/aspects.py``) is imported directly -- the same accepted
cross-module import ``stations.py`` already relies on for this same name --
rather than keeping a second swisseph-constant table in sync by hand.

**Direction determines which house was departed and which was entered.**
For cusp ``n`` (``natal_chart.houses[n - 1]``), the house that begins at
that cusp is house ``n`` itself; the house immediately before it is house
``n - 1`` (wrapping to house 12 when ``n == 1``). A direct crossing (the
signed offset changes ``-`` to ``+``) departs that previous house and enters
house ``n``; a retrograde crossing (``+`` to ``-``) departs house ``n`` and
re-enters the previous house. Repeated crossings of the same cusp within the
month (a retrograde loop) are each a separate, unmerged Ingress -- exactly
the same "never merged" shape ``aspects.py``'s in-orb intervals and
``stations.py``'s Stations already use.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from core.ephemeris.positions import FULL_CIRCLE, HALF_CIRCLE, _calc_body, _julian_day_ut
from core.transits._month_grid import _bisect, _build_grid, _require_utc_interval
from core.transits.aspects import _TRANSIT_BODY_IDS
from core.types.chart import NatalChart
from core.types.computation import ComputationConfig
from core.types.transits import Ingress

__all__ = ["find_ingresses"]

_HOUSES_PER_CHART = 12


def find_ingresses(
    natal_chart: NatalChart,
    month_start_utc: datetime,
    month_end_utc: datetime,
    config: ComputationConfig,
) -> tuple[Ingress, ...]:
    """Every crossing of one of ``natal_chart``'s twelve Placidus house
    cusps within ``[month_start_utc, month_end_utc)``.

    Scans ``config.bodies.fast`` then ``config.bodies.slow`` (in that
    configured order, matching ``find_transit_aspects()``/``find_stations()``'s
    own scan order) against each of the twelve cusps in turn -- the
    transiting Moon is never a valid entry there (see
    ``ComputationConfig.bodies``'s own docstring) and so is never scanned
    here either; it never gets an Ingress (only Lunations, Story 3.4).

    For each (body, cusp) pair: samples the signed longitude offset from
    that cusp on the same coarse grid ``aspects.py``/``stations.py`` use,
    bisecting each sign change to sub-second precision into an
    :class:`Ingress`. A crossing is detected identically for direct and
    retrograde motion; repeated crossings of the same cusp within the month
    are each a separate, unmerged Ingress.

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

    records: list[Ingress] = []
    for body_name in transiting_bodies:
        if body_name not in _TRANSIT_BODY_IDS:
            raise ValueError(
                f"config.bodies names {body_name!r}, which is not a body "
                "find_ingresses() supports scanning as a transiting body "
                f"(supported: {sorted(_TRANSIT_BODY_IDS)})."
            )
        body_id = _TRANSIT_BODY_IDS[body_name]
        longitudes = [_longitude_at(body_id, instant) for instant in grid_times]

        for cusp in natal_chart.houses:
            house_entered_forward = cusp.number
            house_entered_retrograde = _previous_house(cusp.number)

            offsets = [_signed_offset(longitude, cusp.longitude) for longitude in longitudes]

            def offset_at(
                instant: datetime, body_id: int = body_id, cusp_longitude: Decimal = cusp.longitude
            ) -> Decimal:
                return _signed_offset(_longitude_at(body_id, instant), cusp_longitude)

            for index in range(len(grid_times) - 1):
                t0, t1 = grid_times[index], grid_times[index + 1]
                d0, d1 = offsets[index], offsets[index + 1]

                crossed_at: datetime | None = None
                if d1 == 0:
                    crossed_at = t1
                elif d0 != 0 and (d0 > 0) != (d1 > 0) and abs(d1 - d0) < HALF_CIRCLE:
                    # The ``abs(d1 - d0) < HALF_CIRCLE`` guard rules out the
                    # *other* place a wrapped ``(-180, 180]`` signed offset
                    # flips sign between two samples: the point antipodal to
                    # the cusp (offset +/-180), which every body passes once
                    # per revolution relative to a given cusp. A genuine
                    # cusp crossing moves the offset only a small amount
                    # (bounded by the body's motion over one ``_GRID_STEP``)
                    # across zero; the antipodal wrap jumps by nearly 360
                    # degrees instead (e.g. +179.9 to -179.9) -- mirrors the
                    # same precondition ``aspects.py``'s own
                    # ``_signed_offset`` documents (an orb well under 180
                    # degrees keeps its sign-change checks away from that
                    # same wrap point); this module has no orb gating to
                    # rely on instead, since it scans the cusp's exact
                    # target across the whole grid, not just a narrow
                    # in-orb window.
                    crossed_at = _bisect(offset_at, t0, t1)

                # `grid_times` (``_build_grid``) appends ``month_end_utc``
                # itself as a final probe point, purely to catch a crossing
                # hiding in the last partial grid step -- but the analyzed
                # interval is half-open, ``[month_start_utc, month_end_utc)``,
                # and ``month_end_utc`` itself is never inside it. Guarded
                # out here exactly like ``stations.py``'s own boundary fix.
                if crossed_at is not None and crossed_at < month_end_utc:
                    if d0 < 0:
                        # Direct crossing (offset - to +): departs the
                        # house before the cusp, enters the cusp's own
                        # house.
                        house_departed = house_entered_retrograde
                        house_entered = house_entered_forward
                    else:
                        # Retrograde crossing (offset + to -): departs the
                        # cusp's own house, re-enters the house before it.
                        house_departed = house_entered_forward
                        house_entered = house_entered_retrograde
                    records.append(
                        Ingress(
                            body=body_name,
                            house_departed=house_departed,
                            house_entered=house_entered,
                            crossed_at=crossed_at,
                        )
                    )

    return tuple(records)


def _previous_house(house_number: int) -> int:
    """The house immediately before ``house_number`` (wrapping from house 1
    back to house 12)."""
    return _HOUSES_PER_CHART if house_number == 1 else house_number - 1


def _longitude_at(body_id: int, instant: datetime) -> Decimal:
    return _calc_body(_julian_day_ut(instant), body_id)[0]


def _normalize_signed(value: Decimal) -> Decimal:
    """``value`` wrapped into ``(-180, 180]`` -- mirrors
    ``core/transits/aspects.py``'s own ``_normalize_signed``."""
    normalized = value % FULL_CIRCLE
    if normalized < 0:
        normalized += FULL_CIRCLE
    if normalized > HALF_CIRCLE:
        normalized -= FULL_CIRCLE
    return normalized


def _signed_offset(longitude: Decimal, cusp_longitude: Decimal) -> Decimal:
    """The signed distance from ``cusp_longitude``: 0 exactly on the cusp,
    smooth (no kink) through 0 -- mirrors ``core/transits/aspects.py``'s own
    ``_signed_offset``, with the target fixed at 0 (the cusp's own
    longitude) rather than a configurable aspect angle."""
    return _normalize_signed(longitude - cusp_longitude)
