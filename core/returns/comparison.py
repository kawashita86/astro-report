"""A solar return read against the natal chart.

The return chart has its own angles and cusps; what the Italian reading wants
is where they fall in the natal houses and which natal points the return
touches. Everything is built from the synastry helpers (placement in houses,
point-against-point aspects): a return is two static charts, so no applying
flag. Natal houses are required, so this only exists for a known birth time.
"""

from __future__ import annotations

from decimal import Decimal

from core.ephemeris.chart import _house_for_longitude
from core.synastry.inter_aspects import inter_aspects, known_points
from core.synastry.overlays import overlay
from core.types.chart import NatalChart
from core.types.returns import RsToNatalAspect, SolarReturnComparison

__all__ = ["compare_to_natal"]


def compare_to_natal(
    return_chart: NatalChart, natal_chart: NatalChart, orb_limit: Decimal
) -> SolarReturnComparison:
    """Place the return chart in the natal houses and aspect it to the natal chart."""
    cusps = [cusp.longitude for cusp in sorted(natal_chart.houses, key=lambda c: c.number)]
    placements = overlay(
        tuple((planet.name, planet.longitude) for planet in return_chart.planets),
        natal_chart.houses,
    )
    assert placements is not None  # a known-time natal chart always has houses
    aspects = inter_aspects(known_points(return_chart), known_points(natal_chart), orb_limit)
    return SolarReturnComparison(
        rs_ascendant_in_natal_house=_house_for_longitude(return_chart.ascendant, cusps),
        rs_planets_in_natal_houses=placements,
        rs_to_natal_aspects=tuple(
            RsToNatalAspect(
                rs_body=found.body_a, natal_body=found.body_b, aspect=found.aspect, orb=found.orb
            )
            for found in aspects
        ),
    )
