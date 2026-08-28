"""``RecordedResponseGenerator`` -- Story 4.9's own I/O & Edge-Case Matrix
rows. Mirrors ``tests/test_gemini_generator.py``'s structure (payload
fixtures shaped like ``core/payload/freeze.py::freeze_payload()``'s return),
but there is no client to fake: this adapter never calls a network, a model
or the filesystem.
"""

from __future__ import annotations

import socket
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from core.ephemeris.identity import verify_ephemeris_identity
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.generation import GeneratedDraft
from core.types.memory import ReportTheme
from core.types.payload import Payload, SectionPayload
from core.types.transits import Lunation, TransitAspectEvent
from shell.adapters.local.generator import RecordedResponseGenerator
from shell.computation import load_computation_config
from shell.ports.generator import StyleGuideVersion
from shell.sections import load_sections_config

_SECTION_NAMES: tuple[str, ...] = (
    "energia_generale",
    "amore",
    "lavoro",
    "denaro",
    "benessere",
    "giorni_favorevoli",
    "giorni_di_attenzione",
    "consiglio_finale",
)

_STYLE_GUIDE = StyleGuideVersion(version=1, content="Scrivi con calore, mai in modo fatalista.")
_EMPTY_THEME = ReportTheme(dominant_aspects=(), lunations=(), standing_retrogrades=())


def _empty_payload() -> dict[str, Any]:
    """No entries anywhere -- every Section and both day-lists are empty."""
    empty_section = {
        "profile": None,
        "aspects": [],
        "stations": [],
        "standing_retrogrades": [],
        "ingresses": [],
        "lunations": [],
    }
    return {
        "sections": {name: dict(empty_section) for name in _payload_section_names()},
        "day_lists": {"giorni_favorevoli": [], "giorni_di_attenzione": []},
    }


def _payload_section_names() -> tuple[str, ...]:
    """The six ``core.types.payload.Payload`` field names -- kept local to
    this test module rather than imported, mirroring ``_payload_with_ids``'s
    own hand-built shape in ``tests/test_gemini_generator.py``."""
    return (
        "energia_generale",
        "amore",
        "lavoro",
        "denaro",
        "benessere",
        "consiglio_finale",
    )


def _multi_section_payload() -> dict[str, Any]:
    """A realistic multi-Section, multi-day-list payload: entries under
    several Sections and both day-lists, each carrying its own distinct id
    (Matrix row: "A realistic multi-Section, multi-day-list payload")."""
    return {
        "sections": {
            "energia_generale": {
                "profile": None,
                "aspects": [{"id": "aspect-energia-1", "kind": "aspect"}],
                "stations": [],
                "standing_retrogrades": [],
                "ingresses": [],
                "lunations": [{"id": "lunation-energia-1", "kind": "lunation"}],
            },
            "amore": {
                "profile": {"id": "profile-amore-1"},
                "aspects": [{"id": "aspect-amore-1", "kind": "aspect"}],
                "stations": [],
                "standing_retrogrades": [],
                "ingresses": [],
                "lunations": [],
            },
            "lavoro": {
                "profile": None,
                "aspects": [],
                "stations": [{"id": "station-lavoro-1", "kind": "station"}],
                "standing_retrogrades": [],
                "ingresses": [],
                "lunations": [],
            },
            "denaro": {
                "profile": None,
                "aspects": [],
                "stations": [],
                "standing_retrogrades": [],
                "ingresses": [],
                "lunations": [],
            },
            "benessere": {
                "profile": None,
                "aspects": [],
                "stations": [],
                "standing_retrogrades": [
                    {"id": "retrograde-benessere-1", "kind": "standing_retrograde"}
                ],
                "ingresses": [],
                "lunations": [],
            },
            "consiglio_finale": {
                "profile": None,
                "aspects": [],
                "stations": [],
                "standing_retrogrades": [],
                "ingresses": [],
                "lunations": [],
            },
        },
        "day_lists": {
            "giorni_favorevoli": [{"id": "aspect-favorevole-1", "kind": "aspect"}],
            "giorni_di_attenzione": [{"id": "aspect-attenzione-1", "kind": "aspect"}],
        },
    }


# --- Matrix row: a realistic multi-Section, multi-day-list payload ----------


def test_every_sentence_entry_id_is_present_in_the_payload() -> None:
    payload = _multi_section_payload()
    generator = RecordedResponseGenerator()

    draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    assert isinstance(draft, GeneratedDraft)
    assert tuple(field.name for field in dataclass_fields(draft)) == _SECTION_NAMES

    known_ids = {
        "aspect-energia-1",
        "lunation-energia-1",
        "profile-amore-1",
        "aspect-amore-1",
        "station-lavoro-1",
        "retrograde-benessere-1",
        "aspect-favorevole-1",
        "aspect-attenzione-1",
    }
    for field in dataclass_fields(draft):
        for sentence in getattr(draft, field.name):
            for entry_id in sentence.entry_ids:
                assert entry_id in known_ids


