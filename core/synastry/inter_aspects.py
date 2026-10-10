"""Aspects between two people's charts, point against point.

Two static charts have no motion between them, so unlike a natal or transit
aspect there is no applying/separating flag. The caller decides which points a
subject contributes (a time-unknown subject has no angles and no Moon); this
module only pairs them, in a fixed A-major order so identical input always
yields identical output.
"""

from __future__ import annotations

from decimal import Decimal

from core.ephemeris.chart import _match_aspect
from core.types.chart import NatalChart, TimeUnknownChart
from core.types.synastry import InterAspect

__all__ = ["Point", "inter_aspects", "known_points", "unknown_points"]

#: A named ecliptic longitude.
Point = tuple[str, Decimal]

_MOON = "moon"


def known_points(chart: NatalChart) -> tuple[Point, ...]:
    """Every body of a known-time chart (both nodes included), then the angles."""
    bodies = tuple((planet.name, planet.longitude) for planet in chart.planets)
    return (*bodies, ("ascendant", chart.ascendant), ("midheaven", chart.midheaven))


def unknown_points(chart: TimeUnknownChart) -> tuple[Point, ...]:
    """A time-unknown chart's noon bodies without the Moon, and no angles."""
    return tuple(
        (planet.name, planet.longitude) for planet in chart.planets if planet.name != _MOON
    )


def inter_aspects(
    points_a: tuple[Point, ...], points_b: tuple[Point, ...], orb_limit: Decimal
) -> tuple[InterAspect, ...]:
    """Every (A point, B point) pair within ``orb_limit`` of a major aspect."""
    found: list[InterAspect] = []
    for name_a, longitude_a in points_a:
        for name_b, longitude_b in points_b:
            match = _match_aspect(longitude_a, longitude_b, orb_limit)
            if match is None:
                continue
            aspect, orb = match
            found.append(InterAspect(body_a=name_a, body_b=name_b, aspect=aspect, orb=orb))
    return tuple(found)
