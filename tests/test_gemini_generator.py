"""``GeminiGenerator`` -- the ``_GeminiClient`` is an injected fake throughout,
so these tests exercise prompt-building, parsing and both validation steps
without a real network call. Row-for-row coverage of the story's I/O &
Edge-Case Matrix.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from core.ephemeris.identity import verify_ephemeris_identity
from core.errors import GenerationError
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.generation import Sentence
from core.types.memory import ReportTheme, ThemeAspect
from core.types.payload import Payload, SectionPayload
from core.types.transits import StandingRetrograde, TransitAspectEvent
from shell.adapters.gemini.generator import (
    _CONTINUITY_HEADER,
    _FIRST_REPORT_STATEMENT,
    _NOTHING_SIGNIFICANT_CHANGED_STATEMENT,
    GeminiGenerator,
    _build_id_aliases,
    _build_section_response_schema,
)
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

_T0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 1, 10, 6, 0, 0, tzinfo=UTC)
_T2 = datetime(2026, 1, 15, 18, 0, 0, tzinfo=UTC)


def _theme_aspect(
    *,
    transiting_body: str = "saturn",
    natal_point: str = "sun",
    aspect: str = "square",
    perfected_at: datetime | None = _T1,
    never_perfected: bool = False,
    orb_entry_at: datetime = _T0,
    orb_exit_at: datetime | None = None,
) -> ThemeAspect:
    """Mirrors ``tests/test_diff_themes.py``'s own ``_theme_aspect()``
    builder -- same fixture conventions (Story 4.7 Code Map)."""
    return ThemeAspect(
        transiting_body=transiting_body,
        natal_point=natal_point,
        aspect=aspect,
        perfected_at=perfected_at,
        never_perfected=never_perfected,
        orb_entry_at=orb_entry_at,
        orb_exit_at=orb_exit_at,
    )


def _retrograde(
    *, body: str = "saturn", start: datetime = _T0, end: datetime = _T2
) -> StandingRetrograde:
    return StandingRetrograde(body=body, retrograde_start_utc=start, retrograde_end_utc=end)


def _theme(
    *,
    aspects: tuple[ThemeAspect, ...] = (),
    retrogrades: tuple[StandingRetrograde, ...] = (),
) -> ReportTheme:
    return ReportTheme(dominant_aspects=aspects, lunations=(), standing_retrogrades=retrogrades)


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


#: What the model returns for a Section that has nothing to say.
_EMPTY_SECTION_RESPONSE = json.dumps({"sentences": []})


def _one(
    generator: GeminiGenerator,
    payload: dict[str, Any],
    theme_previous: ReportTheme | None,
    theme_current: ReportTheme,
    section: str = "energia_generale",
) -> tuple[Sentence, ...]:
    """One Section through ``generate_section`` with the shared Style Guide."""
    return generator.generate_section(section, payload, _STYLE_GUIDE, theme_previous, theme_current)


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


def test_a_populated_theme_with_real_dataclass_and_datetime_fields_renders_without_raising() -> (
    None
):
    """Every other continuity test in this file uses ``_theme_aspect()``'s
    thin builder. This one exercises the same code path
    (``diff_themes()`` then ``_render_continuity()``) against real
    ``ThemeAspect``/``StandingRetrograde`` instances with every field
    populated -- proving raw datetime fields never need to leak into the
    prompt at all (Story 4.7: the raw JSON dump is removed, not merely
    reformatted)."""
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
                orb_exit_at=None,
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
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = _one(generator, payload, theme, theme)

    assert draft == ()
    prompt = client.calls[0]["prompt"]
    assert "saturn" in prompt
    assert "mercury" in prompt
    assert "2026-01-10T12:00:00+00:00" not in prompt  # ThemeAspect.perfected_at
    assert "2026-01-31T23:59:00+00:00" not in prompt  # StandingRetrograde.retrograde_end_utc


def test_system_instruction_carries_the_style_guide_and_response_schema_matches() -> None:
    """AC: the Style Guide version in force must be supplied with every
    request, and the model must be asked for exactly the module's own
    ``_build_section_response_schema()`` output for this Payload -- not some
    ad-hoc shape built inline."""
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, None, _EMPTY_THEME)

    call = client.calls[0]
    assert _STYLE_GUIDE.content in call["system_instruction"]
    assert str(_STYLE_GUIDE.version) in call["system_instruction"]
    aliases = _build_id_aliases(frozenset({_KNOWN_ID}))
    assert call["response_schema"] == _build_section_response_schema(
        "energia_generale", frozenset(aliases.values()), day_list_count=0
    )


#: A response that satisfies ``_validate_day_list_coverage`` for
#: ``_payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID, "aspect-known-3")``'s two
#: ``giorni_favorevoli`` entries -- one voce per id, matching the new
#: one-id-per-voce contract -- so tests below that only care about what was
#: *sent* to the client (``client.calls[0]``) don't also have to fight the
#: day-list coverage check to get a non-raising call.
_TWO_FAVOREVOLI_RESPONSE = json.dumps(
    {
        "sentences": [
            {"text": "Prima voce.", "entry_ids": [_ANOTHER_KNOWN_ID]},
            {"text": "Seconda voce.", "entry_ids": ["aspect-known-3"]},
        ]
    }
)


def test_response_schema_constrains_entry_ids_to_an_enum_of_short_aliases() -> None:
    """sprint-change-proposal-2026-09-18: ``entry_ids`` is constrained to an
    ``enum`` of short aliases (``"e1"``, ``"e2"``, ...), never the raw
    64-char Payload ids directly -- Gemini's structured-output compiler
    rejects a schema whose enum is built from enough long ids (a real 400
    INVALID_ARGUMENT: "too many states for serving"), and an unknown/mistyped
    id is now impossible to request either way, never just caught after the
    fact by ``_validate_citations``."""
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, None, _EMPTY_THEME)

    schema = client.calls[0]["response_schema"]
    entry_ids_schema = schema["properties"]["sentences"]["items"]["properties"]["entry_ids"]
    expected_aliases = sorted(_build_id_aliases(frozenset({_KNOWN_ID, _ANOTHER_KNOWN_ID})).values())
    assert entry_ids_schema["items"]["enum"] == expected_aliases
    assert _KNOWN_ID not in entry_ids_schema["items"]["enum"]


def test_prompt_embeds_short_aliases_never_the_raw_long_payload_ids() -> None:
    """The Payload block the model actually reads must be self-consistent
    with the schema's alias enum -- the raw 64-char id must never appear in
    the prompt text at all, only its short alias."""
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, None, _EMPTY_THEME)

    prompt = client.calls[0]["prompt"]
    assert _KNOWN_ID not in prompt
    assert _ANOTHER_KNOWN_ID not in prompt
    aliases = _build_id_aliases(frozenset({_KNOWN_ID, _ANOTHER_KNOWN_ID}))
    assert f'"{aliases[_KNOWN_ID]}"' in prompt


def test_prompt_states_the_exact_day_list_counts_and_forbids_bundling() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID, "aspect-known-3")
    client = _FakeGeminiClient(response=_TWO_FAVOREVOLI_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, None, _EMPTY_THEME, section="giorni_favorevoli")

    prompt = client.calls[0]["prompt"]
    assert "esattamente 2 eventi in payload['day_lists']['giorni_favorevoli']" in prompt
    assert "scrivi esattamente 2 frasi" in prompt
    assert "Non accorpare più eventi sotto la stessa frase" in prompt


# --- Matrix row: first Report for a Client (theme_previous=None) ------------


def test_first_report_omits_prior_month_material_and_still_returns_a_draft() -> None:
    """Story 4.7: ``theme_previous=None`` renders the explicit first-Report
    statement, never the raw JSON dump this story removes, and never the
    continuity header (there is nothing prior to be continuous with)."""
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = _one(generator, payload, None, _EMPTY_THEME)

    assert draft == ()
    prompt = client.calls[0]["prompt"]
    assert _FIRST_REPORT_STATEMENT in prompt
    assert _CONTINUITY_HEADER not in prompt
    assert "THEME_PREVIOUS" not in prompt
    assert "THEME_CURRENT" not in prompt


# --- Story 4.7: continuity rendering from diff_themes() ----------------------


def test_still_active_aspect_is_rendered_as_a_continuation_never_a_novelty() -> None:
    aspect = _theme_aspect(orb_exit_at=None)
    theme_previous = _theme(aspects=(aspect,))
    theme_current = _theme(aspects=(aspect,))
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, theme_previous, theme_current)

    prompt = client.calls[0]["prompt"]
    assert _CONTINUITY_HEADER in prompt
    assert "saturn" in prompt and "square" in prompt and "sun" in prompt
    assert "continuazione" in prompt
    assert "novità" in prompt


def test_tightened_aspect_is_rendered_as_an_approach_not_a_sudden_event() -> None:
    theme_previous = _theme(
        aspects=(_theme_aspect(perfected_at=None, never_perfected=True, orb_exit_at=None),)
    )
    theme_current = _theme(
        aspects=(_theme_aspect(perfected_at=_T1, never_perfected=False, orb_exit_at=None),)
    )
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, theme_previous, theme_current)

    prompt = client.calls[0]["prompt"]
    assert _CONTINUITY_HEADER in prompt
    assert "si è stretto" in prompt


def test_resolved_aspect_still_present_in_current_is_not_marked_uncitable() -> None:
    """A "resolved" Aspect whose element separated this month (``orb_exit_at``
    newly set) but whose identity is still present in ``theme_current`` is
    grounded -- it must not carry the "no id" caveat."""
    theme_previous = _theme(aspects=(_theme_aspect(orb_exit_at=None),))
    resolved_current = _theme_aspect(orb_exit_at=_T2)
    theme_current = _theme(aspects=(resolved_current,))
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, theme_previous, theme_current)

    prompt = client.calls[0]["prompt"]
    assert "si è risolto" in prompt
    assert "non presente nel Payload di questo mese" not in prompt


def test_resolved_aspect_absent_from_current_instructs_no_citation() -> None:
    """Review loop 1 finding: an element entirely absent from
    ``theme_current`` (``derive_theme()``'s "no top-N truncation" contract
    means it genuinely is not anywhere in this month's Payload) must be
    instructed, if mentioned at all, without a citation for that claim."""
    theme_previous = _theme(aspects=(_theme_aspect(),))
    theme_current = _theme(aspects=())
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, theme_previous, theme_current)

    prompt = client.calls[0]["prompt"]
    assert "si è risolto" in prompt
    assert "non presente nel Payload di questo mese: se lo menzioni, non citare un id" in prompt


def test_combined_signals_a_tightened_aspect_and_a_resolved_retrograde_together() -> None:
    """Story 4.7 Tasks: more than one simultaneous continuity signal must
    render correctly together in one call."""
    tightened_previous_aspect = _theme_aspect(
        transiting_body="mars", perfected_at=None, never_perfected=True, orb_exit_at=None
    )
    tightened_current_aspect = _theme_aspect(
        transiting_body="mars", perfected_at=_T1, never_perfected=False, orb_exit_at=None
    )
    resolved_retrograde = _retrograde(body="jupiter")
    theme_previous = _theme(
        aspects=(tightened_previous_aspect,), retrogrades=(resolved_retrograde,)
    )
    theme_current = _theme(aspects=(tightened_current_aspect,), retrogrades=())
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, theme_previous, theme_current)

    prompt = client.calls[0]["prompt"]
    assert "mars" in prompt and "si è stretto" in prompt
    assert "jupiter" in prompt and "conclusa" in prompt
    assert "non presente nel Payload di questo mese" in prompt


def test_nothing_significant_changed_instructs_saying_so_plainly() -> None:
    aspect = _theme_aspect(perfected_at=_T0, orb_exit_at=None)
    theme_previous = _theme(aspects=(aspect,))
    theme_current = _theme(aspects=(aspect,))
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, theme_previous, theme_current)

    prompt = client.calls[0]["prompt"]
    assert _NOTHING_SIGNIFICANT_CHANGED_STATEMENT in prompt


def test_nothing_significant_changed_statement_is_absent_when_something_did_change() -> None:
    theme_previous = _theme(aspects=(_theme_aspect(orb_exit_at=None),))
    theme_current = _theme(aspects=(_theme_aspect(orb_exit_at=_T2),))
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, theme_previous, theme_current)

    prompt = client.calls[0]["prompt"]
    assert _NOTHING_SIGNIFICANT_CHANGED_STATEMENT not in prompt


def test_all_new_elements_omit_the_continuity_header_entirely() -> None:
    """Review loop 1 finding (dangling header): when every element this
    month is ``"new"``, there is nothing to render beneath the header and
    ``nothing_significant_changed`` is ``False`` -- the header must be
    omitted entirely, not left dangling over an empty list."""
    theme_previous = _theme(aspects=())
    theme_current = _theme(aspects=(_theme_aspect(),))
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    _one(generator, payload, theme_previous, theme_current)

    prompt = client.calls[0]["prompt"]
    assert _CONTINUITY_HEADER not in prompt
    assert _NOTHING_SIGNIFICANT_CHANGED_STATEMENT not in prompt


# --- sprint-change-proposal-2026-09-18: an id alias leaking into "text" -----


def test_the_italian_conjunction_e_alone_is_never_flagged_as_a_leaked_alias() -> None:
    """ "e" (the conjunction "and") is one of the most common words in
    Italian prose -- the pattern must require at least one trailing digit
    fused to it, never match the bare word."""
    payload = _payload_with_ids(_KNOWN_ID)
    response = _section_response(
        {
            "text": "Marte e Venere si oppongono, e questo richiede attenzione.",
            "entry_ids": [_KNOWN_ID],
        }
    )
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = _one(generator, payload, None, _EMPTY_THEME)

    assert draft[0].text == ("Marte e Venere si oppongono, e questo richiede attenzione.")


# --- Matrix row: model cites an unknown entry id -----------------------------


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

    response = _section_response({"text": "Marte in trigono a Venere.", "entry_ids": [real_id]})
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = _one(generator, frozen, None, _EMPTY_THEME)

    assert draft[0].entry_ids == (real_id,)


# --- Matrix row: model writes a date in Section 6 or 7 -----------------------


@pytest.mark.parametrize(
    "sentence_text",
    [
        "Il 15 gennaio è una buona giornata per agire.",
        "Il 3 marzo porta chiarezza.",
        "La data 2026-01-15 è favorevole.",
        "Occasione il 15.01.",
        "Occasione il 15.01.2026.",
        "Occasione il 15 gen.",
        "Occasione il 15 gen più tardi.",
        "Occasione il 1° feb.",
    ],
)
def test_a_date_token_in_giorni_favorevoli_raises_at_the_date_token_step(
    sentence_text: str,
) -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    response = _section_response({"text": sentence_text, "entry_ids": []})
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        _one(generator, payload, None, _EMPTY_THEME, section="giorni_favorevoli")

    assert caught.value.step == "date_token_validation"
    assert sentence_text in str(caught.value)


def test_a_date_token_in_giorni_di_attenzione_raises_at_the_date_token_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    response = _section_response({"text": "Attenzione il 22 ottobre.", "entry_ids": []})
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        _one(generator, payload, None, _EMPTY_THEME, section="giorni_di_attenzione")

    assert caught.value.step == "date_token_validation"


@pytest.mark.parametrize(
    "sentence_text",
    [
        "Ci sono 3 mare da attraversare.",
        "Analizziamo 3 set di dati distinti.",
        "Buon momento soprattutto verso le 15.30.",
        "Buon momento alle 9.45 del mattino.",
        "Le probabilità aumentano di 1.5 volte.",
    ],
)
def test_a_non_date_lookalike_in_giorni_favorevoli_is_not_flagged(
    sentence_text: str,
) -> None:
    """``\\b`` after the month alternation terminates an abbreviation, and
    ``set`` is deliberately not an abbreviation -- ``3 mare`` / ``3 set di
    dati`` are not date tokens. The numeric branch's month/zero-padding
    constraint also keeps clock times (``15.30``, ``9.45``) and decimals
    (``1.5``) from being flagged."""
    payload = _payload_with_ids(_KNOWN_ID)
    response = _section_response({"text": sentence_text, "entry_ids": []})
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = _one(generator, payload, None, _EMPTY_THEME, section="giorni_favorevoli")

    assert draft[0].text == sentence_text


def test_a_date_shaped_word_elsewhere_is_not_flagged_as_a_date_token() -> None:
    """The heuristic is about giorni_favorevoli/giorni_di_attenzione only --
    a month name appearing in prose elsewhere (e.g. describing a transit in
    energia_generale) is not itself a violation of this story's rule."""
    payload = _payload_with_ids(_KNOWN_ID)
    response = _section_response(
        {"text": "Un transito di gennaio continua a farsi sentire.", "entry_ids": [_KNOWN_ID]}
    )
    client = _FakeGeminiClient(response=response)
    generator = GeminiGenerator(api_key="unused", client=client)

    draft = _one(generator, payload, None, _EMPTY_THEME)

    assert draft[0].text == "Un transito di gennaio continua a farsi sentire."


# --- epic-4-retro-item-31: prompt construction raises before the network call ---


def test_a_prompt_construction_failure_surfaces_as_a_typed_generation_error() -> None:
    """``_build_system_instruction``/``_build_prompt`` sit inside their own
    ``try`` now (epic-4-retro-item-31): a non-``GenerationError`` raised
    while building the prompt (here a payload value ``canonical_json_bytes``
    cannot serialize) becomes ``GenerationError(step="prompt_construction")``
    ``from`` the original, never a raw ``TypeError`` -- and the provider is
    never reached."""
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as caught:
        _one(generator, {"unserializable": object()}, None, _EMPTY_THEME)

    assert caught.value.step == "prompt_construction"
    assert isinstance(caught.value.__cause__, TypeError)
    assert client.calls == []


# --- Matrix row: Gemini call raises or times out -----------------------------


# --- Matrix row: malformed / non-JSON model response -------------------------


# --- The Style Guide is a required argument, never optional ------------------


def test_calling_generate_section_without_a_style_guide_raises_type_error() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    client = _FakeGeminiClient(response=_EMPTY_SECTION_RESPONSE)
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(TypeError):
        generator.generate_section(  # type: ignore[call-arg]
            "energia_generale", payload, theme_previous=None, theme_current=_EMPTY_THEME
        )


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
        def generate_content(self, *, model: str, contents: str, config: Any) -> _FakeResponse:
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return _FakeResponse()

    class _FakeSDKClient:
        def __init__(self, api_key: str) -> None:
            captured["api_key"] = api_key
            self.models = _FakeModels()

    monkeypatch.setattr("shell.adapters.gemini.generator.genai.Client", _FakeSDKClient)

    wrapper = _GoogleGenAIClient(api_key="secret-key", model="gemini-2.5-pro")
    result = wrapper.generate_content(
        system_instruction="be nice", prompt="hello", response_schema={"type": "object"}
    )

    assert result == '{"ok": true}'
    assert captured["api_key"] == "secret-key"
    assert captured["model"] == "gemini-2.5-pro"
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


def test_the_injected_model_reaches_the_sdk_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """``model`` flows from ``Settings`` through ``GeminiGenerator`` to
    ``client.models.generate_content(model=...)``."""
    from shell.adapters.gemini import generator as generator_module

    seen: dict[str, object] = {}

    class _FakeModels:
        def generate_content(self, **kwargs: object) -> object:
            seen.update(kwargs)
            return type("Response", (), {"text": "{}"})()

    class _FakeSdkClient:
        def __init__(self, api_key: str) -> None:
            self.models = _FakeModels()

    monkeypatch.setattr(generator_module.genai, "Client", _FakeSdkClient)

    wrapped = generator_module.GeminiGenerator("unused", model="gemini-2.5-pro")._client
    wrapped.generate_content(system_instruction="s", prompt="p", response_schema={})

    assert seen["model"] == "gemini-2.5-pro"


def test_generator_for_settings_passes_the_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shell.config import load_settings
    from shell.runner import generators as scheduler
    from tests.test_config import environment_with

    seen: dict[str, object] = {}

    class _Spy:
        def __init__(self, api_key: str, *, model: str) -> None:
            seen["model"] = model

    monkeypatch.setattr(scheduler, "GeminiGenerator", _Spy)
    settings = load_settings(
        environment_with(ENVIRONMENT="production", GEMINI_MODEL="gemini-2.5-pro")
    )

    scheduler.generator_for_settings(settings)

    assert seen["model"] == "gemini-2.5-pro"


# --- Story 10.3: generate_section ---------------------------------------------


def _section_response(*sentences: dict[str, Any]) -> str:
    return json.dumps({"sentences": list(sentences)})


def _section_generator(response: str | None) -> tuple[GeminiGenerator, _FakeGeminiClient]:
    client = _FakeGeminiClient(response=response)
    return GeminiGenerator(api_key="unused", client=client), client


def _two_id_aliases() -> dict[str, str]:
    return _build_id_aliases(frozenset({_KNOWN_ID, _ANOTHER_KNOWN_ID}))


def test_generate_section_narrative_translates_aliases_back_to_real_ids() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    aliases = _two_id_aliases()
    generator, client = _section_generator(
        _section_response({"text": "Una frase.", "entry_ids": [aliases[_KNOWN_ID]]})
    )

    sentences = generator.generate_section("amore", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert sentences[0].text == "Una frase."
    assert sentences[0].entry_ids == (_KNOWN_ID,)
    assert len(client.calls) == 1


def test_generate_section_day_list_schema_pins_count_and_one_id_per_sentence() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    aliases = _two_id_aliases()
    generator, client = _section_generator(
        _section_response({"text": "Voce.", "entry_ids": [aliases[_ANOTHER_KNOWN_ID]]})
    )

    generator.generate_section("giorni_favorevoli", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    schema = client.calls[0]["response_schema"]
    sentences = schema["properties"]["sentences"]
    assert sentences["minItems"] == sentences["maxItems"] == 1
    entry_ids = sentences["items"]["properties"]["entry_ids"]
    assert entry_ids["minItems"] == entry_ids["maxItems"] == 1
    assert entry_ids["items"]["enum"] == sorted(aliases.values())


def test_generate_section_narrative_schema_is_unconstrained_in_length() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    generator, client = _section_generator(_section_response())

    generator.generate_section("amore", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    sentences = client.calls[0]["response_schema"]["properties"]["sentences"]
    assert "minItems" not in sentences
    assert "minItems" not in sentences["items"]["properties"]["entry_ids"]


def test_generate_section_day_list_missing_coverage_raises() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    generator, _ = _section_generator(_section_response())

    with pytest.raises(GenerationError) as excinfo:
        generator.generate_section("giorni_favorevoli", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert excinfo.value.step == "day_list_coverage_validation"


def test_generate_section_prompts_share_an_identical_prefix_and_end_with_the_instruction() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    aliases = _two_id_aliases()
    previous = _theme(aspects=(_theme_aspect(),))
    current = _theme(aspects=(_theme_aspect(perfected_at=None),))
    day_list_reply = _section_response({"text": "Voce.", "entry_ids": [aliases[_ANOTHER_KNOWN_ID]]})
    generator, client = _section_generator(day_list_reply)

    generator.generate_section("giorni_favorevoli", payload, _STYLE_GUIDE, previous, current)
    generator.generate_section("amore", payload, _STYLE_GUIDE, previous, current)

    first, second = client.calls
    assert first["system_instruction"] == second["system_instruction"]
    marker = "La Sezione da scrivere è"
    first_prefix, first_instruction = first["prompt"].split(marker)
    second_prefix, second_instruction = second["prompt"].split(marker)
    assert first_prefix == second_prefix
    assert "--- PAYLOAD (JSON) ---" in first_prefix
    assert first_instruction.startswith(' "giorni_favorevoli"')
    assert second_instruction.startswith(' "amore"')
    assert "esattamente 1 eventi" in first_instruction
    assert "esattamente" not in second_instruction


def test_generate_section_accepts_an_empty_day_list() -> None:
    payload = _payload_with_ids(_KNOWN_ID)
    generator, client = _section_generator(_section_response())

    sentences = generator.generate_section(
        "giorni_di_attenzione", payload, _STYLE_GUIDE, None, _EMPTY_THEME
    )

    assert sentences == ()
    schema = client.calls[0]["response_schema"]["properties"]["sentences"]
    assert schema["minItems"] == schema["maxItems"] == 0


def test_consiglio_finale_prompt_carries_the_other_texts_but_never_their_ids() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    aliases = _two_id_aliases()
    written = {
        "amore": (Sentence(text="Testo dell'amore.", entry_ids=(_KNOWN_ID,)),),
        "lavoro": (Sentence(text="Testo del lavoro.", entry_ids=(_ANOTHER_KNOWN_ID,)),),
    }
    generator, client = _section_generator(
        _section_response({"text": "Consiglio.", "entry_ids": [aliases[_KNOWN_ID]]})
    )

    sentences = generator.generate_section(
        "consiglio_finale", payload, _STYLE_GUIDE, None, _EMPTY_THEME, written
    )

    instruction = client.calls[0]["prompt"].split("--- SEZIONI GIÀ SCRITTE ---")[1]
    assert "Testo dell'amore." in instruction
    assert "Testo del lavoro." in instruction
    for token in (_KNOWN_ID, _ANOTHER_KNOWN_ID, *aliases.values()):
        assert token not in instruction
    assert sentences[0].entry_ids == (_KNOWN_ID,)


def test_other_sections_ignore_written_sections() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    written = {"amore": (Sentence(text="Testo dell'amore.", entry_ids=()),)}
    generator, client = _section_generator(_section_response())

    generator.generate_section("lavoro", payload, _STYLE_GUIDE, None, _EMPTY_THEME, written)

    assert "Testo dell'amore." not in client.calls[0]["prompt"]


def test_generate_section_strips_an_alias_leak_and_cites_it() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    aliases = _two_id_aliases()
    generator, _ = _section_generator(
        _section_response(
            {
                "text": "Giove è in congiunzione (e1, e2), e questo conta.",
                "entry_ids": [aliases[_KNOWN_ID]],
            }
        )
    )

    sentences = generator.generate_section("amore", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert sentences[0].text == "Giove è in congiunzione, e questo conta."
    assert sentences[0].entry_ids == (_KNOWN_ID, _ANOTHER_KNOWN_ID)


def test_generate_section_strips_a_bare_alias_and_ignores_an_unknown_one() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    generator, _ = _section_generator(
        _section_response({"text": "Il transito e999 pesa.", "entry_ids": []})
    )

    sentences = generator.generate_section("amore", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert sentences[0].text == "Il transito pesa."
    assert sentences[0].entry_ids == ()


def test_generate_section_keeps_the_conjunction_e() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    generator, _ = _section_generator(
        _section_response({"text": "Sole e Luna dialogano.", "entry_ids": []})
    )

    sentences = generator.generate_section("amore", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert sentences[0].text == "Sole e Luna dialogano."


def test_generate_section_unknown_id_raises_at_the_citation_step() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    generator, _ = _section_generator(
        _section_response({"text": "Frase.", "entry_ids": ["not-an-alias"]})
    )

    with pytest.raises(GenerationError) as excinfo:
        generator.generate_section("amore", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert excinfo.value.step == "citation_validation"


def test_generate_section_date_token_in_a_day_list_section_raises() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    aliases = _two_id_aliases()
    generator, _ = _section_generator(
        _section_response(
            {"text": "Il 15 gennaio va bene.", "entry_ids": [aliases[_ANOTHER_KNOWN_ID]]}
        )
    )

    with pytest.raises(GenerationError) as excinfo:
        generator.generate_section("giorni_favorevoli", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert excinfo.value.step == "date_token_validation"


def test_generate_section_a_date_in_a_narrative_section_is_allowed() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    generator, _ = _section_generator(
        _section_response({"text": "Il 15 gennaio.", "entry_ids": []})
    )

    sentences = generator.generate_section("amore", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    assert sentences[0].text == "Il 15 gennaio."


@pytest.mark.parametrize(
    ("response", "step"),
    [
        (None, "parsing"),
        ("not json", "parsing"),
        (json.dumps({"other": []}), "parsing"),
        (json.dumps({"sentences": "x"}), "parsing"),
    ],
)
def test_generate_section_bad_responses_raise_at_the_parsing_step(
    response: str | None, step: str
) -> None:
    generator, _ = _section_generator(response)

    with pytest.raises(GenerationError) as excinfo:
        generator.generate_section(
            "amore", _payload_with_ids(_KNOWN_ID), _STYLE_GUIDE, None, _EMPTY_THEME
        )

    assert excinfo.value.step == step


def test_generate_section_client_failure_raises_at_the_request_step() -> None:
    client = _FakeGeminiClient(error=RuntimeError("boom"))
    generator = GeminiGenerator(api_key="unused", client=client)

    with pytest.raises(GenerationError) as excinfo:
        generator.generate_section(
            "amore", _payload_with_ids(_KNOWN_ID), _STYLE_GUIDE, None, _EMPTY_THEME
        )

    assert excinfo.value.step == "request"


def test_generate_section_unknown_section_is_rejected_before_any_call() -> None:
    generator, client = _section_generator(_section_response())

    with pytest.raises(ValueError, match="unknown Section"):
        generator.generate_section(
            "foo", _payload_with_ids(_KNOWN_ID), _STYLE_GUIDE, None, _EMPTY_THEME
        )

    assert client.calls == []


def test_style_guide_has_no_default_and_cannot_be_omitted() -> None:
    import inspect

    signature = inspect.signature(GeminiGenerator.generate_section)
    assert signature.parameters["style_guide"].default is inspect.Parameter.empty


def test_the_whole_report_generate_call_is_gone() -> None:
    """Story 10.4: a Report is written Section by Section; no adapter offers a
    one-call whole-report path any more."""
    from shell.adapters.local.generator import RecordedResponseGenerator

    assert not hasattr(GeminiGenerator, "generate")
    assert not hasattr(RecordedResponseGenerator, "generate")


def test_the_section_prompt_forbids_a_perfection_date_for_a_never_perfected_aspect() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    generator, client = _section_generator(_section_response())

    generator.generate_section("amore", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    prompt = client.calls[0]["prompt"]
    assert '"never_perfected": true' in prompt
    assert "non scrivere MAI una data di perfezionamento" in prompt


def test_the_section_prompt_forbids_date_ranges_and_approximations() -> None:
    payload = _payload_with_ids(_KNOWN_ID, _ANOTHER_KNOWN_ID)
    generator, client = _section_generator(_section_response())

    generator.generate_section("denaro", payload, _STYLE_GUIDE, None, _EMPTY_THEME)

    prompt = client.calls[0]["prompt"]
    assert "MAI intervalli" in prompt
    assert "intorno al 10 gennaio" in prompt
