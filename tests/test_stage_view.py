"""``shell/http/stage_view.py`` -- the pure view-model core behind the
stage-track / Gate-violation surfaces Story 9.5 renders. No I/O, no database:
these tests exercise every I/O & Edge-Case Matrix stage state directly
against ``build_stage_track()`` / ``stage_caption()`` / ``violation_kind_label()``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from core.ephemeris.identity import verify_ephemeris_identity
from core.gate.run import _index_entries
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.payload import Payload, SectionPayload
from core.types.transits import Ingress, Lunation, StandingRetrograde, Station, TransitAspectEvent
from shell.computation import load_computation_config
from shell.http.stage_view import (
    _ENTRY_FIELD_ORDER,
    _ENTRY_KIND_HEADINGS_IT,
    CITED_ENTRY_FIELD_LABELS,
    STAGE_NODES,
    VIOLATION_KIND_LABELS,
    build_stage_track,
    resolve_cited_entries,
    stage_caption,
    violation_kind_label,
)
from shell.runner.driver import _STAGE_SEQUENCE
from shell.sections import load_sections_config

_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()
_EPHEMERIS_IDENTITY = verify_ephemeris_identity()


def _empty_section() -> SectionPayload:
    return SectionPayload(
        profile=None, aspects=(), stations=(), standing_retrogrades=(), ingresses=(), lunations=()
    )


def _freeze(
    *,
    aspects: tuple[TransitAspectEvent, ...] = (),
    stations: tuple[Station, ...] = (),
    standing_retrogrades: tuple[StandingRetrograde, ...] = (),
    ingresses: tuple[Ingress, ...] = (),
    lunations: tuple[Lunation, ...] = (),
) -> dict[str, Any]:
    """One populated ``SectionPayload`` holding whichever cited-entry kinds a
    test needs, frozen through the real ``freeze_payload()`` -- mirrors
    ``tests/test_gate_run.py``'s own ``_freeze()`` fixture."""
    populated = SectionPayload(
        profile=None,
        aspects=aspects,
        stations=stations,
        standing_retrogrades=standing_retrogrades,
        ingresses=ingresses,
        lunations=lunations,
    )
    payload = Payload(
        energia_generale=populated,
        amore=_empty_section(),
        lavoro=_empty_section(),
        denaro=_empty_section(),
        benessere=_empty_section(),
        consiglio_finale=_empty_section(),
    )
    return freeze_payload(
        payload,
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
        config=_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


def _find_id(entries: list[dict[str, Any]], **match: Any) -> str:
    for entry in entries:
        if all(entry.get(key) == value for key, value in match.items()):
            entry_id = entry["id"]
            assert isinstance(entry_id, str)
            return entry_id
    raise AssertionError(f"no entry in {entries!r} matches {match!r}")


# --- STAGE_NODES <-> _STAGE_SEQUENCE binding --------------------------------------


def test_stage_nodes_is_bound_to_the_stage_sequence_by_length_and_order() -> None:
    """A seventh stage registered in the driver cannot ship without a label
    here -- this is exactly the binding the Code Map calls for."""
    assert len(STAGE_NODES) == len(_STAGE_SEQUENCE)
    assert tuple(key for key, _label in STAGE_NODES) == _STAGE_SEQUENCE


def test_every_stage_node_has_a_non_empty_italian_label() -> None:
    for _key, label in STAGE_NODES:
        assert isinstance(label, str)
        assert label != ""


# --- build_stage_track: the I/O Matrix's stage states -----------------------------


def test_run_just_started_has_the_first_node_active_and_the_rest_pending() -> None:
    track = build_stage_track(None, failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "active",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
    ]


def test_mid_run_has_the_completed_nodes_done_and_the_next_one_active() -> None:
    track = build_stage_track("transits_ready", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "active",
        "pending",
        "pending",
        "pending",
    ]


def test_payload_ready_has_the_bozza_node_active() -> None:
    track = build_stage_track("payload_ready", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "done",
        "active",
        "pending",
        "pending",
    ]


def test_gate_running_has_the_verifica_node_active() -> None:
    track = build_stage_track("draft_ready", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "done",
        "done",
        "active",
        "pending",
    ]


def test_gate_passed_has_the_esportazione_node_active() -> None:
    track = build_stage_track("gate_passed", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "done",
        "done",
        "done",
        "active",
    ]


def test_exported_has_every_node_done() -> None:
    track = build_stage_track("exported", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == ["done"] * 6


def test_a_gate_failure_marks_the_verifica_node_failed() -> None:
    track = build_stage_track("draft_ready", failed=True, gate_failed=True)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "done",
        "done",
        "failed",
        "pending",
    ]


def test_a_non_gate_terminal_failure_marks_the_first_incomplete_node_failed() -> None:
    """E.g. a run that failed at ``natal_ready`` (``run.stage is None``) --
    ``gate_failed`` does not change which node is marked failed, only the
    caption (see the ``stage_caption`` tests below)."""
    track = build_stage_track(None, failed=True, gate_failed=False)

    assert [node["state"] for node in track] == [
        "failed",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
    ]


def test_node_keys_and_labels_match_stage_nodes_regardless_of_state() -> None:
    track = build_stage_track("payload_ready", failed=False, gate_failed=False)

    assert [(node["key"], node["label"]) for node in track] == list(STAGE_NODES)


# --- stage_caption: the I/O Matrix's captions --------------------------------------


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        (None, "Calcolo del tema natale"),
        ("natal_ready", "Ricerca dei transiti"),
        ("transits_ready", "Assemblaggio del Payload"),
        ("payload_ready", "Generazione della bozza in corso, attendere"),
        ("draft_ready", "Verifica di fondatezza"),
        ("gate_passed", "Pronto per l'esportazione"),
    ],
)
def test_the_running_caption_names_the_active_stage(stage: str | None, expected: str) -> None:
    caption = stage_caption(stage, failed=False, gate_failed=False, failure_reason=None)

    assert caption == expected


