"""The noon chart for a birth whose time is unknown (Story 11.2, API only).

Report generation stays exact-time-only; this exists so a consultation draft
can still name what a real ephemeris says about a person whose birth time is
lost. It is a separate computation, not a flag on ``compute_natal_chart``: no
ascendant, midheaven or house can be honest without a time, and a separate
result type (``TimeUnknownChart``) makes it impossible to read one off by
mistake. The body list, sign decomposition and aspect detection are the very
same functions the exact-time chart uses, so the two cannot drift.

Pure: it takes three UTC instants the shell has already derived from the local
calendar day (noon, 00:00, and the next 00:00, each with its own offset), so no
timezone work happens in ``core/``. Every position goes through ``_calc_body``,
which re-binds the verified ephemeris path to the calling thread.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from core.ephemeris.chart import PLANET_BODIES, detect_aspects, sign_and_degree
from core.ephemeris.positions import (
    HALF_CIRCLE,
    _calc_body,
    _julian_day_ut,
    _normalize_decimal,
)
from core.types.chart import TimeUnknownChart, TimeUnknownPlanet
from core.types.computation import ComputationConfig

__all__ = ["compute_time_unknown_chart"]

_MOON = "moon"


def compute_time_unknown_chart(
    noon_utc: datetime,
    day_start_utc: datetime,
    day_end_utc: datetime,
    config: ComputationConfig,
) -> TimeUnknownChart:
    """Compute the noon chart and each body's span across the local day.

    ``noon_utc`` is local noon, ``day_start_utc`` local 00:00 and
    ``day_end_utc`` the next local 00:00. Aspects use ``config.orbs.natal``,
    are measured at noon, and exclude every aspect involving the Moon.

    Raises:
        ValueError: an instant is not timezone-aware UTC, or the three are not
            ordered ``start <= noon <= end``.
        EphemerisIntegrityError: a position did not come from the Swiss
            Ephemeris.
    """
    for instant in (noon_utc, day_start_utc, day_end_utc):
        _require_utc(instant)
    if not day_start_utc <= noon_utc <= day_end_utc:
        raise ValueError("expected day_start_utc <= noon_utc <= day_end_utc.")

    noon = _positions(noon_utc)
    start = _positions(day_start_utc)
    end = _positions(day_end_utc)

    planets = [
        _planet(name, noon[name], start[name][0], end[name][0]) for name, _body_id in PLANET_BODIES
    ]
    true_node_noon, true_node_speed = noon["true_node"]
    south_noon = _normalize_decimal(true_node_noon + HALF_CIRCLE)
    planets.append(
        _planet(
            "south_node",
            (south_noon, true_node_speed),
            _normalize_decimal(start["true_node"][0] + HALF_CIRCLE),
            _normalize_decimal(end["true_node"][0] + HALF_CIRCLE),
        )
    )

    aspect_bodies = [
        (name, noon[name][0], noon[name][1]) for name, _ in PLANET_BODIES if name != _MOON
    ]
    return TimeUnknownChart(
        planets=tuple(planets),
        aspects=detect_aspects(aspect_bodies, config.orbs.natal),
    )


def _positions(instant: datetime) -> dict[str, tuple[Decimal, Decimal]]:
    jd_ut = _julian_day_ut(instant)
    return {name: _calc_body(jd_ut, body_id) for name, body_id in PLANET_BODIES}


def _planet(
    name: str,
    at_noon: tuple[Decimal, Decimal],
    from_longitude: Decimal,
    to_longitude: Decimal,
) -> TimeUnknownPlanet:
    longitude, speed = at_noon
    sign, degree = sign_and_degree(longitude)
    signs = {sign, sign_and_degree(from_longitude)[0], sign_and_degree(to_longitude)[0]}
    return TimeUnknownPlanet(
        name=name,
        longitude=longitude,
        sign=sign,
        degree=degree,
        retrograde=speed < 0,
        range_from=from_longitude,
        range_to=to_longitude,
        sign_uncertain=len(signs) > 1,
    )


def _require_utc(instant: datetime) -> None:
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
        raise ValueError(
            f"instants must be timezone-aware UTC (utcoffset() == 0); got {instant!r}."
        )
