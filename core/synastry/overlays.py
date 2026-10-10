"""House overlays: where one person's planets fall in the other's houses.

Placement uses the receiving chart's Placidus cusps, so a receiving chart with
no birth time has no houses and the overlay is ``None`` -- never an empty list,
which would read as "no planets" instead of "cannot be known".
"""

from __future__ import annotations

from decimal import Decimal

from core.ephemeris.chart import _house_for_longitude
from core.types.chart import HouseCusp
from core.types.synastry import OverlayEntry

__all__ = ["overlay"]

_ANGLES = frozenset({"ascendant", "midheaven"})


def overlay(
    bodies: tuple[tuple[str, Decimal], ...], receiving_houses: tuple[HouseCusp, ...] | None
) -> tuple[OverlayEntry, ...] | None:
    """Each of ``bodies`` placed in ``receiving_houses``, or ``None`` without houses."""
    if receiving_houses is None:
        return None
    cusps = [cusp.longitude for cusp in sorted(receiving_houses, key=lambda c: c.number)]
    return tuple(
        OverlayEntry(body=name, house=_house_for_longitude(longitude, cusps))
        for name, longitude in bodies
        if name not in _ANGLES
    )
