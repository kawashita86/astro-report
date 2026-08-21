"""``GeminiGenerator`` -- the ``_GeminiClient`` is an injected fake throughout,
so these tests exercise prompt-building, parsing and both validation steps
without a real network call. Row-for-row coverage of the story's I/O &
Edge-Case Matrix.
"""

from __future__ import annotations

import json
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from typing import Any

import pytest

from core.ephemeris.identity import verify_ephemeris_identity
from core.errors import GenerationError
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.generation import GeneratedDraft
from core.types.memory import ReportTheme, ThemeAspect
from core.types.payload import Payload, SectionPayload
from core.types.transits import StandingRetrograde, TransitAspectEvent
from shell.adapters.gemini.generator import _MODEL, _RESPONSE_SCHEMA, GeminiGenerator
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

_KNOWN_ID = "aspect-known-1"
_ANOTHER_KNOWN_ID = "aspect-known-2"

_STYLE_GUIDE = StyleGuideVersion(version=3, content="Scrivi con calore, mai in modo fatalista.")

_EMPTY_THEME = ReportTheme(dominant_aspects=(), lunations=(), standing_retrogrades=())


def _payload_with_ids(*entry_ids: str) -> dict[str, Any]:
    """A minimal ``payload`` dict shaped like ``core/payload/freeze.py::freeze_payload()``'s
    return: entry ids nested under both a Section (``sections``) and a
    day-list (``day_lists``), matching where citation validation must look."""
    ids = list(entry_ids)
    first = ids[0] if ids else None
    rest = ids[1:]
    return {
        "sections": {
            "energia_generale": {
                "profile": None,
                "aspects": [{"id": first, "kind": "aspect"}] if first else [],
                "stations": [],
                "standing_retrogrades": [],
                "ingresses": [],
                "lunations": [],
            },
        },
        "day_lists": {
            "giorni_favorevoli": [{"id": entry_id, "kind": "aspect"} for entry_id in rest],
            "giorni_di_attenzione": [],
        },
    }


def _draft_response(**overrides: list[dict[str, Any]]) -> str:
    data: dict[str, list[dict[str, Any]]] = {name: [] for name in _SECTION_NAMES}
    data.update(overrides)
    return json.dumps(data)


