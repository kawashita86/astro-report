"""``GeminiGenerator``: the ``Generator`` port implementation this
application runs against (Story 4.5, AD-9) -- exactly one adapter, no
runtime failover to a second provider, ever.

Holds no database handle, no filesystem access and no tool definitions
(AD-3): it is a pure function of ``generate()``'s four arguments plus one
network call to Gemini. The Style Guide and both ``ReportTheme``s are turned
into a prompt asking for cited structure, never free prose (AD-6); the
response is parsed against the exact eight-Section shape and validated --
every cited ``entry_id`` must be present somewhere in ``payload``, and
neither ``giorni_favorevoli`` nor ``giorni_di_attenzione`` may contain a
date-shaped token (dates there are code-projected upstream, Story 3.7) --
before a ``GeneratedDraft`` is ever returned.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from google import genai
from google.genai import types

from core.errors import GenerationError
from core.payload.freeze import canonical_json_bytes
from core.types.generation import GeneratedDraft, Sentence
from core.types.memory import ReportTheme
from shell.ports.generator import StyleGuideVersion

__all__ = ["GeminiGenerator"]

#: Free tier, EEA data terms (AD-9's own technical decision) -- the exactly
#: one Generator adapter this application is configured against.
_MODEL = "gemini-2.5-flash"

#: The eight Section field names, in ``GeneratedDraft``'s own fixed order
#: (AD-6) -- introspected rather than hand-listed so a future field is
#: picked up automatically instead of silently dropped from the prompt/schema.
_SECTION_FIELD_NAMES: tuple[str, ...] = tuple(
    field.name for field in dataclass_fields(GeneratedDraft)
)

#: The two Sections where dates are code-projected upstream (Story 3.7) --
#: the model must never write one itself.
_DATE_TOKEN_SECTIONS = frozenset({"giorni_favorevoli", "giorni_di_attenzione"})

_ITALIAN_MONTHS = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)

#: Best-effort regex heuristic (Design Notes), not a completeness guarantee:
#: an ISO date, a day-of-month (optionally with a degree-sign ordinal, e.g.
#: "1°") followed by an Italian month name, or a numeric ``DD/MM``/``DD-MM``
#: pair. Deliberately does not attempt spelled-out ordinals ("il primo
#: gennaio") -- genuinely out of scope for a regex.
_DATE_TOKEN_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"  # ISO date, e.g. "2026-01-15"
    r"|\b\d{1,2}°?\s+(?:" + "|".join(_ITALIAN_MONTHS) + r")\b"  # "15 gennaio" / "1° gennaio"
    r"|\b\d{1,2}[/-]\d{1,2}\b",  # "15/01" / "15-01"
    re.IGNORECASE,
)

_SENTENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "entry_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "entry_ids"],
}

#: The JSON Schema the model's structured response must match -- one array
#: of {text, entry_ids} objects per Section, all eight Sections required.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        name: {"type": "array", "items": _SENTENCE_SCHEMA} for name in _SECTION_FIELD_NAMES
    },
    "required": list(_SECTION_FIELD_NAMES),
}


class _GeminiClient(Protocol):
    def generate_content(
        self, *, system_instruction: str, prompt: str, response_schema: dict[str, Any]
    ) -> str | None:
        """Return the model's raw response text -- expected to be a JSON
        document matching ``response_schema`` -- or ``None`` if the model
        returned no text."""
        ...


class _GoogleGenAIClient:
    """The default ``_GeminiClient``: wraps ``google.genai.Client`` (whose
    real call shape is ``client.models.generate_content(model=..., contents=...,
    config=...)``) behind this adapter's own narrow Protocol -- mirrors
    ``NominatimGeocoder``'s constructor-injected client pattern
    (``shell/adapters/nominatim/geocoder.py``), so a test's fake ``_GeminiClient``
    never needs to know the real SDK's shape either.
    """

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    def generate_content(
        self, *, system_instruction: str, prompt: str, response_schema: dict[str, Any]
    ) -> str | None:
        response = self._client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_json_schema=response_schema,
            ),
        )
        return response.text


class GeminiGenerator:
    """The ``Generator`` port implementation this application runs against.

    ``client`` is injectable so tests exercise prompt-building, parsing and
    both validation steps without a real network call or an API key --
    mirrors ``NominatimGeocoder``'s own ``geolocator``/``timezone_finder``
    injection.
    """

    def __init__(self, api_key: str, *, client: _GeminiClient | None = None) -> None:
        self._client = client or _GoogleGenAIClient(api_key)

    def generate(
        self,
        payload: dict,
        style_guide: StyleGuideVersion,
        theme_previous: ReportTheme | None,
        theme_current: ReportTheme,
    ) -> GeneratedDraft:
        system_instruction = _build_system_instruction(style_guide)
        prompt = _build_prompt(payload, theme_previous, theme_current)

        try:
            raw = self._client.generate_content(
                system_instruction=system_instruction,
                prompt=prompt,
                response_schema=_RESPONSE_SCHEMA,
            )
        except Exception as error:
            raise GenerationError("request", f"the Gemini call failed: {error}") from error

        data = _parse_response(raw)
        draft = _build_draft(data)
        _validate_citations(draft, payload)
        _validate_no_date_tokens(draft)
        return draft


def _json_safe(value: Any) -> Any:
    """``Decimal`` -> ``str``, ``datetime`` -> ISO 8601, a frozen dataclass ->
    its fields recursively converted the same way, a tuple/list -> a list of
    converted items -- everything else passes through unchanged.

    A small serializer of this adapter's own, like
    ``shell/adapters/postgres/report_theme.py``'s own private ``_json_safe``
    (not imported -- each adapter owns a small one rather than sharing one),
    needed only to turn a ``ReportTheme`` into the prompt's embedded JSON.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in dataclass_fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _build_system_instruction(style_guide: StyleGuideVersion) -> str:
    return (
        "Sei il redattore dei Report mensili astrologici di Francesco. Scrivi "
        "esclusivamente in italiano, seguendo con precisione lo Style Guide "
        f"riportato qui sotto (versione {style_guide.version}). Non inventare mai "
        "fatti che non siano presenti nel Payload fornito nel messaggio utente.\n\n"
        f"--- STYLE GUIDE (v{style_guide.version}) ---\n{style_guide.content}"
    )


