"""Pure result shapes for a computed Natal Chart (Story 2.2, PRD FR-3/FR-4).

Living in ``core/types/`` rather than ``shell/`` or inline in
``core/ephemeris/chart.py`` lets a future ``core/`` function (Rulers, Domain
Profiles) type-hint on ``NatalChart`` without importing anything from
``shell/`` (AD-1), mirroring ``core/types/place.py`` and
``core/types/computation.py``. These types are pure data: no I/O, no
computation, no logic beyond the dataclass machinery itself -- the
computation that produces them lives in ``core/ephemeris/chart.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

__all__ = ["Aspect", "HouseCusp", "HouseRuler", "NatalChart", "PlanetPosition"]


@dataclass(frozen=True)
class PlanetPosition:
    """One computed body's position (FR-3): the ten planets, the True Node
    and the South Node all use this same shape.

    ``longitude`` is the absolute ecliptic longitude in ``[0, 360)``;
    ``sign``/``degree`` are that same longitude decomposed into a zodiac sign
    (lowercase, matching ``data/computation.toml``'s ruler-table keys) and
    the 0-30 degree position within it. ``house`` is which of the twelve
    Placidus cusps the position falls within. ``retrograde`` is derived from
    the body's daily motion at the birth instant, not stored ambiently.
    """

    name: str
    longitude: Decimal
    sign: str
    degree: Decimal
    house: int
    retrograde: bool


@dataclass(frozen=True)
class HouseCusp:
    """One of the twelve Placidus house cusps (FR-3). House 1's cusp is the
    ascendant and house 10's cusp is the midheaven -- not separate lookups
    (see ``core/ephemeris/chart.py``'s Design Notes)."""

    number: int
    longitude: Decimal


@dataclass(frozen=True)
class HouseRuler:
    """The resolved traditional and modern Ruler of one house cusp (Story
    2.4), looked up from ``ComputationConfig.rulers`` rather than a
    hardcoded sign-to-planet mapping.

    ``co_ruler`` is the traditional Ruler when it differs from the modern
    one (true today for Scorpio, Aquarius and Pisces per the configured
    tables) and ``None`` otherwise -- derived from the two Ruler fields, not
    a hardcoded sign list."""

    house: int
    sign: str
    traditional_ruler: str
    modern_ruler: str
    co_ruler: str | None


@dataclass(frozen=True)
class Aspect:
    """One natal Aspect within the configured orb (FR-3): conjunction,
    sextile, square, trine or opposition only.

    ``orb`` is an unsigned magnitude, matching how conformance fixtures
    record it; the applying/separating sign is carried separately by
    ``applying`` rather than by a signed orb.
    """

    body1: str
    body2: str
    aspect: str
    orb: Decimal
    applying: bool


@dataclass(frozen=True)
class NatalChart:
    """A complete computed Natal Chart (FR-3): ascendant, midheaven, all
    twelve Placidus cusps, every computed body's position and every natal
    Aspect within Orb.

    ``planets`` includes the ten planets, the True Node and the South Node
    (True Node longitude + 180 degrees) -- the South Node is computed and
    returned here even though it is not itself a fixture-checked
    conformance value (see the story's Design Notes).
    """

    ascendant: Decimal
    midheaven: Decimal
    planets: tuple[PlanetPosition, ...]
    houses: tuple[HouseCusp, ...]
    aspects: tuple[Aspect, ...]
