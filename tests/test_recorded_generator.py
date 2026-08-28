"""``RecordedResponseGenerator`` -- Story 4.9's own I/O & Edge-Case Matrix
rows. Mirrors ``tests/test_gemini_generator.py``'s structure (payload
fixtures shaped like ``core/payload/freeze.py::freeze_payload()``'s return),
but there is no client to fake: this adapter never calls a network, a model
or the filesystem.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any

from core.types.generation import GeneratedDraft
from core.types.memory import ReportTheme
from shell.adapters.local.generator import RecordedResponseGenerator
from shell.ports.generator import StyleGuideVersion

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