def test_each_section_cites_exactly_the_ids_present_in_its_own_subtree() -> None:
    payload = _multi_section_payload()
    generator = RecordedResponseGenerator()

    draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    assert set(draft.energia_generale[0].entry_ids) == {"aspect-energia-1", "lunation-energia-1"}
    assert set(draft.amore[0].entry_ids) == {"profile-amore-1", "aspect-amore-1"}
    assert set(draft.lavoro[0].entry_ids) == {"station-lavoro-1"}
    assert set(draft.denaro[0].entry_ids) == set()
    assert set(draft.benessere[0].entry_ids) == {"retrograde-benessere-1"}
    assert set(draft.giorni_favorevoli[0].entry_ids) == {"aspect-favorevole-1"}
    assert set(draft.giorni_di_attenzione[0].entry_ids) == {"aspect-attenzione-1"}
    assert set(draft.consiglio_finale[0].entry_ids) == set()


def test_giorni_sections_contain_no_date_shaped_token() -> None:
    payload = _multi_section_payload()
    generator = RecordedResponseGenerator()

    draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    for sentence in draft.giorni_favorevoli:
        assert "2026" not in sentence.text
    for sentence in draft.giorni_di_attenzione:
        assert "2026" not in sentence.text


# --- Matrix row: a Section/day-list with zero entries -----------------------


def test_a_section_with_zero_entries_still_returns_a_sentence_with_no_citations() -> None:
    payload = _empty_payload()
    generator = RecordedResponseGenerator()

    draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    for field in dataclass_fields(draft):
        sentences = getattr(draft, field.name)
        assert len(sentences) == 1
        assert sentences[0].entry_ids == ()


def test_an_absent_day_list_key_is_treated_like_an_empty_one() -> None:
    """The Matrix's own "``[]``/absent" phrasing -- a payload missing the
    ``day_lists`` sub-tree entirely must not raise, and reads as zero ids."""
    payload = {
        "sections": {name: {} for name in _payload_section_names()},
        "day_lists": {},
    }
    generator = RecordedResponseGenerator()

    draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    assert draft.giorni_favorevoli[0].entry_ids == ()
    assert draft.giorni_di_attenzione[0].entry_ids == ()


# --- Never a network, model, or filesystem call ------------------------------


def _all_ids(payload: dict[str, Any]) -> set[str]:
    """Every string ``"id"`` anywhere in ``payload`` -- a generic recursive
    walk, mirroring the adapter's own ``_collect_known_entry_ids``."""
    found: set[str] = set()

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("id"), str):
                found.add(value["id"])
            for item in value.values():
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(payload)
    return found


