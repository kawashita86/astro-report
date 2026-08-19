"""``project_day_lists()`` -- one test per row of the story's I/O &
Edge-Case Matrix, plus the properties those rows imply: purity/determinism
and frozen dataclasses.

Uses the real shipped ``data/computation.toml`` (via
``load_computation_config()``) rather than a hand-built config -- mirrors
``tests/test_payload_assembly.py``'s own technique, exercising the actual
shipped ``[harmonic]`` table. ``Payload``, ``NatalChart`` and every Transit
Event are hand-built fixtures (also mirroring ``test_payload_assembly.py``):
``project_day_lists()`` is pure and needs no ephemeris, so nothing here
calls into ``core/ephemeris/``.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.payload.day_lists import project_day_lists
from core.types.chart import NatalChart, PlanetPosition
from core.types.day_lists import DayLists
from core.types.payload import Payload, SectionPayload
from core.types.transits import Lunation, StandingRetrograde, Station, TransitAspectEvent
from shell.computation import load_computation_config

_CONFIG = load_computation_config()

# `_CONFIG.harmonic` (the shipped `data/computation.toml`): harmonic_aspects
# = trine, sextile; disharmonic_aspects = square, opposition;
# harmonic_conjunction_bodies = venus, jupiter;
# disharmonic_conjunction_bodies = mars, saturn, pluto. `_CONFIG.orbs.transit`
# = 2.0 degrees.

_T0 = datetime(2024, 6, 5, tzinfo=UTC)
_T1 = datetime(2024, 6, 10, tzinfo=UTC)

#: Ascendant/midheaven shared by every chart fixture below: chosen so that,
#: for every Lunation longitude these tests use, neither forms any of the
#: five Aspects within `_CONFIG.orbs.transit` -- neutral filler targets that
#: never accidentally qualify a Lunation as favorable.
_NEUTRAL_ASCENDANT = Decimal("47")
_NEUTRAL_MIDHEAVEN = Decimal("133")


def _planet(name: str, longitude: str) -> PlanetPosition:
    return PlanetPosition(
        name=name,
        longitude=Decimal(longitude),
        sign="aries",
        degree=Decimal("0"),
        house=1,
        retrograde=False,
    )


def _chart(*planets: PlanetPosition) -> NatalChart:
    return NatalChart(
        ascendant=_NEUTRAL_ASCENDANT,
        midheaven=_NEUTRAL_MIDHEAVEN,
        planets=planets,
        houses=(),
        aspects=(),
    )


_EMPTY_CHART = _chart()


def _section(
    *,
    aspects: tuple[TransitAspectEvent, ...] = (),
    stations: tuple[Station, ...] = (),
    standing_retrogrades: tuple[StandingRetrograde, ...] = (),
    lunations: tuple[Lunation, ...] = (),
) -> SectionPayload:
    return SectionPayload(
        profile=None,
        aspects=aspects,
        stations=stations,
        standing_retrogrades=standing_retrogrades,
        ingresses=(),
        lunations=lunations,
    )


_EMPTY_SECTION = _section()


def _payload(consiglio_finale: SectionPayload) -> Payload:
    return Payload(
        energia_generale=_EMPTY_SECTION,
        amore=_EMPTY_SECTION,
        lavoro=_EMPTY_SECTION,
        denaro=_EMPTY_SECTION,
        benessere=_EMPTY_SECTION,
        consiglio_finale=consiglio_finale,
    )


def _aspect(
    *,
    transiting_body: str,
    natal_point: str = "sun",
    aspect: str,
    perfected_at: datetime | None = _T0,
    never_perfected: bool = False,
) -> TransitAspectEvent:
    return TransitAspectEvent(
        transiting_body=transiting_body,
        natal_point=natal_point,
        aspect=aspect,
        perfected_at=perfected_at,
        never_perfected=never_perfected,
        orb_entry_at=_T0,
        orb_exit_at=_T1,
    )


# --- Matrix row: Trine/sextile aspect ---------------------------------------


def test_trine_aspect_is_harmonic() -> None:
    event = _aspect(transiting_body="mercury", aspect="trine")
    payload = _payload(_section(aspects=(event,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_favorevoli == (event,)
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Square/opposition aspect -----------------------------------


def test_opposition_aspect_is_disharmonic() -> None:
    event = _aspect(transiting_body="mercury", aspect="opposition")
    payload = _payload(_section(aspects=(event,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_di_attenzione == (event,)
    assert result.giorni_favorevoli == ()


# --- Matrix row: Conjunction, Venus/Jupiter ---------------------------------


def test_venus_conjunction_is_harmonic() -> None:
    event = _aspect(transiting_body="venus", aspect="conjunction")
    payload = _payload(_section(aspects=(event,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_favorevoli == (event,)
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Conjunction, Mars/Saturn/Pluto -----------------------------


def test_saturn_conjunction_is_disharmonic() -> None:
    event = _aspect(transiting_body="saturn", aspect="conjunction")
    payload = _payload(_section(aspects=(event,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_di_attenzione == (event,)
    assert result.giorni_favorevoli == ()


# --- Matrix row: Conjunction, other body ------------------------------------


def test_mercury_conjunction_is_neutral() -> None:
    event = _aspect(transiting_body="mercury", aspect="conjunction")
    payload = _payload(_section(aspects=(event,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_favorevoli == ()
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Never-perfected aspect --------------------------------------


def test_never_perfected_harmonic_aspect_is_excluded_for_lack_of_a_date() -> None:
    event = _aspect(
        transiting_body="mercury", aspect="trine", perfected_at=None, never_perfected=True
    )
    payload = _payload(_section(aspects=(event,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_favorevoli == ()
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Lunation trine/sextile a natal point ------------------------


def test_lunation_trine_a_natal_point_is_favorable() -> None:
    chart = _chart(_planet("mercury", "0"))
    lunation = Lunation(kind="new_moon", occurred_at=_T0, longitude=Decimal("120"), natal_house=1)
    payload = _payload(_section(lunations=(lunation,)))

    result = project_day_lists(payload, chart, _CONFIG)

    assert result.giorni_favorevoli == (lunation,)
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Lunation conjunct natal Venus/Jupiter -----------------------


def test_lunation_conjunct_natal_jupiter_is_favorable() -> None:
    chart = _chart(_planet("jupiter", "200"))
    lunation = Lunation(kind="full_moon", occurred_at=_T0, longitude=Decimal("200"), natal_house=1)
    payload = _payload(_section(lunations=(lunation,)))

    result = project_day_lists(payload, chart, _CONFIG)

    assert result.giorni_favorevoli == (lunation,)
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Lunation conjunct other natal point -------------------------


def test_lunation_conjunct_natal_saturn_is_neither() -> None:
    chart = _chart(_planet("saturn", "50"))
    lunation = Lunation(kind="new_moon", occurred_at=_T0, longitude=Decimal("50"), natal_house=1)
    payload = _payload(_section(lunations=(lunation,)))

    result = project_day_lists(payload, chart, _CONFIG)

    assert result.giorni_favorevoli == ()
    assert result.giorni_di_attenzione == ()


# --- Lunation favorability: scan continues past a non-matching natal target -


def test_lunation_favorability_scans_past_a_non_matching_natal_target() -> None:
    """A chart with two natal targets: the Lunation is conjunct the first
    (`saturn`, not in the favorable-conjunction set) but trine the second
    (`jupiter`). If the scan over `_natal_targets()` stopped at the first
    non-qualifying target instead of continuing to the next, this Lunation
    would wrongly be excluded."""
    chart = _chart(_planet("saturn", "200"), _planet("jupiter", "320"))
    lunation = Lunation(kind="full_moon", occurred_at=_T0, longitude=Decimal("200"), natal_house=1)
    payload = _payload(_section(lunations=(lunation,)))

    result = project_day_lists(payload, chart, _CONFIG)

    assert result.giorni_favorevoli == (lunation,)
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Lunation with no qualifying aspect --------------------------


def test_lunation_square_every_natal_point_is_neither() -> None:
    chart = _chart(_planet("mercury", "0"))
    lunation = Lunation(kind="full_moon", occurred_at=_T0, longitude=Decimal("90"), natal_house=1)
    payload = _payload(_section(lunations=(lunation,)))

    result = project_day_lists(payload, chart, _CONFIG)

    assert result.giorni_favorevoli == ()
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Retrograde Station ------------------------------------------


def test_retrograde_station_is_attention() -> None:
    station = Station(
        body="mercury", direction="retrograde", station_at=_T0, longitude=Decimal("10")
    )
    payload = _payload(_section(stations=(station,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_di_attenzione == (station,)
    assert result.giorni_favorevoli == ()


# --- Matrix row: Direct-turn Station -----------------------------------------


def test_direct_station_is_excluded() -> None:
    station = Station(body="mars", direction="direct", station_at=_T0, longitude=Decimal("50"))
    payload = _payload(_section(stations=(station,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_favorevoli == ()
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Standing retrograde (no Station) ----------------------------


def test_standing_retrograde_is_excluded() -> None:
    standing = StandingRetrograde(body="saturn", retrograde_start_utc=_T0, retrograde_end_utc=_T1)
    payload = _payload(_section(standing_retrogrades=(standing,)))

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_favorevoli == ()
    assert result.giorni_di_attenzione == ()


# --- Matrix row: Empty month --------------------------------------------------


def test_empty_month_produces_two_empty_tuples() -> None:
    payload = _payload(_EMPTY_SECTION)

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result == DayLists(giorni_favorevoli=(), giorni_di_attenzione=())


# --- Matrix row: Determinism ---------------------------------------------------


def test_project_day_lists_is_pure_identical_inputs_produce_equal_day_lists() -> None:
    harmonic_event = _aspect(transiting_body="mercury", aspect="trine")
    disharmonic_event = _aspect(transiting_body="mars", aspect="square", natal_point="moon")
    station = Station(
        body="mercury", direction="retrograde", station_at=_T0, longitude=Decimal("10")
    )
    chart = _chart(_planet("jupiter", "200"))
    lunation = Lunation(kind="full_moon", occurred_at=_T0, longitude=Decimal("200"), natal_house=1)
    payload = _payload(
        _section(
            aspects=(harmonic_event, disharmonic_event),
            stations=(station,),
            lunations=(lunation,),
        )
    )

    first = project_day_lists(payload, chart, _CONFIG)
    second = project_day_lists(payload, chart, _CONFIG)

    assert first == second


# --- Mixed set: relative order preserved, neutral events untouched ----------


def test_relative_order_is_preserved_within_each_source_kind_and_payload_is_untouched() -> None:
    """Two harmonic aspects, out of chronological order but in a fixed
    relative order within `consiglio_finale.aspects`, must keep that same
    relative order in `giorni_favorevoli` -- membership, not re-sorting."""
    first_event = _aspect(transiting_body="venus", aspect="trine", natal_point="sun")
    second_event = _aspect(transiting_body="mercury", aspect="sextile", natal_point="moon")
    neutral_event = _aspect(transiting_body="mercury", aspect="conjunction", natal_point="mars")
    section = _section(aspects=(first_event, neutral_event, second_event))
    payload = _payload(section)

    result = project_day_lists(payload, _EMPTY_CHART, _CONFIG)

    assert result.giorni_favorevoli == (first_event, second_event)
    assert neutral_event not in result.giorni_favorevoli
    assert neutral_event not in result.giorni_di_attenzione
    # `payload` itself is untouched: the source section still carries all
    # three events, including the neutral one, unfiltered.
    assert payload.consiglio_finale.aspects == (first_event, neutral_event, second_event)


# --- Concatenation order: aspects precede lunations/stations within a tuple -


def test_aspects_precede_lunations_and_stations_in_each_output_tuple() -> None:
    """`giorni_favorevoli` is built as `favorable_aspects + favorable_lunations`
    and `giorni_di_attenzione` as `attention_aspects + attention_stations`
    (Story 3.7's Boundaries): with one qualifying entry of each kind present
    together, the aspect must come first in both tuples."""
    harmonic_event = _aspect(transiting_body="mercury", aspect="trine")
    disharmonic_event = _aspect(transiting_body="mars", aspect="square", natal_point="moon")
    station = Station(
        body="mercury", direction="retrograde", station_at=_T0, longitude=Decimal("10")
    )
    chart = _chart(_planet("jupiter", "200"))
    lunation = Lunation(kind="full_moon", occurred_at=_T0, longitude=Decimal("200"), natal_house=1)
    payload = _payload(
        _section(
            aspects=(harmonic_event, disharmonic_event),
            stations=(station,),
            lunations=(lunation,),
        )
    )

    result = project_day_lists(payload, chart, _CONFIG)

    assert result.giorni_favorevoli == (harmonic_event, lunation)
    assert result.giorni_di_attenzione == (disharmonic_event, station)


# --- Frozen dataclass ----------------------------------------------------------


def test_day_lists_is_frozen() -> None:
    result = project_day_lists(_payload(_EMPTY_SECTION), _EMPTY_CHART, _CONFIG)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.giorni_favorevoli = ()  # type: ignore[misc]
