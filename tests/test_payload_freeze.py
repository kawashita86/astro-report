"""``core/payload/freeze.py::freeze_payload()`` -- one test per row of Story
3.8's I/O & Edge-Case Matrix, plus the properties those rows imply:
purity/determinism, the total order over each tuple's canonical fields, and
that every persisted identity fact (schema version, ``computation.toml``/
``sections.toml`` version+hash, ephemeris files) survives into the frozen
dict.

Uses the real shipped ``data/computation.toml``/``data/sections.toml``/
vendored ephemeris (via ``load_computation_config()``/
``load_sections_config()``/``verify_ephemeris_identity()``) rather than
hand-built configs, mirroring ``tests/test_payload_assembly.py`` -- and
hand-built ``Payload``/``DayLists`` fixtures, since ``freeze_payload()`` is
pure and needs neither ``core/ephemeris/`` computation nor a database.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from core.ephemeris.identity import verify_ephemeris_identity
from core.payload.freeze import PAYLOAD_SCHEMA_VERSION, canonical_json_bytes, freeze_payload
from core.types.chart import Aspect, HouseRuler, PlanetPosition
from core.types.day_lists import DayLists
from core.types.domains import AmoreProfile, DomainHouse, DomainPlanet
from core.types.payload import Payload, SectionPayload
from core.types.transits import Ingress, Lunation, StandingRetrograde, Station, TransitAspectEvent
from shell.computation import load_computation_config
from shell.sections import load_sections_config

_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()
_EPHEMERIS_IDENTITY = verify_ephemeris_identity()

_T0 = datetime(2024, 6, 5, tzinfo=UTC)
_T1 = datetime(2024, 6, 10, tzinfo=UTC)

_ASPECT_1 = TransitAspectEvent(
    transiting_body="mars",
    natal_point="venus",
    aspect="trine",
    perfected_at=_T0,
    never_perfected=False,
    orb_entry_at=_T0,
    orb_exit_at=None,
)
_ASPECT_2 = TransitAspectEvent(
    transiting_body="jupiter",
    natal_point="sun",
    aspect="square",
    perfected_at=_T1,
    never_perfected=False,
    orb_entry_at=_T0,
    orb_exit_at=_T1,
)
_LUNATION = Lunation(kind="new_moon", occurred_at=_T0, longitude=Decimal("10.0"), natal_house=3)


def _empty_section(profile: object = None) -> SectionPayload:
    return SectionPayload(
        profile=profile,  # type: ignore[arg-type]
        aspects=(),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )


def _payload(consiglio: SectionPayload, *, amore: SectionPayload | None = None) -> Payload:
    return Payload(
        energia_generale=_empty_section(),
        amore=amore if amore is not None else _empty_section(),
        lavoro=_empty_section(),
        denaro=_empty_section(),
        benessere=_empty_section(),
        consiglio_finale=consiglio,
    )


def _freeze(payload: Payload, day_lists: DayLists) -> dict:
    return freeze_payload(
        payload,
        day_lists,
        config=_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


# --- Matrix row: two events with disjoint fields -----------------------------


def test_two_events_with_disjoint_fields_get_distinct_ids() -> None:
    section = SectionPayload(
        profile=None,
        aspects=(_ASPECT_1,),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(_LUNATION,),
    )
    frozen = _freeze(_payload(section), DayLists(giorni_favorevoli=(), giorni_di_attenzione=()))

    consiglio = frozen["sections"]["consiglio_finale"]
    aspect_id = consiglio["aspects"][0]["id"]
    lunation_id = consiglio["lunations"][0]["id"]

    assert aspect_id != lunation_id


# --- Matrix row: identical inputs, two calls -> byte-identical output --------


def test_freeze_payload_is_pure_two_calls_produce_byte_identical_canonical_json() -> None:
    section = SectionPayload(
        profile=None,
        aspects=(_ASPECT_1, _ASPECT_2),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(_LUNATION,),
    )
    payload = _payload(section)
    day_lists = DayLists(giorni_favorevoli=(_LUNATION,), giorni_di_attenzione=(_ASPECT_1,))

    first = _freeze(payload, day_lists)
    second = _freeze(payload, day_lists)

    assert canonical_json_bytes(first) == canonical_json_bytes(second)


# --- Entry id: a stable hash of the event's own canonical fields -------------


def test_entry_id_equals_sha256_of_its_own_canonical_kind_tagged_fields() -> None:
    section = SectionPayload(
        profile=None,
        aspects=(_ASPECT_1,),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    frozen = _freeze(_payload(section), DayLists(giorni_favorevoli=(), giorni_di_attenzione=()))

    entry = frozen["sections"]["consiglio_finale"]["aspects"][0]
    fields = {key: value for key, value in entry.items() if key != "id"}

    assert entry["id"] == hashlib.sha256(canonical_json_bytes(fields)).hexdigest()
    assert fields["kind"] == "aspect"


def test_entry_id_is_independent_of_input_order() -> None:
    """The total order is over each entry's own canonical fields, not
    insertion order -- two Payloads differing only in tuple order must
    freeze to the same entries in the same emitted order."""
    section_a = SectionPayload(
        profile=None,
        aspects=(_ASPECT_1, _ASPECT_2),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    section_b = SectionPayload(
        profile=None,
        aspects=(_ASPECT_2, _ASPECT_1),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    empty_day_lists = DayLists(giorni_favorevoli=(), giorni_di_attenzione=())

    frozen_a = _freeze(_payload(section_a), empty_day_lists)
    frozen_b = _freeze(_payload(section_b), empty_day_lists)

    assert (
        frozen_a["sections"]["consiglio_finale"]["aspects"]
        == frozen_b["sections"]["consiglio_finale"]["aspects"]
    )


def test_events_are_emitted_sorted_by_canonical_json_bytes_of_their_fields() -> None:
    section = SectionPayload(
        profile=None,
        aspects=(_ASPECT_2, _ASPECT_1),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    frozen = _freeze(_payload(section), DayLists(giorni_favorevoli=(), giorni_di_attenzione=()))

    aspects = frozen["sections"]["consiglio_finale"]["aspects"]
    fields_only = [{key: value for key, value in entry.items() if key != "id"} for entry in aspects]

    assert fields_only == sorted(fields_only, key=canonical_json_bytes)


# --- JSON-safety: Decimal -> str, datetime -> isoformat -----------------------


def test_station_fields_convert_decimal_to_string_and_datetime_to_isoformat() -> None:
    station = Station(
        body="mercury", direction="retrograde", station_at=_T0, longitude=Decimal("12.5")
    )
    section = SectionPayload(
        profile=None,
        aspects=(),
        stations=(station,),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    frozen = _freeze(_payload(section), DayLists(giorni_favorevoli=(), giorni_di_attenzione=()))

    entry = frozen["sections"]["consiglio_finale"]["stations"][0]
    assert entry["longitude"] == "12.5"
    assert entry["station_at"] == _T0.isoformat()
    assert entry["kind"] == "station"


def test_lunation_kind_collision_is_preserved_under_lunation_kind_key() -> None:
    lunation = Lunation(
        kind="full_moon", occurred_at=_T0, longitude=Decimal("200.0"), natal_house=7
    )
    section = SectionPayload(
        profile=None,
        aspects=(),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(lunation,),
    )
    frozen = _freeze(_payload(section), DayLists(giorni_favorevoli=(), giorni_di_attenzione=()))

    entry = frozen["sections"]["consiglio_finale"]["lunations"][0]
    assert entry["kind"] == "lunation"
    assert entry["lunation_kind"] == "full_moon"


def test_standing_retrograde_and_ingress_freeze_with_correct_kind_tags() -> None:
    standing = StandingRetrograde(body="saturn", retrograde_start_utc=_T0, retrograde_end_utc=_T1)
    ingress = Ingress(body="venus", house_departed=4, house_entered=5, crossed_at=_T0)
    section = SectionPayload(
        profile=None,
        aspects=(),
        stations=(),
        standing_retrogrades=(standing,),
        ingresses=(ingress,),
        lunations=(),
    )
    frozen = _freeze(_payload(section), DayLists(giorni_favorevoli=(), giorni_di_attenzione=()))

    consiglio = frozen["sections"]["consiglio_finale"]
    assert consiglio["standing_retrogrades"][0]["kind"] == "standing_retrograde"
    assert consiglio["standing_retrogrades"][0]["retrograde_start_utc"] == _T0.isoformat()
    assert consiglio["ingresses"][0]["kind"] == "ingress"
    assert consiglio["ingresses"][0]["crossed_at"] == _T0.isoformat()


def test_profile_decimals_are_converted_to_strings() -> None:
    aspect = Aspect(body1="venus", body2="mars", aspect="trine", orb=Decimal("3.25"), applying=True)
    planet = DomainPlanet(name="venus", sign="taurus", house=5, aspects=(aspect,))
    house = DomainHouse(
        number=5,
        sign="taurus",
        planets=(
            PlanetPosition(
                name="venus",
                longitude=Decimal("45.0"),
                sign="taurus",
                degree=Decimal("15.0"),
                house=5,
                retrograde=False,
            ),
        ),
        ruler=HouseRuler(
            house=5, sign="taurus", traditional_ruler="venus", modern_ruler="venus", co_ruler=None
        ),
        aspects=(aspect,),
    )
    profile = AmoreProfile(venus=planet, mars=planet, house_5=house, house_7=house, moon=planet)
    amore_section = SectionPayload(
        profile=profile,
        aspects=(),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    frozen = _freeze(
        _payload(_empty_section(), amore=amore_section),
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
    )

    frozen_profile = frozen["sections"]["amore"]["profile"]
    assert frozen_profile["venus"]["aspects"][0]["orb"] == "3.25"
    assert frozen_profile["house_5"]["planets"][0]["longitude"] == "45.0"
    assert isinstance(frozen_profile["venus"]["aspects"][0]["applying"], bool)


def test_a_section_with_no_domain_profile_freezes_profile_to_none() -> None:
    empty_day_lists = DayLists(giorni_favorevoli=(), giorni_di_attenzione=())
    frozen = _freeze(_payload(_empty_section()), empty_day_lists)

    assert frozen["sections"]["energia_generale"]["profile"] is None
    assert frozen["sections"]["consiglio_finale"]["profile"] is None


# --- Day lists get ids and the same total order too ---------------------------


def test_day_lists_events_get_ids_and_are_emitted_in_total_order() -> None:
    lunation_1 = Lunation(
        kind="new_moon", occurred_at=_T0, longitude=Decimal("1.0"), natal_house=1
    )
    lunation_2 = Lunation(
        kind="full_moon", occurred_at=_T1, longitude=Decimal("181.0"), natal_house=7
    )
    day_lists = DayLists(giorni_favorevoli=(lunation_2, lunation_1), giorni_di_attenzione=())

    frozen = _freeze(_payload(_empty_section()), day_lists)

    favorevoli = frozen["day_lists"]["giorni_favorevoli"]
    assert len(favorevoli) == 2
    assert all("id" in entry for entry in favorevoli)
    fields_only = [
        {key: value for key, value in entry.items() if key != "id"} for entry in favorevoli
    ]
    assert fields_only == sorted(fields_only, key=canonical_json_bytes)


# --- The frozen dict carries its own identity metadata -------------------------


def test_frozen_payload_carries_schema_version_and_identity_metadata() -> None:
    empty_day_lists = DayLists(giorni_favorevoli=(), giorni_di_attenzione=())
    frozen = _freeze(_payload(_empty_section()), empty_day_lists)

    assert frozen["schema_version"] == PAYLOAD_SCHEMA_VERSION
    assert frozen["computation_config_version"] == _CONFIG.version
    assert frozen["computation_config_content_hash"] == _CONFIG.content_hash
    assert frozen["sections_config_version"] == _SECTIONS_CONFIG.version
    assert frozen["sections_config_content_hash"] == _SECTIONS_CONFIG.content_hash
    assert frozen["ephemeris_files"] == [
        {"filename": file.filename, "sha256": file.sha256} for file in _EPHEMERIS_IDENTITY.files
    ]


def test_schema_version_can_be_overridden() -> None:
    frozen = freeze_payload(
        _payload(_empty_section()),
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
        config=_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
        schema_version=2,
    )

    assert frozen["schema_version"] == 2


def test_frozen_payload_has_all_six_sections() -> None:
    empty_day_lists = DayLists(giorni_favorevoli=(), giorni_di_attenzione=())
    frozen = _freeze(_payload(_empty_section()), empty_day_lists)

    assert set(frozen["sections"]) == {
        "energia_generale",
        "amore",
        "lavoro",
        "denaro",
        "benessere",
        "consiglio_finale",
    }


# --- canonical_json_bytes() itself ---------------------------------------------


def test_canonical_json_bytes_sorts_keys_and_strips_whitespace() -> None:
    assert canonical_json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_frozen_payload_round_trips_through_real_json() -> None:
    """Proves the whole tree is actually JSON-safe (no leftover Decimal or
    datetime), not merely that the pieces this file happens to assert on
    are."""
    frozen = _freeze(
        _payload(
            SectionPayload(
                profile=None,
                aspects=(_ASPECT_1,),
                stations=(
                    Station(
                        body="mars", direction="direct", station_at=_T0, longitude=Decimal("1.0")
                    ),
                ),
                standing_retrogrades=(),
                ingresses=(),
                lunations=(_LUNATION,),
            )
        ),
        DayLists(giorni_favorevoli=(_LUNATION,), giorni_di_attenzione=(_ASPECT_1,)),
    )

    round_tripped = json.loads(canonical_json_bytes(frozen))
    assert round_tripped == frozen