class _FakeGeminiClient:
    """Records every call so a "prompt omits prior-month material" claim is
    provable rather than assumed -- mirrors ``_FakeGeolocator``
    (``tests/test_geocoder_nominatim.py``)."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def generate_content(
        self, *, system_instruction: str, prompt: str, response_schema: dict[str, Any]
    ) -> str | None:
        self.calls.append(
            {
                "system_instruction": system_instruction,
                "prompt": prompt,
                "response_schema": response_schema,
            }
        )
        if self._error is not None:
            raise self._error
        return self._response


# --- Matrix row: happy path, returning Client --------------------------------


def test_happy_path_returns_a_populated_draft_with_all_eight_fields() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    response = _draft_response(
        energia_generale=[
            {"text": "Il mese si apre con energia stabile.", "entry_ids": [_KNOWN_ID]}
        ],
        giorni_favorevoli=[{"text": "Una buona giornata per iniziare progetti.", "entry_ids": []}],
    )
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = generator.generate(payload, _STYLE_GUIDE, _EMPTY_THEME, _EMPTY_THEME)

    assert isinstance(draft, GeneratedDraft)
    assert tuple(field.name for field in dataclass_fields(draft)) == _SECTION_NAMES
    assert draft.energia_generale[0].text == "Il mese si apre con energia stabile."
    assert draft.energia_generale[0].entry_ids == (_KNOWN_ID,)
    assert draft.amore == ()
    assert len(client.calls) == 1


def test_a_populated_theme_with_real_dataclass_and_datetime_fields_serializes() -> None:
    """Every other test in this file uses ``_EMPTY_THEME`` (all-empty
    tuples), which never exercises the adapter's own ``_json_safe``
    dataclass/datetime conversion branches -- needed for a real
    ``ThemeAspect``/``StandingRetrograde``'s ``perfected_at``/``orb_entry_at``/
    ``orb_exit_at``/``retrograde_start_utc``/``retrograde_end_utc`` fields.
    A populated theme as both ``theme_previous`` and ``theme_current`` must
    still serialize into the prompt without raising."""
    payload = _payload_with_ids(_KNOWN_ID)
    theme = ReportTheme(
        dominant_aspects=(
            ThemeAspect(
                transiting_body="saturn",
                natal_point="sun",
                aspect="square",
                perfected_at=datetime(2026, 1, 10, 12, 0, tzinfo=UTC),
                never_perfected=False,
                orb_entry_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                orb_exit_at=datetime(2026, 1, 20, 0, 0, tzinfo=UTC),
            ),
        ),
        lunations=(),
        standing_retrogrades=(
            StandingRetrograde(
                body="mercury",
                retrograde_start_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                retrograde_end_utc=datetime(2026, 1, 31, 23, 59, tzinfo=UTC),
            ),
        ),
    )
    client = _FakeGeminiClient(response=_draft_response())
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = generator.generate(payload, _STYLE_GUIDE, theme, theme)

    assert isinstance(draft, GeneratedDraft)
    prompt = client.calls[0]["prompt"]
    assert "2026-01-10T12:00:00+00:00" in prompt  # ThemeAspect.perfected_at
    assert "2026-01-31T23:59:00+00:00" in prompt  # StandingRetrograde.retrograde_end_utc
    assert "saturn" in prompt
    assert "mercury" in prompt


def test_system_instruction_carries_the_style_guide_and_response_schema_matches() -> None:
    """AC: the Style Guide version in force must be supplied with every
    request, and the model must be asked for exactly the module's own
    ``_RESPONSE_SCHEMA`` -- not some ad-hoc shape built inline."""
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_draft_response())
    generator = GeminiGenerator(api_key="unused", client=client)

    generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    call = client.calls[0]
    assert _STYLE_GUIDE.content in call["system_instruction"]
    assert str(_STYLE_GUIDE.version) in call["system_instruction"]
    assert call["response_schema"] == _RESPONSE_SCHEMA


def test_generated_draft_is_never_a_string_keyed_dict() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_draft_response())
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert not isinstance(draft, dict)
    assert isinstance(draft, GeneratedDraft)


# --- Matrix row: first Report for a Client (theme_previous=None) ------------


def test_first_report_omits_prior_month_material_and_still_returns_a_draft() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_draft_response())
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert isinstance(draft, GeneratedDraft)
    prompt = client.calls[0]["prompt"]
    assert "THEME_PREVIOUS (JSON, null se primo Report) ---\nnull" in prompt


# --- Matrix row: model cites an unknown entry id -----------------------------


def test_an_unknown_cited_entry_id_raises_at_the_citation_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    response = _draft_response(
        amore=[{"text": "Una frase mal fondata.", "entry_ids": ["does-not-exist"]}]
    )
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "citation_validation"
    assert "does-not-exist" in str(caught.value)


def test_citation_validation_finds_ids_in_a_real_freeze_payload_shaped_payload() -> None:
    """Every other citation test in this file uses ``_payload_with_ids()``'s
    hand-rolled, simplified shape. This one runs a real ``Payload``/``DayLists``
    through the actual ``freeze_payload()`` (mirrors
    ``tests/test_payload_freeze.py``'s own fixtures) so citation validation
    is proven against the true nested structure, not a stand-in for it."""
    config = load_computation_config()
    sections_config = load_sections_config()
    ephemeris_identity = verify_ephemeris_identity()

    aspect = TransitAspectEvent(
        transiting_body="mars",
        natal_point="venus",
        aspect="trine",
        perfected_at=datetime(2026, 1, 5, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    populated_section = SectionPayload(
        profile=None,
        aspects=(aspect,),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    empty_section = SectionPayload(
        profile=None, aspects=(), stations=(), standing_retrogrades=(), ingresses=(), lunations=()
    )
    payload = Payload(
        energia_generale=populated_section,
        amore=empty_section,
        lavoro=empty_section,
        denaro=empty_section,
        benessere=empty_section,
        consiglio_finale=empty_section,
    )
    frozen = freeze_payload(
        payload,
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
        config=config,
        sections_config=sections_config,
        ephemeris_identity=ephemeris_identity,
    )
    real_id = frozen["sections"]["energia_generale"]["aspects"][0]["id"]

    response = _draft_response(
        energia_generale=[{"text": "Marte in trigono a Venere.", "entry_ids": [real_id]}]
    )
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = generator.generate(frozen, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert draft.energia_generale[0].entry_ids == (real_id,)


# --- Matrix row: model writes a date in Section 6 or 7 -----------------------


@pytest.mark.parametrize(
    "sentence_text",
    [
        "Il 15 gennaio è una buona giornata per agire.",
        "Il 3 marzo porta chiarezza.",
        "La data 2026-01-15 è favorevole.",
    ],
)
def test_a_date_token_in_giorni_favorevoli_raises_at_the_date_token_step(
    sentence_text: str,
) -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    response = _draft_response(
        giorni_favorevoli=[{"text": sentence_text, "entry_ids": []}]
    )
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "date_token_validation"
    assert sentence_text in str(caught.value)


def test_a_date_token_in_giorni_di_attenzione_raises_at_the_date_token_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    response = _draft_response(
        giorni_di_attenzione=[{"text": "Attenzione il 22 ottobre.", "entry_ids": []}]
    )
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "date_token_validation"


def test_a_date_shaped_word_elsewhere_is_not_flagged_as_a_date_token() -> None:
    """The heuristic is about giorni_favorevoli/giorni_di_attenzione only --
    a month name appearing in prose elsewhere (e.g. describing a transit in
    energia_generale) is not itself a violation of this story's rule."""
    payload = _payload_with_ids(_KNOWN_ID)
    response = _draft_response(
        energia_generale=[
            {"text": "Un transito di gennaio continua a farsi sentire.", "entry_ids": [_KNOWN_ID]}
        ],
    )
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert draft.energia_generale[0].text == "Un transito di gennaio continua a farsi sentire."


# --- Matrix row: Gemini call raises or times out -----------------------------


def test_a_raising_client_wraps_the_original_error_at_the_request_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(error=TimeoutError("the provider timed out"))
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "request"
    assert isinstance(caught.value.__cause__, TimeoutError)


# --- Matrix row: malformed / non-JSON model response -------------------------


def test_a_non_json_response_raises_at_the_parsing_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response="this is not json at all")
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "parsing"


