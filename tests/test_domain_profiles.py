"""``assemble_domain_profiles()`` -- one test per row of the story's I/O &
Edge-Case Matrix, plus the properties those rows imply: the four Profile
field names are the literal Italian words, ``lavoro.house_10``/
``benessere.ascendant`` are genuinely the house 10/house 1 ``DomainHouse``
(cross-checked against the same house built for another domain), and
assembly is pure.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from core.domains.profiles import assemble_domain_profiles
from core.types.chart import Aspect, HouseCusp, HouseRuler, NatalChart, PlanetPosition
from core.types.domains import DomainHouse, DomainPlanet, DomainProfiles

_ZODIAC_SIGNS = (
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

# Body -> house placement. Houses 5, 6, 7 and 8 get a planet; houses 1, 2 and
# 10 are deliberately left empty (the "Empty house" matrix row). House 8
# holds two planets (mars, jupiter) on purpose: every other Domain-relevant
# house holds at most one, which would let a `_build_house()` regression that
# collapses its `.house == number` filter down to "first match only" slip
# past every assertion undetected.
_PLANET_HOUSES = {
    "sun": 3,
    "moon": 7,
    "mercury": 4,
    "venus": 5,
    "mars": 8,
    "jupiter": 8,
    "saturn": 6,
    "uranus": 11,
    "neptune": 12,
    "pluto": 9,
    "true_node": 3,
    "south_node": 4,
}

_ASPECTS = (
    Aspect(body1="venus", body2="mars", aspect="trine", orb=Decimal("1.0"), applying=True),
    Aspect(body1="moon", body2="saturn", aspect="square", orb=Decimal("2.0"), applying=False),
    Aspect(body1="sun", body2="jupiter", aspect="conjunction", orb=Decimal("0.5"), applying=True),
    Aspect(body1="mercury", body2="pluto", aspect="opposition", orb=Decimal("3.0"), applying=True),
)


def _planets() -> tuple[PlanetPosition, ...]:
    return tuple(
        PlanetPosition(
            name=name,
            longitude=Decimal(house * 30 - 25),
            sign=_ZODIAC_SIGNS[(house - 1) % 12],
            degree=Decimal("5.0"),
            house=house,
            retrograde=False,
        )
        for name, house in _PLANET_HOUSES.items()
    )


def _rulers() -> tuple[HouseRuler, ...]:
    return tuple(
        HouseRuler(
            house=number,
            sign=_ZODIAC_SIGNS[(number - 1) % 12],
            traditional_ruler=f"traditional_{number}",
            modern_ruler=f"modern_{number}",
            co_ruler=None,
        )
        for number in range(1, 13)
    )


def _chart() -> NatalChart:
    houses = tuple(
        HouseCusp(number=number, longitude=Decimal((number - 1) * 30)) for number in range(1, 13)
    )
    return NatalChart(
        ascendant=houses[0].longitude,
        midheaven=houses[9].longitude,
        planets=_planets(),
        houses=houses,
        aspects=_ASPECTS,
    )


_CHART = _chart()
_RULERS = _rulers()


# --- Matrix row: full chart -------------------------------------------------


def test_full_chart_populates_all_four_domains() -> None:
    profiles = assemble_domain_profiles(_CHART, _RULERS)

    assert isinstance(profiles, DomainProfiles)
    assert profiles.amore.venus.name == "venus"
    assert profiles.amore.mars.name == "mars"
    assert profiles.amore.house_5.number == 5
    assert profiles.amore.house_7.number == 7
    assert profiles.amore.moon.name == "moon"

    assert profiles.lavoro.house_10.number == 10
    assert profiles.lavoro.house_6.number == 6
    assert profiles.lavoro.house_2.number == 2

    assert profiles.denaro.house_2.number == 2
    assert profiles.denaro.house_8.number == 8
    assert profiles.denaro.venus.name == "venus"
    assert profiles.denaro.jupiter.name == "jupiter"
    assert profiles.denaro.saturn.name == "saturn"

    assert profiles.benessere.ascendant.number == 1
    assert profiles.benessere.house_6.number == 6
    assert profiles.benessere.mars.name == "mars"
    assert profiles.benessere.saturn.name == "saturn"
    assert profiles.benessere.moon.name == "moon"


# --- Matrix row: planet in a domain -----------------------------------------


def test_planet_in_a_domain_carries_sign_house_and_matching_aspects() -> None:
    profiles = assemble_domain_profiles(_CHART, _RULERS)

    venus = profiles.amore.venus
    assert venus == DomainPlanet(
        name="venus",
        sign=_ZODIAC_SIGNS[(5 - 1) % 12],
        house=5,
        aspects=(_ASPECTS[0],),  # venus-mars trine
    )

    jupiter = profiles.denaro.jupiter
    assert jupiter.aspects == (_ASPECTS[2],)  # sun-jupiter conjunction


# --- Matrix row: house in a domain ------------------------------------------


def test_house_in_a_domain_carries_sign_planets_ruler_and_matching_aspects() -> None:
    profiles = assemble_domain_profiles(_CHART, _RULERS)

    house_5 = profiles.amore.house_5
    assert house_5 == DomainHouse(
        number=5,
        sign=_RULERS[4].sign,
        planets=(next(p for p in _CHART.planets if p.name == "venus"),),
        ruler=_RULERS[4],
        aspects=(_ASPECTS[0],),  # venus-mars trine, via venus
    )

    house_6 = profiles.lavoro.house_6
    assert house_6.ruler == _RULERS[5]
    assert house_6.planets == (next(p for p in _CHART.planets if p.name == "saturn"),)
    assert house_6.aspects == (_ASPECTS[1],)  # moon-saturn square, via saturn


# --- Matrix row: house with more than one planet in it -----------------------


def test_house_with_two_planets_carries_both_and_every_matching_aspect() -> None:
    """House 8 holds both mars and jupiter. `.planets` must contain both --
    not just the first match -- and `.aspects` must include Aspects naming
    either one (venus-mars trine, sun-jupiter conjunction)."""
    profiles = assemble_domain_profiles(_CHART, _RULERS)

    house_8 = profiles.denaro.house_8
    mars = next(p for p in _CHART.planets if p.name == "mars")
    jupiter = next(p for p in _CHART.planets if p.name == "jupiter")

    assert house_8.planets == (mars, jupiter)
    assert house_8.aspects == (_ASPECTS[0], _ASPECTS[2])


# --- Matrix row: empty house -------------------------------------------------


def test_empty_house_has_no_planets_and_no_aspects() -> None:
    profiles = assemble_domain_profiles(_CHART, _RULERS)

    for house in (profiles.benessere.ascendant, profiles.lavoro.house_2, profiles.lavoro.house_10):
        assert house.planets == ()
        assert house.aspects == ()


# --- Naming: literal Italian field names -------------------------------------


def test_domain_profiles_field_names_are_the_literal_italian_words() -> None:
    field_names = {field.name for field in dataclasses.fields(DomainProfiles)}
    assert field_names == {"amore", "lavoro", "denaro", "benessere"}


def test_lavoro_house_10_and_benessere_ascendant_are_the_house_10_and_house_1_domain_houses() -> (
    None
):
    profiles = assemble_domain_profiles(_CHART, _RULERS)

    assert profiles.lavoro.house_10.number == 10
    assert profiles.lavoro.house_10.ruler == _RULERS[9]

    assert profiles.benessere.ascendant.number == 1
    assert profiles.benessere.ascendant.ruler == _RULERS[0]


def test_same_house_or_planet_reused_across_domains_is_identically_assembled() -> None:
    """House 2 appears in both `lavoro` and `denaro`; house 6 in both
    `lavoro` and `benessere`; Venus in both `amore` and `denaro`; Mars and
    the Moon in both `amore` and `benessere`; Saturn in both `denaro` and
    `benessere`. Each independently-assembled occurrence must match."""
    profiles = assemble_domain_profiles(_CHART, _RULERS)

    assert profiles.lavoro.house_2 == profiles.denaro.house_2
    assert profiles.lavoro.house_6 == profiles.benessere.house_6
    assert profiles.amore.venus == profiles.denaro.venus
    assert profiles.amore.mars == profiles.benessere.mars
    assert profiles.amore.moon == profiles.benessere.moon
    assert profiles.denaro.saturn == profiles.benessere.saturn


# --- Matrix row: purity -------------------------------------------------------


def test_assembly_is_pure_identical_inputs_produce_byte_identical_results() -> None:
    first = assemble_domain_profiles(_CHART, _RULERS)
    second = assemble_domain_profiles(_CHART, _RULERS)

    assert first == second


def test_domain_profiles_dataclasses_are_frozen() -> None:
    profiles = assemble_domain_profiles(_CHART, _RULERS)

    with pytest.raises(dataclasses.FrozenInstanceError):
        profiles.amore = profiles.amore  # type: ignore[misc]
