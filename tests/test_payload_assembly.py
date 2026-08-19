"""``assemble_payload()`` -- one test per row of the story's I/O & Edge-Case
Matrix, plus the properties those rows imply: purity/determinism and frozen
dataclasses.

Uses the real shipped ``data/computation.toml``/``data/sections.toml`` (via
``load_computation_config()``/``load_sections_config()``) rather than
hand-built configs -- Story 3.6's declared goal is that this mapping is
data, not code, so exercising the actual shipped file is the version of this
test that would actually catch a `data/sections.toml` regression. Domain
Profiles, the Natal Chart and every Transit Event are still hand-built
fixtures (mirrors ``tests/test_domain_profiles.py``'s own technique) --
``assemble_payload()`` is pure and needs no ephemeris, so nothing here calls
into ``core/ephemeris/``.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.payload.assemble import assemble_payload
from core.types.chart import HouseCusp, HouseRuler, NatalChart
from core.types.domains import (
    AmoreProfile,
    BenessereProfile,
    DenaroProfile,
    DomainHouse,
    DomainPlanet,
    DomainProfiles,
    LavoroProfile,
)
from core.types.payload import Payload, SectionPayload
from core.types.transits import (
    Ingress,
    Lunation,
    StandingRetrograde,
    Station,
    TransitAspectEvent,
)
from shell.computation import load_computation_config
from shell.sections import load_sections_config

_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()

# `_CONFIG.bodies` (the shipped `data/computation.toml`): fast = sun,
# mercury, venus, mars; slow = jupiter, saturn, uranus, neptune, pluto.


def _chart() -> NatalChart:
    houses = tuple(HouseCusp(number=n, longitude=Decimal((n - 1) * 30)) for n in range(1, 13))
    return NatalChart(
        ascendant=houses[0].longitude,
        midheaven=houses[9].longitude,
        planets=(),
        houses=houses,
        aspects=(),
    )


def _dummy_planet(name: str) -> DomainPlanet:
    return DomainPlanet(name=name, sign="aries", house=1, aspects=())


def _dummy_house(number: int) -> DomainHouse:
    return DomainHouse(
        number=number,
        sign="aries",
        planets=(),
        ruler=HouseRuler(
            house=number,
            sign="aries",
            traditional_ruler="mars",
            modern_ruler="mars",
            co_ruler=None,
        ),
        aspects=(),
    )


def _profiles() -> DomainProfiles:
    return DomainProfiles(
        amore=AmoreProfile(
            venus=_dummy_planet("venus"),
            mars=_dummy_planet("mars"),
            house_5=_dummy_house(5),
            house_7=_dummy_house(7),
            moon=_dummy_planet("moon"),
        ),
        lavoro=LavoroProfile(
            house_10=_dummy_house(10), house_6=_dummy_house(6), house_2=_dummy_house(2)
        ),
        denaro=DenaroProfile(
            house_2=_dummy_house(2),
            house_8=_dummy_house(8),
            venus=_dummy_planet("venus"),
            jupiter=_dummy_planet("jupiter"),
            saturn=_dummy_planet("saturn"),
        ),
        benessere=BenessereProfile(
            ascendant=_dummy_house(1),
            house_6=_dummy_house(6),
            mars=_dummy_planet("mars"),
            saturn=_dummy_planet("saturn"),
            moon=_dummy_planet("moon"),
        ),
    )


_CHART = _chart()
_PROFILES = _profiles()

_T0 = datetime(2024, 6, 5, tzinfo=UTC)
_T1 = datetime(2024, 6, 10, tzinfo=UTC)

# --- One of each event kind, chosen to exercise distinct match patterns ----

#: Slow-body aspect to a natal point energia_generale lists -- matches
#: energia_generale (aspect_bodies="slow") and consiglio_finale only: no
#: domain Section's aspect_natal_points names "sun".
_ASPECT_ENERGIA_ONLY = TransitAspectEvent(
    transiting_body="jupiter",
    natal_point="sun",
    aspect="trine",
    perfected_at=_T0,
    never_perfected=False,
    orb_entry_at=_T0,
    orb_exit_at=_T1,
)

#: Fast-body aspect to "venus" -- matches amore (aspect_bodies=None, any
#: body) and consiglio_finale only. Not energia_generale: aspect_bodies is
#: "slow" there and "venus" (transiting) is a fast body.
_ASPECT_AMORE_ONLY = TransitAspectEvent(
    transiting_body="venus",
    natal_point="venus",
    aspect="conjunction",
    perfected_at=None,
    never_perfected=True,
    orb_entry_at=_T0,
    orb_exit_at=None,
)

#: Fast-body aspect to "saturn" -- "saturn" is named by lavoro, denaro and
#: benessere's aspect_natal_points, none of which restrict aspect_bodies, so
#: this one event matches three domain Sections at once plus consiglio_finale.
_ASPECT_MULTI_DOMAIN = TransitAspectEvent(
    transiting_body="mars",
    natal_point="saturn",
    aspect="square",
    perfected_at=_T0,
    never_perfected=False,
    orb_entry_at=_T0,
    orb_exit_at=_T1,
)

#: Matrix row "Event matching no Section's filter": a fast-body Aspect to a
#: natal point no Section's aspect_natal_points names.
_ASPECT_NO_MATCH = TransitAspectEvent(
    transiting_body="mars",
    natal_point="pluto",
    aspect="opposition",
    perfected_at=_T0,
    never_perfected=False,
    orb_entry_at=_T0,
    orb_exit_at=_T1,
)

#: Retrograde Station -- matches energia_generale (retrogrades=true) and
#: consiglio_finale only; no domain Section sets retrogrades=true.
_STATION_RETROGRADE = Station(
    body="mercury", direction="retrograde", station_at=_T0, longitude=Decimal("10.0")
)

#: Direct Station -- energia_generale's own filter requires
#: direction=="retrograde", so this matches consiglio_finale only.
_STATION_DIRECT = Station(
    body="mars", direction="direct", station_at=_T0, longitude=Decimal("50.0")
)

#: StandingRetrograde -- matches energia_generale and consiglio_finale only.
_STANDING_RETROGRADE = StandingRetrograde(
    body="saturn", retrograde_start_utc=_T0, retrograde_end_utc=_T1
)

#: Matrix row "Ingress crossing counted from either side": house_departed=4
#: is only in energia_generale's houses [1,4,7,10]; house_entered=5 is only
#: in amore's houses [5,7]. `saturn` (slow) satisfies both Sections'
#: house_bodies (energia_generale="slow", amore=None/any). This single
#: Ingress must land in both energia_generale.ingresses (via the departed
#: side) and amore.ingresses (via the entered side).
_INGRESS_EITHER_SIDE = Ingress(
    body="saturn", house_departed=4, house_entered=5, crossed_at=_T0
)

#: Matrix row "Event matching no Section's filter", Ingress flavor: neither
#: house 3 nor house 9 appears in any Section's houses list (union of all
#: five domain/energia_generale houses lists is {1,2,4,5,6,7,8,10}).
_INGRESS_NO_MATCH = Ingress(body="venus", house_departed=3, house_entered=9, crossed_at=_T0)

#: House matches but body doesn't: house 4 is in energia_generale's houses
#: [1,4,7,10], but energia_generale's house_bodies="slow" excludes `mercury`
#: (a fast body). House 11 (the other side of this crossing) is in no
#: Section's houses list, so this event must be excluded from every domain
#: Section -- energia_generale via the body filter, the rest via the house
#: filter -- and present only in consiglio_finale.
_INGRESS_HOUSE_MATCH_BODY_MISMATCH = Ingress(
    body="mercury", house_departed=4, house_entered=11, crossed_at=_T0
)

#: Lunation -- no Section names Lunations specifically; matches
#: consiglio_finale only (include_all_events).
_LUNATION = Lunation(kind="new_moon", occurred_at=_T0, longitude=Decimal("15.0"), natal_house=3)


def _assemble() -> Payload:
    return assemble_payload(
        _CHART,
        _PROFILES,
        (
            _ASPECT_ENERGIA_ONLY,
            _ASPECT_AMORE_ONLY,
            _ASPECT_MULTI_DOMAIN,
            _ASPECT_NO_MATCH,
        ),
        (
            _STATION_RETROGRADE,
            _STATION_DIRECT,
            _STANDING_RETROGRADE,
        ),
        (
            _INGRESS_EITHER_SIDE,
            _INGRESS_NO_MATCH,
            _INGRESS_HOUSE_MATCH_BODY_MISMATCH,
        ),
        (_LUNATION,),
        _CONFIG,
        _SECTIONS_CONFIG,
    )


# --- Matrix row: full month, all event kinds present ------------------------


def test_full_month_each_section_receives_exactly_the_slice_its_spec_matches() -> None:
    payload = _assemble()

    assert isinstance(payload, Payload)

    # energia_generale: energia-only aspect, multi-domain aspect (natal
    # point "saturn" is not in its aspect_natal_points list, so NOT this
    # one), retrograde Station, StandingRetrograde, the either-side Ingress
    # (departed side, house 4).
    energia = payload.energia_generale
    assert energia.profile is None
    assert energia.aspects == (_ASPECT_ENERGIA_ONLY,)
    assert energia.stations == (_STATION_RETROGRADE,)
    assert energia.standing_retrogrades == (_STANDING_RETROGRADE,)
    assert energia.ingresses == (_INGRESS_EITHER_SIDE,)
    assert energia.lunations == ()

    # amore: its own aspect, plus the either-side Ingress via its entered
    # side (house 5). No Station/StandingRetrograde: retrogrades=False.
    amore = payload.amore
    assert amore.profile is _PROFILES.amore
    assert amore.aspects == (_ASPECT_AMORE_ONLY,)
    assert amore.stations == ()
    assert amore.standing_retrogrades == ()
    assert amore.ingresses == (_INGRESS_EITHER_SIDE,)
    assert amore.lunations == ()

    # lavoro, denaro, benessere: each picks up the multi-domain aspect
    # (natal point "saturn"), nothing else from this fixture set.
    lavoro = payload.lavoro
    assert lavoro.profile is _PROFILES.lavoro
    assert lavoro.aspects == (_ASPECT_MULTI_DOMAIN,)
    assert lavoro.stations == ()
    assert lavoro.standing_retrogrades == ()
    assert lavoro.ingresses == ()

    denaro = payload.denaro
    assert denaro.profile is _PROFILES.denaro
    assert denaro.aspects == (_ASPECT_MULTI_DOMAIN,)
    assert denaro.stations == ()
    assert denaro.standing_retrogrades == ()
    assert denaro.ingresses == ()

    benessere = payload.benessere
    assert benessere.profile is _PROFILES.benessere
    assert benessere.aspects == (_ASPECT_MULTI_DOMAIN,)
    assert benessere.stations == ()
    assert benessere.standing_retrogrades == ()
    assert benessere.ingresses == ()

    # consiglio_finale: include_all_events=true -- every event, unfiltered.
    consiglio = payload.consiglio_finale
    assert consiglio.profile is None
    assert consiglio.aspects == (
        _ASPECT_ENERGIA_ONLY,
        _ASPECT_AMORE_ONLY,
        _ASPECT_MULTI_DOMAIN,
        _ASPECT_NO_MATCH,
    )
    assert consiglio.stations == (_STATION_RETROGRADE, _STATION_DIRECT)
    assert consiglio.standing_retrogrades == (_STANDING_RETROGRADE,)
    assert consiglio.ingresses == (
        _INGRESS_EITHER_SIDE,
        _INGRESS_NO_MATCH,
        _INGRESS_HOUSE_MATCH_BODY_MISMATCH,
    )
    assert consiglio.lunations == (_LUNATION,)


# --- Matrix row: Ingress crossing counted from either side ------------------


def test_ingress_crossing_is_counted_toward_a_section_listing_either_house() -> None:
    payload = _assemble()

    assert _INGRESS_EITHER_SIDE in payload.energia_generale.ingresses  # house 4 (departed)
    assert _INGRESS_EITHER_SIDE in payload.amore.ingresses  # house 5 (entered)
    # Not counted toward Sections that list neither house.
    assert _INGRESS_EITHER_SIDE not in payload.lavoro.ingresses
    assert _INGRESS_EITHER_SIDE not in payload.denaro.ingresses
    assert _INGRESS_EITHER_SIDE not in payload.benessere.ingresses


# --- Matrix row: event matching no Section's filter --------------------------


def test_an_ingress_whose_house_matches_but_whose_body_doesnt_is_excluded() -> None:
    """House 4 is in energia_generale's `houses=[1,4,7,10]`, but its
    `house_bodies="slow"` excludes `mercury` -- the house filter alone is
    not enough to match; the body filter must also pass."""
    payload = _assemble()

    assert _INGRESS_HOUSE_MATCH_BODY_MISMATCH not in payload.energia_generale.ingresses
    assert _INGRESS_HOUSE_MATCH_BODY_MISMATCH in payload.consiglio_finale.ingresses


def test_an_event_matching_no_domain_filter_is_absent_everywhere_but_consiglio_finale() -> None:
    payload = _assemble()

    for name in ("energia_generale", "amore", "lavoro", "denaro", "benessere"):
        section: SectionPayload = getattr(payload, name)
        assert _ASPECT_NO_MATCH not in section.aspects
        assert _INGRESS_NO_MATCH not in section.ingresses

    assert _ASPECT_NO_MATCH in payload.consiglio_finale.aspects
    assert _INGRESS_NO_MATCH in payload.consiglio_finale.ingresses


def test_a_lunation_matches_only_consiglio_finale() -> None:
    payload = _assemble()

    for name in ("energia_generale", "amore", "lavoro", "denaro", "benessere"):
        section: SectionPayload = getattr(payload, name)
        assert section.lunations == ()

    assert payload.consiglio_finale.lunations == (_LUNATION,)


def test_a_direct_station_never_matches_energia_generales_retrograde_only_filter() -> None:
    payload = _assemble()

    assert _STATION_DIRECT not in payload.energia_generale.stations
    assert _STATION_DIRECT in payload.consiglio_finale.stations


# --- Matrix row: same inputs, two calls -> byte-identical Payload -----------


def test_assembly_is_pure_identical_inputs_produce_equal_payloads() -> None:
    first = _assemble()
    second = _assemble()

    assert first == second


def test_payload_and_section_payload_are_frozen() -> None:
    payload = _assemble()

    with pytest.raises(dataclasses.FrozenInstanceError):
        payload.amore = payload.amore  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        payload.amore.aspects = ()  # type: ignore[misc]


# --- No entry IDs, no canonical-JSON serialization, no persistence ----------


def test_payload_carries_no_entry_ids_or_serialization_machinery() -> None:
    """Story 3.6's Never bullets: no entry IDs, no canonical-JSON
    serialization here -- that is Story 3.8's job. A cheap structural check:
    SectionPayload's fields are exactly the six the story names, nothing
    extra (e.g. no "id" field)."""
    field_names = {field.name for field in dataclasses.fields(SectionPayload)}
    assert field_names == {
        "profile",
        "aspects",
        "stations",
        "standing_retrogrades",
        "ingresses",
        "lunations",
    }

    payload_field_names = {field.name for field in dataclasses.fields(Payload)}
    assert payload_field_names == {
        "energia_generale",
        "amore",
        "lavoro",
        "denaro",
        "benessere",
        "consiglio_finale",
    }