def _build_prompt(
    payload: dict[str, Any],
    theme_previous: ReportTheme | None,
    theme_current: ReportTheme,
) -> str:
    payload_json = canonical_json_bytes(payload).decode()
    theme_current_json = canonical_json_bytes(_json_safe(theme_current)).decode()
    theme_previous_json = (
        "null"
        if theme_previous is None
        else canonical_json_bytes(_json_safe(theme_previous)).decode()
    )
    sections_list = "\n".join(f"- {name}" for name in _SECTION_FIELD_NAMES)

    return (
        "Genera il Report mensile come struttura citata, non come prosa libera.\n\n"
        "Restituisci esattamente le otto Sezioni seguenti, in questo ordine, come "
        "chiavi dell'oggetto JSON:\n"
        f"{sections_list}\n\n"
        'Ogni Sezione è una lista di frasi; ogni frase ha due campi: "text" (la '
        'frase in italiano) e "entry_ids" (gli id degli eventi del Payload su cui '
        "la frase si basa -- ogni affermazione specifica deve citare almeno un id "
        "valido).\n\n"
        'Le Sezioni "giorni_favorevoli" e "giorni_di_attenzione" non devono MAI '
        "contenere una data (né un giorno del mese con un nome di mese, né una "
        "data in formato ISO): le date sono già proiettate a monte dal codice.\n\n"
        'Se "theme_previous" è null, questo è il primo Report per questo Cliente: '
        "non fare alcun riferimento a mesi precedenti. Altrimenti, tratta un "
        'transito ancora attivo in "theme_previous" come una continuazione '
        "(spostato, si è stretto, si è risolto), mai come una novità; se nulla di "
        "significativo è cambiato, dillo esplicitamente invece di inventare un "
        "cambiamento.\n\n"
        f"--- PAYLOAD (JSON) ---\n{payload_json}\n\n"
        f"--- THEME_PREVIOUS (JSON, null se primo Report) ---\n{theme_previous_json}\n\n"
        f"--- THEME_CURRENT (JSON) ---\n{theme_current_json}\n"
    )


