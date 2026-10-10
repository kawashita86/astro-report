"""Pure result shapes for synastry and the midpoint composite (Story 11.4).

They are separate from ``NatalChart`` on purpose: a synastry aspect has no
applying flag (two static charts), a composite aspect carries ``applying`` as
``None`` rather than a guessed boolean, and a composite has nullable angles and
houses when either birth time is unknown. Sharing the natal types would make
those absences unrepresentable or silently wrong. Plain data, no computation;
the arithmetic lives in ``core/synastry/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.types.chart import HouseCusp

__all__ = [
    "CompositeAspect",
    "CompositeChart",
    "CompositePlanet",
    "InterAspect",
    "OverlayEntry",
]


@dataclass(frozen=True)
class InterAspect:
    """One aspect between a point of subject A and a point of subject B."""

    body_a: str
    body_b: str
    aspect: str
    orb: Decimal


@dataclass(frozen=True)
class OverlayEntry:
    """Which house of the other subject's chart ``body`` falls in."""

    body: str
    house: int


@dataclass(frozen=True)
class CompositePlanet:
    """A composite body: the midpoint of the two subjects' longitudes.

    ``house`` is ``None`` whenever the composite has no houses (either birth
    time unknown).
    """

    name: str
    longitude: Decimal
    sign: str
    degree: Decimal
    house: int | None


@dataclass(frozen=True)
class CompositeAspect:
    """A composite aspect within the natal orb. ``applying`` is always
    ``None``: a composite is a static construct with no motion."""

    body1: str
    body2: str
    aspect: str
    orb: Decimal
    applying: None


@dataclass(frozen=True)
class CompositeChart:
    """The midpoint composite. ``ascendant``, ``midheaven`` and ``houses`` are
    ``None`` when either subject's birth time is unknown."""

    ascendant: Decimal | None
    midheaven: Decimal | None
    planets: tuple[CompositePlanet, ...]
    houses: tuple[HouseCusp, ...] | None
    aspects: tuple[CompositeAspect, ...]