def test_the_exported_caption_is_the_true_terminal_phrase() -> None:
    caption = stage_caption("exported", failed=False, gate_failed=False, failure_reason=None)

    assert caption == "Esportato"


def test_a_gate_failure_caption_is_verifica_non_superata_regardless_of_failure_reason() -> None:
    caption = stage_caption(
        "draft_ready",
        failed=True,
        gate_failed=True,
        failure_reason="Refusing to advance past the Groundedness Gate: 1 violation(s).",
    )

    assert caption == "Verifica non superata"


def test_a_non_gate_failure_caption_is_the_runs_own_failure_reason() -> None:
    caption = stage_caption(
        "draft_ready",
        failed=True,
        gate_failed=False,
        failure_reason="stage 'draft_ready' failed 5 consecutive times: simulated rate limit",
    )

    assert caption == "stage 'draft_ready' failed 5 consecutive times: simulated rate limit"


# --- violation_kind_label -----------------------------------------------------------


def test_every_known_violation_kind_has_a_distinct_italian_label() -> None:
    assert set(VIOLATION_KIND_LABELS) == {
        "empty_citation",
        "invented_fact",
        "contradicted_fact",
        "date_token_in_day_list",
    }
    assert len(set(VIOLATION_KIND_LABELS.values())) == len(VIOLATION_KIND_LABELS)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("empty_citation", "Citazione vuota"),
        ("invented_fact", "Fatto inventato"),
        ("contradicted_fact", "Fatto contraddetto"),
        ("date_token_in_day_list", "Data in un elenco di giorni"),
    ],
)
def test_a_known_kind_maps_to_its_italian_label(kind: str, expected: str) -> None:
    assert violation_kind_label(kind) == expected


def test_an_unknown_kind_falls_back_to_the_raw_token() -> None:
    assert violation_kind_label("some_future_kind") == "some_future_kind"


# --- resolve_cited_entries: parity ---------------------------------------------------


def test_cited_entry_field_labels_covers_every_field_of_the_five_dataclasses() -> None:
    all_fields: set[str] = set()
    for names in _ENTRY_FIELD_ORDER.values():
        all_fields.update(names)
    assert set(CITED_ENTRY_FIELD_LABELS) == all_fields


def test_entry_kind_headings_and_field_order_cover_the_same_five_kind_tags() -> None:
    """The five literal kind tags ``core/payload/freeze.py::_event_kind()``
    can produce."""
    expected = {"aspect", "station", "standing_retrograde", "ingress", "lunation"}
    assert set(_ENTRY_KIND_HEADINGS_IT) == expected
    assert set(_ENTRY_FIELD_ORDER) == expected


# --- resolve_cited_entries: I/O & Edge-Case Matrix rows -----------------------------


def test_resolve_cited_entries_returns_empty_list_for_no_citations() -> None:
    assert resolve_cited_entries((), {}, "Europe/Rome") == []


def test_resolve_cited_entries_skips_a_stale_unresolvable_id_without_crashing() -> None:
    assert resolve_cited_entries(("does-not-exist",), {}, "Europe/Rome") == []