def _parse_response(raw: str | None) -> dict[str, Any]:
    if raw is None:
        raise GenerationError("parsing", "Gemini returned no response text.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GenerationError(
            "parsing", f"the model response was not valid JSON: {error}"
        ) from error
    if not isinstance(data, dict):
        raise GenerationError(
            "parsing",
            f"the model response was not a JSON object (got {type(data).__name__}).",
        )
    return data


def _parse_sentences(section: str, raw_sentences: Any) -> tuple[Sentence, ...]:
    if not isinstance(raw_sentences, list):
        raise GenerationError(
            "parsing", f"Section {section!r} was not a list of sentences."
        )
    sentences: list[Sentence] = []
    for index, raw_sentence in enumerate(raw_sentences):
        if not isinstance(raw_sentence, dict):
            raise GenerationError(
                "parsing", f"Section {section!r}, sentence {index}: not a JSON object."
            )
        text = raw_sentence.get("text")
        entry_ids = raw_sentence.get("entry_ids")
        if not isinstance(text, str):
            raise GenerationError(
                "parsing",
                f"Section {section!r}, sentence {index}: missing or non-string 'text'.",
            )
        if not isinstance(entry_ids, list) or not all(
            isinstance(item, str) for item in entry_ids
        ):
            raise GenerationError(
                "parsing",
                f"Section {section!r}, sentence {index}: 'entry_ids' must be a list "
                "of strings.",
            )
        sentences.append(Sentence(text=text, entry_ids=tuple(entry_ids)))
    return tuple(sentences)


def _build_draft(data: dict[str, Any]) -> GeneratedDraft:
    fields: dict[str, tuple[Sentence, ...]] = {}
    for name in _SECTION_FIELD_NAMES:
        if name not in data:
            raise GenerationError(
                "parsing", f"the model response is missing Section {name!r}."
            )
        fields[name] = _parse_sentences(name, data[name])
    return GeneratedDraft(**fields)


def _collect_known_entry_ids(payload: dict[str, Any]) -> frozenset[str]:
    """Every ``"id"`` present anywhere in ``payload`` -- both ``"sections"``
    and ``"day_lists"`` entries (Boundaries) -- collected by a generic
    recursive walk rather than one hand-written per Section/day-list, since
    an entry id is global and content-derived (AD-4, Design Notes): the same
    Aspect/Lunation/Retrograde may legitimately recur under more than one
    Section's own slice.
    """
    ids: set[str] = set()

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            entry_id = value.get("id")
            if isinstance(entry_id, str):
                ids.add(entry_id)
            for item in value.values():
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(payload)
    return frozenset(ids)


def _validate_citations(draft: GeneratedDraft, payload: dict[str, Any]) -> None:
    known_ids = _collect_known_entry_ids(payload)
    for field in dataclass_fields(draft):
        for sentence in getattr(draft, field.name):
            for entry_id in sentence.entry_ids:
                if entry_id not in known_ids:
                    raise GenerationError(
                        "citation_validation",
                        f"sentence {sentence.text!r} in Section {field.name!r} cites "
                        f"unknown entry id {entry_id!r}, absent from the Payload.",
                    )


def _validate_no_date_tokens(draft: GeneratedDraft) -> None:
    for section in _DATE_TOKEN_SECTIONS:
        for sentence in getattr(draft, section):
            if _DATE_TOKEN_PATTERN.search(sentence.text):
                raise GenerationError(
                    "date_token_validation",
                    f"sentence {sentence.text!r} in Section {section!r} contains a "
                    "date-shaped token; dates in this Section are code-projected "
                    "upstream (Story 3.7) and must never be written by the model.",
                )
