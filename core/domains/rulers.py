"""Resolve the Ruler of every house, traditional and modern (Story 2.4).

Pure (AD-1): reads only the passed ``NatalChart`` and ``ComputationConfig``,
no I/O, clock, network or randomness. Ruler assignment consults
``config.rulers.traditional``/``config.rulers.modern`` exclusively -- no
sign-to-planet mapping is hardcoded here (see the story's Design Notes).
"""

from __future__ import annotations

from decimal import Decimal

from core.types.chart import HouseRuler, NatalChart
from core.types.computation import ComputationConfig

__all__ = ["resolve_house_rulers"]

#: A local, module-private copy of the twelve zodiac signs in longitude
#: order. Deliberately duplicated rather than imported from
#: ``core/ephemeris/chart.py``'s underscore-private ``_ZODIAC_SIGNS`` -- see
#: the story's Design Notes ("Sign derivation is duplicated, not imported").
_ZODIAC_SIGNS: tuple[str, ...] = (
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
)

_DEGREES_PER_SIGN = Decimal(30)


def resolve_house_rulers(chart: NatalChart, config: ComputationConfig) -> tuple[HouseRuler, ...]:
    """Resolve the traditional and modern Ruler of all twelve house cusps.

    Each cusp's zodiac sign is derived from its longitude, then both Rulers
    are looked up from ``config.rulers`` -- never a hardcoded sign-to-planet
    mapping. ``co_ruler`` is the traditional Ruler whenever it differs from
    the modern one, derived from the two looked-up values rather than a
    hardcoded sign list.

    Returns twelve ``HouseRuler`` entries, one per cusp, ordered by
    ``house`` 1-12.
    """
    return tuple(_resolve_one(cusp.number, cusp.longitude, config) for cusp in chart.houses)


def _resolve_one(house: int, longitude: Decimal, config: ComputationConfig) -> HouseRuler:
    sign = _sign_for_longitude(longitude)
    traditional_ruler = config.rulers.traditional[sign]
    modern_ruler = config.rulers.modern[sign]
    co_ruler = traditional_ruler if traditional_ruler != modern_ruler else None
    return HouseRuler(
        house=house,
        sign=sign,
        traditional_ruler=traditional_ruler,
        modern_ruler=modern_ruler,
        co_ruler=co_ruler,
    )


def _sign_for_longitude(longitude: Decimal) -> str:
    sign_index = int(longitude // _DEGREES_PER_SIGN)
    return _ZODIAC_SIGNS[sign_index]
