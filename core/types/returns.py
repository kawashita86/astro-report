"""Pure result shapes for reading a solar return against the natal chart (Story 11.5).

Separate from ``NatalChart`` and ``InterAspect`` on purpose: an RS-to-natal
aspect names which chart each body belongs to (``rs_body`` / ``natal_body``)
rather than A and B, and carries no applying flag. Plain data, no computation;
the arithmetic lives in ``core/returns/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.types.synastry import OverlayEntry

__all__ = ["RsToNatalAspect", "SolarReturnComparison"]


@dataclass(frozen=True)
class RsToNatalAspect:
    """One aspect between a solar-return point and a natal point."""

    rs_body: str
    natal_body: str
    aspect: str
    orb: Decimal


@dataclass(frozen=True)
class SolarReturnComparison:
    """The return chart read against the natal chart's houses and points."""

    rs_ascendant_in_natal_house: int
    rs_planets_in_natal_houses: tuple[OverlayEntry, ...]
    rs_to_natal_aspects: tuple[RsToNatalAspect, ...]
