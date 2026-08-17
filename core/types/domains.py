"""Pure result shapes for the four Domain Profiles (Story 2.5, PRD FR-6/FR-7).

Living in ``core/types/`` rather than ``shell/`` or inline in
``core/domains/profiles.py`` mirrors ``core/types/chart.py``: these types are
pure data, assembled from an already-computed ``NatalChart`` and its resolved
``HouseRuler`` tuple, with no logic beyond the dataclass machinery itself.

``DomainPlanet``/``DomainHouse`` are one shared shape per kind, reused
identically across all four Profiles (see the story's Design Notes) rather
than a bespoke shape per domain row.

The four Profile field names -- ``amore``, ``lavoro``, ``denaro``,
``benessere`` -- are Italian, lowercase, and never translated (PRD glossary
rule).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.types.chart import Aspect, HouseRuler, PlanetPosition

__all__ = [
    "AmoreProfile",
    "BenessereProfile",
    "DenaroProfile",
    "DomainHouse",
    "DomainPlanet",
    "DomainProfiles",
    "LavoroProfile",
]


@dataclass(frozen=True)
class DomainPlanet:
    """One planet's placement within a Domain Profile: its sign, house and
    the natal Aspects naming it."""

    name: str
    sign: str
    house: int
    aspects: tuple[Aspect, ...]


@dataclass(frozen=True)
class DomainHouse:
    """One house's placement within a Domain Profile: its sign (from the
    resolved ``HouseRuler``), the planets falling in it, its Ruler, and the
    natal Aspects naming any of those planets."""

    number: int
    sign: str
    planets: tuple[PlanetPosition, ...]
    ruler: HouseRuler
    aspects: tuple[Aspect, ...]


@dataclass(frozen=True)
class AmoreProfile:
    """FR-7: Venus, Mars, the 5th house, the 7th house, and the Moon."""

    venus: DomainPlanet
    mars: DomainPlanet
    house_5: DomainHouse
    house_7: DomainHouse
    moon: DomainPlanet


@dataclass(frozen=True)
class LavoroProfile:
    """FR-7: the 10th, 6th and 2nd houses -- the 10th also stands for the
    midheaven, not a separate lookup (see the story's Design Notes)."""

    house_10: DomainHouse
    house_6: DomainHouse
    house_2: DomainHouse


@dataclass(frozen=True)
class DenaroProfile:
    """FR-7: the 2nd and 8th houses, and Venus, Jupiter and Saturn."""

    house_2: DomainHouse
    house_8: DomainHouse
    venus: DomainPlanet
    jupiter: DomainPlanet
    saturn: DomainPlanet


@dataclass(frozen=True)
class BenessereProfile:
    """FR-7: the ascendant (house 1) -- not a separate lookup, see the
    story's Design Notes -- the 6th house, Mars, Saturn and the Moon."""

    ascendant: DomainHouse
    house_6: DomainHouse
    mars: DomainPlanet
    saturn: DomainPlanet
    moon: DomainPlanet


@dataclass(frozen=True)
class DomainProfiles:
    """The four Domain Profiles assembled from one Natal Chart (FR-6)."""

    amore: AmoreProfile
    lavoro: LavoroProfile
    denaro: DenaroProfile
    benessere: BenessereProfile
