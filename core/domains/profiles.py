"""Assemble the four Domain Profiles from a computed Natal Chart (Story 2.5,
PRD FR-6/FR-7).

Pure (AD-1): reads only the passed ``NatalChart`` and already-resolved
``tuple[HouseRuler, ...]``, no I/O, clock, network or randomness, and no
``ComputationConfig`` -- every value this story needs (sign, Aspects,
Rulers) is already resolved upstream (Story 2.2, Story 2.4). Domain content
follows FR-7 exactly and is a fixed rule, not configuration.
"""

from __future__ import annotations

from core.types.chart import Aspect, HouseRuler, NatalChart
from core.types.domains import (
    AmoreProfile,
    BenessereProfile,
    DenaroProfile,
    DomainHouse,
    DomainPlanet,
    DomainProfiles,
    LavoroProfile,
)

__all__ = ["assemble_domain_profiles"]


def assemble_domain_profiles(chart: NatalChart, rulers: tuple[HouseRuler, ...]) -> DomainProfiles:
    """Regroup an already-computed ``NatalChart`` (with its Rulers resolved)
    into the four Domain Profiles: ``amore``, ``lavoro``, ``denaro`` and
    ``benessere`` (FR-7).

    No new lookup, config or computation is introduced -- every field is
    assembled from planets/houses already present in ``chart``/``rulers``.
    """
    amore = AmoreProfile(
        venus=_build_planet(chart, "venus"),
        mars=_build_planet(chart, "mars"),
        house_5=_build_house(chart, rulers, 5),
        house_7=_build_house(chart, rulers, 7),
        moon=_build_planet(chart, "moon"),
    )
    lavoro = LavoroProfile(
        house_10=_build_house(chart, rulers, 10),
        house_6=_build_house(chart, rulers, 6),
        house_2=_build_house(chart, rulers, 2),
    )
    denaro = DenaroProfile(
        house_2=_build_house(chart, rulers, 2),
        house_8=_build_house(chart, rulers, 8),
        venus=_build_planet(chart, "venus"),
        jupiter=_build_planet(chart, "jupiter"),
        saturn=_build_planet(chart, "saturn"),
    )
    benessere = BenessereProfile(
        ascendant=_build_house(chart, rulers, 1),
        house_6=_build_house(chart, rulers, 6),
        mars=_build_planet(chart, "mars"),
        saturn=_build_planet(chart, "saturn"),
        moon=_build_planet(chart, "moon"),
    )
    return DomainProfiles(amore=amore, lavoro=lavoro, denaro=denaro, benessere=benessere)


def _build_planet(chart: NatalChart, name: str) -> DomainPlanet:
    """Build the ``DomainPlanet`` for the body named ``name``: its sign and
    house are read from the matching ``PlanetPosition``; its Aspects are
    ``chart.aspects`` filtered to entries naming it."""
    position = next(planet for planet in chart.planets if planet.name == name)
    return DomainPlanet(
        name=position.name,
        sign=position.sign,
        house=position.house,
        aspects=_aspects_naming(chart.aspects, {name}),
    )


def _build_house(chart: NatalChart, rulers: tuple[HouseRuler, ...], number: int) -> DomainHouse:
    """Build the ``DomainHouse`` for cusp ``number``: its sign is read from
    the matching ``HouseRuler.sign``; its planets are ``chart.planets``
    filtered by ``.house == number``; its Aspects are ``chart.aspects``
    filtered to entries naming any of those planets."""
    ruler = next(ruler for ruler in rulers if ruler.house == number)
    planets = tuple(planet for planet in chart.planets if planet.house == number)
    planet_names = {planet.name for planet in planets}
    return DomainHouse(
        number=number,
        sign=ruler.sign,
        planets=planets,
        ruler=ruler,
        aspects=_aspects_naming(chart.aspects, planet_names),
    )


def _aspects_naming(aspects: tuple[Aspect, ...], names: set[str]) -> tuple[Aspect, ...]:
    """``aspects`` filtered to entries naming any body in ``names`` (as
    either ``body1`` or ``body2``)."""
    return tuple(aspect for aspect in aspects if aspect.body1 in names or aspect.body2 in names)