def test_resolve_cited_entries_renders_an_aspect_card_with_italian_labels_and_a_local_time() -> (
    None
):
    aspect = TransitAspectEvent(
        transiting_body="saturn",
        natal_point="moon",
        aspect="trine",
        perfected_at=datetime(2026, 1, 5, 12, 30, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    frozen = _freeze(aspects=(aspect,))
    aspect_id = _find_id(frozen["sections"]["energia_generale"]["aspects"], kind="aspect")
    index = _index_entries(frozen)

    [card] = resolve_cited_entries((aspect_id,), index, "Europe/Rome")

    assert card["kind_label"] == "Aspetto"
    assert card["id"] == aspect_id
    fields = dict(card["fields"])
    assert fields["Corpo transitante"] == "Saturno"
    assert fields["Punto natale"] == "Luna"
    assert fields["Aspetto"] == "Trigono"
    assert fields["Perfezionato il"] == "05/01/2026 13:30"
    assert fields["Mai perfezionato"] == "No"
    assert fields["Uscita dall'orbita"] == "—"


def test_resolve_cited_entries_renders_an_ingress_card() -> None:
    ingress = Ingress(
        body="mars",
        house_departed=4,
        house_entered=5,
        crossed_at=datetime(2026, 1, 10, tzinfo=UTC),
    )
    frozen = _freeze(ingresses=(ingress,))
    ingress_id = _find_id(frozen["sections"]["energia_generale"]["ingresses"], kind="ingress")
    index = _index_entries(frozen)

    [card] = resolve_cited_entries((ingress_id,), index, "UTC")

    assert card["kind_label"] == "Ingresso"
    fields = dict(card["fields"])
    assert fields["Corpo"] == "Marte"
    assert fields["Casa di partenza"] == "4"
    assert fields["Casa di arrivo"] == "5"
    assert fields["Attraversamento il"] == "10/01/2026 00:00"


def test_resolve_cited_entries_renders_a_standing_retrograde_card() -> None:
    retrograde = StandingRetrograde(
        body="mercury",
        retrograde_start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        retrograde_end_utc=datetime(2026, 1, 31, tzinfo=UTC),
    )
    frozen = _freeze(standing_retrogrades=(retrograde,))
    retro_id = _find_id(
        frozen["sections"]["energia_generale"]["standing_retrogrades"],
        kind="standing_retrograde",
    )
    index = _index_entries(frozen)

    [card] = resolve_cited_entries((retro_id,), index, "UTC")

    assert card["kind_label"] == "Retrogradazione in corso"
    fields = dict(card["fields"])
    assert fields["Corpo"] == "Mercurio"
    assert fields["Inizio della retrogradazione"] == "01/01/2026 00:00"
    assert fields["Fine della retrogradazione"] == "31/01/2026 00:00"


def test_resolve_cited_entries_renders_a_lunation_card() -> None:
    lunation = Lunation(
        kind="full_moon",
        occurred_at=datetime(2026, 1, 12, 6, 0, tzinfo=UTC),
        longitude=Decimal("100.5"),
        natal_house=7,
    )
    frozen = _freeze(lunations=(lunation,))
    lunation_id = _find_id(frozen["sections"]["energia_generale"]["lunations"], kind="lunation")
    index = _index_entries(frozen)

    [card] = resolve_cited_entries((lunation_id,), index, "UTC")

    assert card["kind_label"] == "Lunazione"
    fields = dict(card["fields"])
    assert fields["Tipo di lunazione"] == "Luna Piena"
    assert fields["Data della lunazione"] == "12/01/2026 06:00"
    assert fields["Longitudine"] == "100.5°"
    assert fields["Casa natale"] == "7"


def test_resolve_cited_entries_renders_a_station_card() -> None:
    station = Station(
        body="venus",
        direction="direct",
        station_at=datetime(2026, 1, 8, tzinfo=UTC),
        longitude=Decimal("50.25"),
    )
    frozen = _freeze(stations=(station,))
    station_id = _find_id(frozen["sections"]["energia_generale"]["stations"], kind="station")
    index = _index_entries(frozen)

    [card] = resolve_cited_entries((station_id,), index, "UTC")

    assert card["kind_label"] == "Stazione"
    fields = dict(card["fields"])
    assert fields["Corpo"] == "Venere"
    assert fields["Direzione"] == "Diretto"
    assert fields["Stazione il"] == "08/01/2026 00:00"
    assert fields["Longitudine"] == "50.25°"


@pytest.mark.parametrize(
    ("natal_point", "expected_label"),
    [
        ("ascendant", "Ascendente"),
        ("midheaven", "Mediocielo"),
        ("true_node", "Nodo Nord"),
        ("south_node", "Nodo Sud"),
    ],
)
def test_resolve_cited_entries_translates_an_angle_or_node_natal_point(
    natal_point: str, expected_label: str
) -> None:
    """review-loop 2: an Aspect's ``natal_point`` can name one of the four
    angle/node targets ``core/transits/aspects.py::_natal_targets()`` admits
    alongside the ten planets -- never the raw English token in a rendered
    card."""
    aspect = TransitAspectEvent(
        transiting_body="jupiter",
        natal_point=natal_point,
        aspect="square",
        perfected_at=datetime(2026, 1, 5, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    frozen = _freeze(aspects=(aspect,))
    aspect_id = _find_id(frozen["sections"]["energia_generale"]["aspects"], kind="aspect")
    index = _index_entries(frozen)

    [card] = resolve_cited_entries((aspect_id,), index, "UTC")

    assert dict(card["fields"])["Punto natale"] == expected_label


def test_resolve_cited_entries_degrades_gracefully_for_an_unrecognized_kind() -> None:
    """Mirrors ``violation_kind_label``'s own defensive fallback: a future
    sixth transit-event kind degrades to a readable-if-English heading and
    an empty field list instead of raising."""
    index = {"weird-id": {"id": "weird-id", "kind": "some_future_kind", "value": 42}}

    [card] = resolve_cited_entries(("weird-id",), index, "UTC")

    assert card["kind_label"] == "some_future_kind"
    assert card["fields"] == []
