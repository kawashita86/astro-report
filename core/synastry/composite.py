"""The midpoint composite of two charts.

Every composite position is the midpoint of the two on the shorter arc. An
exact opposition (arc of exactly 180 degrees) has no shorter arc -- both
halves are equally short -- so the rule is fixed: A's longitude plus 90 degrees,
normalized. Longitudes carry four decimal places, so "exact" means exactly
180.0000 and the choice is deterministic on either side of it.

House cusps are either the midpoint of each cusp pair (``midpoint_cusps``) or
supplied by the caller (``derived_from_mc``, which needs the ephemeris and so
lives in ``core/ephemeris/composite_houses.py``). Without both birth times the
composite has no angles, houses or planet houses, and its Moon is left out of
the aspects, exactly as the natal rules treat an unknown time.
"""

from __future__ import annotations

from decimal import Decimal

from core.ephemeris.chart import PLANET_BODIES, _house_for_longitude, _match_aspect, sign_and_degree
from core.ephemeris.positions import FULL_CIRCLE, HALF_CIRCLE, _normalize_decimal
from core.types.chart import HouseCusp
from core.types.synastry import CompositeAspect, CompositeChart, CompositePlanet

__all__ = ["composite_chart", "midpoint", "midpoint_cusps"]

_QUARTER_CIRCLE = Decimal(90)
_TWO = Decimal(2)
_MOON = "moon"

#: Bodies whose composite positions are reported: the planets, both nodes.
_BODY_ORDER: tuple[str, ...] = (*(name for name, _ in PLANET_BODIES), "south_node")

#: Bodies composite aspects are detected among -- the same set natal aspects use
#: (the South Node is always the True Node's exact opposite, so it adds nothing).
_ASPECT_BODY_ORDER: tuple[str, ...] = tuple(name for name, _ in PLANET_BODIES)


def midpoint(longitude_a: Decimal, longitude_b: Decimal) -> Decimal:
    """The midpoint on the shorter arc; for an exact opposition, A + 90 degrees."""
    # Decimal's % keeps the dividend's sign, so a negative difference needs
    # bringing into [0, 360) by hand.
    arc = (longitude_b - longitude_a) % FULL_CIRCLE
    if arc < 0:
        arc += FULL_CIRCLE
    if arc == HALF_CIRCLE:
        return _normalize_decimal(longitude_a + _QUARTER_CIRCLE)
    if arc < HALF_CIRCLE:
        return _normalize_decimal(longitude_a + arc / _TWO)
    return _normalize_decimal(longitude_a - (FULL_CIRCLE - arc) / _TWO)


def midpoint_cusps(
    houses_a: tuple[HouseCusp, ...], houses_b: tuple[HouseCusp, ...]
) -> tuple[HouseCusp, ...]:
    """Each house's cusp as the midpoint of the two subjects' cusps for that house."""
    by_number_b = {cusp.number: cusp.longitude for cusp in houses_b}
    return tuple(
        HouseCusp(number=cusp.number, longitude=midpoint(cusp.longitude, by_number_b[cusp.number]))
        for cusp in sorted(houses_a, key=lambda c: c.number)
    )


def composite_chart(
    bodies_a: dict[str, Decimal],
    bodies_b: dict[str, Decimal],
    angles_a: tuple[Decimal, Decimal] | None,
    angles_b: tuple[Decimal, Decimal] | None,
    houses: tuple[HouseCusp, ...] | None,
    natal_orb: Decimal,
) -> CompositeChart:
    """The composite of two subjects.

    ``bodies_*`` map every name in the planets-and-nodes order to a longitude.
    ``angles_*`` are ``(ascendant, midheaven)`` or ``None`` for an unknown
    time; ``houses`` are the composite cusps, supplied only when both times are
    known. Either set of angles missing means no composite angles, houses or
    planet houses and no Moon aspects.
    """
    both_known = angles_a is not None and angles_b is not None
    if not both_known:
        houses = None
    elif houses is None:
        raise ValueError("composite houses are required when both birth times are known.")
    cusp_longitudes = (
        [cusp.longitude for cusp in sorted(houses, key=lambda c: c.number)]
        if houses is not None
        else None
    )
    longitudes = {name: midpoint(bodies_a[name], bodies_b[name]) for name in _BODY_ORDER}

    planets = []
    for name in _BODY_ORDER:
        sign, degree = sign_and_degree(longitudes[name])
        house = (
            _house_for_longitude(longitudes[name], cusp_longitudes)
            if cusp_longitudes is not None
            else None
        )
        planets.append(
            CompositePlanet(
                name=name, longitude=longitudes[name], sign=sign, degree=degree, house=house
            )
        )

    aspect_names = [name for name in _ASPECT_BODY_ORDER if both_known or name != _MOON]
    aspects: list[CompositeAspect] = []
    for i, first in enumerate(aspect_names):
        for second in aspect_names[i + 1 :]:
            match = _match_aspect(longitudes[first], longitudes[second], natal_orb)
            if match is None:
                continue
            aspect, orb = match
            aspects.append(
                CompositeAspect(body1=first, body2=second, aspect=aspect, orb=orb, applying=None)
            )

    if both_known:
        assert angles_a is not None and angles_b is not None
        ascendant: Decimal | None = midpoint(angles_a[0], angles_b[0])
        midheaven: Decimal | None = midpoint(angles_a[1], angles_b[1])
    else:
        ascendant = midheaven = None
    return CompositeChart(
        ascendant=ascendant,
        midheaven=midheaven,
        planets=tuple(planets),
        houses=houses,
        aspects=tuple(aspects),
    )