def _real_frozen_payload() -> dict[str, Any]:
    """A payload produced by the real ``core/payload/freeze.py::freeze_payload()``
    -- entries under a Section and under both day-lists, each carrying its
    own content-hashed ``"id"`` (epic-4-retro-item-29). Copies the
    ``Payload``/``SectionPayload``/``DayLists`` +
    ``load_computation_config``/``load_sections_config``/``verify_ephemeris_identity``
    setup from
    ``tests/test_gemini_generator.py::test_citation_validation_finds_ids_in_a_real_freeze_payload_shaped_payload``,
    which had no counterpart for this adapter until now."""
    config = load_computation_config()
    sections_config = load_sections_config()
    ephemeris_identity = verify_ephemeris_identity()

    section_aspect = TransitAspectEvent(
        transiting_body="mars",
        natal_point="venus",
        aspect="trine",
        perfected_at=datetime(2026, 1, 5, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    favorable_aspect = TransitAspectEvent(
        transiting_body="venus",
        natal_point="moon",
        aspect="sextile",
        perfected_at=datetime(2026, 1, 12, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 9, tzinfo=UTC),
        orb_exit_at=None,
    )
    favorable_lunation = Lunation(
        kind="new_moon",
        occurred_at=datetime(2026, 1, 18, tzinfo=UTC),
        longitude=Decimal("15.0"),
        natal_house=3,
    )
    attention_aspect = TransitAspectEvent(
        transiting_body="saturn",
        natal_point="sun",
        aspect="square",
        perfected_at=datetime(2026, 1, 22, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 19, tzinfo=UTC),
        orb_exit_at=None,
    )
    populated = SectionPayload(
        profile=None,
        aspects=(section_aspect,),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    empty = SectionPayload(
        profile=None,
        aspects=(),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    payload = Payload(
        energia_generale=populated,
        amore=empty,
        lavoro=empty,
        denaro=empty,
        benessere=empty,
        consiglio_finale=empty,
    )
    return freeze_payload(
        payload,
        DayLists(
            giorni_favorevoli=(favorable_aspect, favorable_lunation),
            giorni_di_attenzione=(attention_aspect,),
        ),
        config=config,
        sections_config=sections_config,
        ephemeris_identity=ephemeris_identity,
    )


# --- epic-4-retro-item-29: exercised against a real freeze_payload() output ---


def test_generate_against_a_real_frozen_payload_returns_a_valid_cited_draft() -> None:
    payload = _real_frozen_payload()
    generator = RecordedResponseGenerator()

    draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    assert isinstance(draft, GeneratedDraft)
    assert tuple(field.name for field in dataclass_fields(draft)) == _SECTION_NAMES

    known_ids = _all_ids(payload)
    assert len(known_ids) == 4  # one section aspect + two favorevoli + one attenzione
    for field in dataclass_fields(draft):
        for sentence in getattr(draft, field.name):
            for entry_id in sentence.entry_ids:
                assert entry_id in known_ids


def test_each_section_cites_exactly_the_ids_in_its_own_real_subtree() -> None:
    payload = _real_frozen_payload()
    generator = RecordedResponseGenerator()

    draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    energia_ids = {entry["id"] for entry in payload["sections"]["energia_generale"]["aspects"]}
    favorevoli_ids = {entry["id"] for entry in payload["day_lists"]["giorni_favorevoli"]}
    attenzione_ids = {entry["id"] for entry in payload["day_lists"]["giorni_di_attenzione"]}

    assert set(draft.energia_generale[0].entry_ids) == energia_ids
    assert set(draft.giorni_favorevoli[0].entry_ids) == favorevoli_ids
    assert set(draft.giorni_di_attenzione[0].entry_ids) == attenzione_ids
    for empty_section in ("amore", "lavoro", "denaro", "benessere", "consiglio_finale"):
        assert getattr(draft, empty_section)[0].entry_ids == ()


def test_real_freeze_payload_never_puts_none_at_sections_or_day_lists() -> None:
    """edge-case-hunter #4: ``_section_subtree`` reads
    ``payload.get("sections", {})`` / ``payload.get("day_lists", {})``, which
    would raise ``AttributeError`` if the key were present but ``None``. Real
    ``freeze_payload()`` output always writes a dict at both (and at every
    Section within ``sections``), so that branch is unreachable in practice
    (epic-4-retro-item-29 settles this)."""
    payload = _real_frozen_payload()

    assert isinstance(payload["sections"], dict)
    assert isinstance(payload["day_lists"], dict)
    assert all(value is not None for value in payload["sections"].values())
    assert all(value is not None for value in payload["day_lists"].values())


# --- epic-4-retro-item-30: a runtime no-I/O proof, not just import-time -------


def test_generate_opens_no_socket_and_no_file_against_a_real_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """epic-4-retro-item-30: ``test_never_imports_google_genai`` only
    inspects the module namespace. This proves it at runtime -- ``socket.socket``
    and ``builtins.open`` are made to raise for the duration of the
    ``generate()`` call (against a real frozen payload) and it still
    succeeds, so the "never a network call, a model call or a filesystem
    read" guarantee is checked for the code path that actually runs under
    ``compose.yaml``."""
    payload = _real_frozen_payload()
    generator = RecordedResponseGenerator()

    def _no_network(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("RecordedResponseGenerator.generate attempted network I/O")

    def _no_open(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("RecordedResponseGenerator.generate opened a file")

    with monkeypatch.context() as patched:
        patched.setattr(socket, "socket", _no_network)
        patched.setattr(socket, "create_connection", _no_network)
        patched.setattr(socket, "getaddrinfo", _no_network)
        patched.setattr("builtins.open", _no_open)
        draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    assert isinstance(draft, GeneratedDraft)


def test_never_imports_google_genai() -> None:
    """Boundaries & Constraints: never imports ``google.genai`` (epic-4-retro-item-24).

    Asserts the *direct* import lines of the two files that matter:
    ``shell/adapters/local/generator.py`` names nothing under
    ``shell.adapters.gemini`` (whose import executes ``from google import
    genai``), and ``shell/adapters/generation/validation.py`` -- the
    provider-neutral module ``local.generator`` now depends on -- names no
    ``google`` root. Deeper transitive purity of ``core.*`` is enforced
    separately by ``tests/test_import_boundary.py``."""
    import ast
    from pathlib import Path

    import shell.adapters.local.generator as module

    assert "genai" not in vars(module)
    assert not hasattr(module, "genai")

    repo_root = Path(__file__).resolve().parent.parent

    def _imported_module_names(relative_path: str) -> list[str]:
        tree = ast.parse((repo_root / relative_path).read_text(encoding="utf-8"))
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.append(node.module)
        return names

    local_imports = _imported_module_names("shell/adapters/local/generator.py")
    assert not any(
        name == "shell.adapters.gemini" or name.startswith("shell.adapters.gemini.")
        for name in local_imports
    ), f"local.generator still reaches into the Gemini adapter: {local_imports}"

    validation_imports = _imported_module_names("shell/adapters/generation/validation.py")
    assert not any(
        name == "google" or name.startswith("google.") for name in validation_imports
    ), f"generation/validation.py imports a google root: {validation_imports}"
