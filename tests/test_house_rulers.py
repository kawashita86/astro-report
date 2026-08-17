"""``resolve_house_rulers()`` -- one test per row of the story's I/O &
Edge-Case Matrix, plus the properties those rows imply: every non-divergent
sign resolves a ``None`` co_ruler, and resolution consults no clock, network
or database (purity).
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from types import MappingProxyType

import pytest

from core.domains.rulers import resolve_house_rulers
from core.types.chart import HouseCusp, HouseRuler, NatalChart
from shell.computation import load_computation_config

_CONFIG = load_computation_config()

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

_DIVERGENT_SIGNS = frozenset({"scorpio", "aquarius", "pisces"})


def _chart_with_cusps(cusps: tuple[HouseCusp, ...]) -> NatalChart:
    """A minimal, otherwise-empty ``NatalChart`` -- only ``houses`` matters
    to ``resolve_house_rulers()``."""
    return NatalChart(
        ascendant=cusps[0].longitude,
        midheaven=cusps[9].longitude,
        planets=(),
        houses=cusps,
        aspects=(),
    )


def _single_cusp_chart(sign: str) -> NatalChart:
    """A twelve-cusp chart where house 1 falls in ``sign`` and every other
    house is spaced 30 degrees apart from it (a full, valid Placidus-shaped
    cusp set is not required -- only that each cusp resolves a sign)."""
    sign_index = _ZODIAC_SIGNS.index(sign)
    base_longitude = Decimal(sign_index * 30 + 5)
    cusps = tuple(
        HouseCusp(
            number=number,
            longitude=(base_longitude + Decimal((number - 1) * 30)) % Decimal(360),
        )
        for number in range(1, 13)
    )
    return _chart_with_cusps(cusps)


# --- Matrix row: standard cusp --------------------------------------------------


def test_standard_cusp_resolves_matching_traditional_and_modern_ruler_with_no_co_ruler() -> None:
    chart = _single_cusp_chart("taurus")

    rulers = resolve_house_rulers(chart, _CONFIG)
    house_1 = rulers[0]

    assert house_1.house == 1
    assert house_1.sign == "taurus"
    assert house_1.traditional_ruler == "venus"
    assert house_1.modern_ruler == "venus"
    assert house_1.co_ruler is None


# --- Matrix row: Scorpio/Aquarius/Pisces cusp -----------------------------------


def test_scorpio_cusp_resolves_pluto_as_modern_ruler_with_mars_as_co_ruler() -> None:
    chart = _single_cusp_chart("scorpio")

    house_1 = resolve_house_rulers(chart, _CONFIG)[0]

    assert house_1.traditional_ruler == "mars"
    assert house_1.modern_ruler == "pluto"
    assert house_1.co_ruler == "mars"


def test_aquarius_cusp_resolves_uranus_as_modern_ruler_with_saturn_as_co_ruler() -> None:
    chart = _single_cusp_chart("aquarius")

    house_1 = resolve_house_rulers(chart, _CONFIG)[0]

    assert house_1.traditional_ruler == "saturn"
    assert house_1.modern_ruler == "uranus"
    assert house_1.co_ruler == "saturn"


def test_pisces_cusp_resolves_neptune_as_modern_ruler_with_jupiter_as_co_ruler() -> None:
    chart = _single_cusp_chart("pisces")

    house_1 = resolve_house_rulers(chart, _CONFIG)[0]

    assert house_1.traditional_ruler == "jupiter"
    assert house_1.modern_ruler == "neptune"
    assert house_1.co_ruler == "jupiter"


# --- Matrix row: full chart ------------------------------------------------------


def test_full_chart_resolves_twelve_rulers_ordered_by_house_1_to_12() -> None:
    cusps = tuple(
        HouseCusp(number=number, longitude=Decimal((number - 1) * 30))
        for number in range(1, 13)
    )
    chart = _chart_with_cusps(cusps)

    rulers = resolve_house_rulers(chart, _CONFIG)

    assert len(rulers) == 12
    assert [ruler.house for ruler in rulers] == list(range(1, 13))
    assert [ruler.sign for ruler in rulers] == list(_ZODIAC_SIGNS)
    assert all(isinstance(ruler, HouseRuler) for ruler in rulers)


def test_every_non_divergent_sign_resolves_a_none_co_ruler() -> None:
    cusps = tuple(
        HouseCusp(number=number, longitude=Decimal((number - 1) * 30))
        for number in range(1, 13)
    )
    chart = _chart_with_cusps(cusps)

    rulers = resolve_house_rulers(chart, _CONFIG)

    for ruler in rulers:
        if ruler.sign in _DIVERGENT_SIGNS:
            assert ruler.co_ruler is not None
        else:
            assert ruler.co_ruler is None


# --- Matrix row: assignment follows config.rulers exactly ------------------------


def test_assignment_follows_config_rulers_not_a_hardcoded_mapping() -> None:
    """A different ``ComputationConfig.rulers`` table changes the resolved
    Rulers -- proof the function reads the passed config rather than a
    hardcoded sign-to-planet mapping baked into the function itself."""
    swapped_traditional = dict(_CONFIG.rulers.traditional)
    swapped_traditional["taurus"] = "mercury"
    swapped_config = dataclasses.replace(
        _CONFIG,
        rulers=dataclasses.replace(
            _CONFIG.rulers, traditional=MappingProxyType(swapped_traditional)
        ),
    )
    chart = _single_cusp_chart("taurus")

    default_house_1 = resolve_house_rulers(chart, _CONFIG)[0]
    swapped_house_1 = resolve_house_rulers(chart, swapped_config)[0]

    assert default_house_1.traditional_ruler == "venus"
    assert swapped_house_1.traditional_ruler == "mercury"


def test_co_ruler_newly_appears_when_config_makes_a_non_divergent_sign_diverge() -> None:
    """Taurus is normally non-divergent (traditional == modern == venus, so
    ``co_ruler`` is ``None``). Swapping only ``config.rulers.modern["taurus"]``
    to a different planet must make ``co_ruler`` newly appear as the
    (unchanged) traditional Ruler -- proof ``co_ruler`` is derived by
    comparing the two config-driven lookups rather than checking the sign
    against a hardcoded Scorpio/Aquarius/Pisces list."""
    swapped_modern = dict(_CONFIG.rulers.modern)
    swapped_modern["taurus"] = "mercury"
    swapped_config = dataclasses.replace(
        _CONFIG,
        rulers=dataclasses.replace(_CONFIG.rulers, modern=MappingProxyType(swapped_modern)),
    )
    chart = _single_cusp_chart("taurus")

    default_house_1 = resolve_house_rulers(chart, _CONFIG)[0]
    swapped_house_1 = resolve_house_rulers(chart, swapped_config)[0]

    assert default_house_1.co_ruler is None
    assert swapped_house_1.traditional_ruler == "venus"
    assert swapped_house_1.modern_ruler == "mercury"
    assert swapped_house_1.co_ruler == "venus"


def test_co_ruler_becomes_none_when_config_makes_a_divergent_sign_converge() -> None:
    """Scorpio is normally divergent (traditional=mars, modern=pluto, so
    ``co_ruler`` is ``mars``). Swapping only ``config.rulers.modern["scorpio"]``
    to equal the traditional Ruler must make ``co_ruler`` become ``None`` --
    proof ``co_ruler`` tracks the config's traditional/modern comparison
    rather than a hardcoded Scorpio/Aquarius/Pisces check that would keep
    returning ``mars`` regardless of what the config says."""
    swapped_modern = dict(_CONFIG.rulers.modern)
    swapped_modern["scorpio"] = "mars"
    swapped_config = dataclasses.replace(
        _CONFIG,
        rulers=dataclasses.replace(_CONFIG.rulers, modern=MappingProxyType(swapped_modern)),
    )
    chart = _single_cusp_chart("scorpio")

    default_house_1 = resolve_house_rulers(chart, _CONFIG)[0]
    swapped_house_1 = resolve_house_rulers(chart, swapped_config)[0]

    assert default_house_1.co_ruler == "mars"
    assert swapped_house_1.traditional_ruler == "mars"
    assert swapped_house_1.modern_ruler == "mars"
    assert swapped_house_1.co_ruler is None


# --- Matrix row: purity -----------------------------------------------------------


def test_resolution_is_pure_identical_inputs_produce_byte_identical_results() -> None:
    chart = _single_cusp_chart("scorpio")

    first = resolve_house_rulers(chart, _CONFIG)
    second = resolve_house_rulers(chart, _CONFIG)

    assert first == second


def test_house_ruler_dataclass_is_frozen() -> None:
    ruler = HouseRuler(
        house=1,
        sign="taurus",
        traditional_ruler="venus",
        modern_ruler="venus",
        co_ruler=None,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        ruler.house = 2  # type: ignore[misc]