def test_a_none_response_raises_at_the_parsing_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=None)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "parsing"


def test_a_json_array_instead_of_object_raises_at_the_parsing_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response="[1, 2, 3]")
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "parsing"


def test_a_response_missing_a_required_section_raises_at_the_parsing_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    incomplete = {name: [] for name in _SECTION_NAMES if name != "consiglio_finale"}
    client = _FakeGeminiClient(response=json.dumps(incomplete))
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "parsing"
    assert "consiglio_finale" in str(caught.value)


def test_a_sentence_missing_text_raises_at_the_parsing_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    response = _draft_response(amore=[{"entry_ids": [_KNOWN_ID]}])
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "parsing"


def test_a_sentence_with_non_list_entry_ids_raises_at_the_parsing_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    response = _draft_response(amore=[{"text": "Una frase.", "entry_ids": "not-a-list"}])
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "parsing"


def test_a_section_that_is_not_a_list_raises_at_the_parsing_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    data = {name: [] for name in _SECTION_NAMES}
    data["amore"] = "not-a-list"
    client = _FakeGeminiClient(response=json.dumps(data))
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        generator.generate(payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert caught.value.step == "parsing"


# --- The Style Guide is a required argument, never optional ------------------


def test_style_guide_has_no_default_and_cannot_be_omitted() -> None:
    import inspect

    signature = inspect.signature(GeminiGenerator.generate)
    assert signature.parameters["style_guide"].default is inspect.Parameter.empty


def test_calling_generate_without_a_style_guide_raises_type_error() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_draft_response())
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(TypeError):
        generator.generate(payload, theme_previous=None, theme_current=_EMPTY_THEME)  # type: ignore[call-arg]


# --- _GoogleGenAIClient: the wrapper around the real google-genai SDK -------


def test_google_genai_client_wrapper_calls_the_real_sdk_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every other test in this file injects the fake ``_GeminiClient``,
    bypassing ``_GoogleGenAIClient`` entirely. This pins its translation onto
    the real SDK's shape (``client.models.generate_content(model=...,
    contents=..., config=types.GenerateContentConfig(...))``) so a future
    ``google-genai`` upgrade that changes field names fails loudly here
    rather than silently at the first real call."""
    from google.genai import types as genai_types

    from shell.adapters.gemini.generator import _GoogleGenAIClient

    captured: dict[str, Any] = {}

    class _FakeResponse:
        text = '{"ok": true}'

    class _FakeModels:
        def generate_content(
            self, *, model: str, contents: str, config: Any
        ) -> _FakeResponse:
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return _FakeResponse()

    class _FakeSDKClient:
        def __init__(self, api_key: str) -> None:
            captured["api_key"] = api_key
            self.models = _FakeModels()

    monkeypatch.setattr("shell.adapters.gemini.generator.genai.Client", _FakeSDKClient)

    wrapper = _GoogleGenAIClient(api_key="secret-key")
    result = wrapper.generate_content(
        system_instruction="be nice", prompt="hello", response_schema={"type": "object"}
    )

    assert result == '{"ok": true}'
    assert captured["api_key"] == "secret-key"
    assert captured["model"] == _MODEL
    assert captured["contents"] == "hello"
    config = captured["config"]
    assert isinstance(config, genai_types.GenerateContentConfig)
    assert config.system_instruction == "be nice"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == {"type": "object"}


# --- The adapter holds no DB handle, filesystem access or tool definitions ---


def test_the_adapter_module_imports_nothing_from_postgres_or_sqlalchemy() -> None:
    import ast
    from pathlib import Path

    module_path = Path(__file__).resolve().parent.parent / "shell/adapters/gemini/generator.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_roots = {"sqlmodel", "sqlalchemy"}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in forbidden_roots or "postgres" in alias.name:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in forbidden_roots or "postgres" in node.module:
                offenders.append(node.module)

    assert not offenders, f"shell/adapters/gemini/generator.py imports: {offenders}"
