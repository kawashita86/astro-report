"""``GeminiGenerator``: the ``Generator`` port implementation this
application runs against (Story 4.5, AD-9) -- exactly one adapter, no
runtime failover to a second provider, ever.

Holds no database handle, no filesystem access and no tool definitions
(AD-3): it is a pure function of ``generate()``'s four arguments plus one
network call to Gemini. The Style Guide and both ``ReportTheme``s are turned
into a prompt asking for cited structure, never free prose (AD-6); the
response is parsed against the exact eight-Section shape and validated --
every cited ``entry_id`` must be present somewhere in ``payload``, neither
``giorni_favorevoli`` nor ``giorni_di_attenzione`` may contain a date-shaped
token (dates there are code-projected upstream, Story 3.7), and every entry
in ``payload["day_lists"]`` must be cited by at least one sentence in its
own Section -- before a ``GeneratedDraft`` is ever returned.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from google import genai
from google.genai import types

from core.errors import GenerationError
from core.memory.diff import diff_themes
from core.payload.freeze import canonical_json_bytes
from core.types.generation import GeneratedDraft, Sentence
from core.types.memory import AspectChange, ReportTheme, RetrogradeChange, ThemeAspect, ThemeDiff
from shell.adapters.generation.validation import (
    _SECTION_FIELD_NAMES,
    _validate_citations,
    _validate_day_list_coverage,
    _validate_no_date_tokens,
)
from shell.ports.generator import StyleGuideVersion

__all__ = ["GeminiGenerator"]

#: Free tier, EEA data terms (AD-9's own technical decision) -- the exactly
#: one Generator adapter this application is configured against.
_MODEL = "gemini-2.5-flash"

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
        try:
            system_instruction = _build_system_instruction(style_guide)
            prompt = _build_prompt(payload, theme_previous, theme_current)
        except GenerationError:
            raise
        except Exception as error:
            raise GenerationError(
                "prompt_construction",
                f"building the system instruction / prompt failed: {error}",
            ) from error

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
        _validate_day_list_coverage(draft, payload)
        return draft


#: Rendered per matched/unmatched ``AspectChange.status`` (Story 4.7, Design
#: Notes) -- ``"new"`` is deliberately absent: a fresh Aspect is never
#: mentioned as continuity, it is simply this month's material (the Payload
#: itself already carries it).
_ASPECT_STATUS_TEMPLATES: dict[str, str] = {
    "still_active": (
        "{transiting_body} {aspect} {natal_point}: transito ancora attivo dal "
        "mese precedente -- trattalo come una continuazione, mai come una novità."
    ),
    "tightened": (
        "{transiting_body} {aspect} {natal_point}: si è stretto rispetto al mese "
        "precedente (prima non ancora perfezionato, ora sì) -- descrivilo come un "
        "avvicinamento, non come un evento improvviso."
    ),
    "resolved": (
        "{transiting_body} {aspect} {natal_point}: si è risolto rispetto al mese "
        "precedente (l'orbita si è chiusa) -- trattalo come un capitolo che si "
        "conclude, non reintrodurlo come una novità."
    ),
}

#: Rendered per ``RetrogradeChange.status`` -- no ``"tightened"`` entry, since
#: a ``StandingRetrograde`` carries no tightness signal to newly-perfect
#: (``core/types/memory.py``'s own docstring).
_RETROGRADE_STATUS_TEMPLATES: dict[str, str] = {
    "still_active": (
        "Stazione retrograda di {body}: ancora in corso dal mese precedente -- "
        "trattala come una continuazione, mai come una novità."
    ),
    "resolved": (
        "Stazione retrograda di {body}: conclusa rispetto al mese precedente -- "
        "trattala come un capitolo che si chiude, non reintrodurla come una novità."
    ),
}

#: Appended only to a ``"resolved"`` line whose element's identity is not
#: present in ``theme_current`` at all (review loop 1, Design Notes:
#: "Resolved-and-entirely-absent-from-current") -- ``derive_theme()``'s own
#: "no top-N truncation" contract means such an element genuinely does not
#: appear anywhere in this month's Payload either, so the model must never be
#: invited to cite an ``entry_id`` for that specific claim.
_UNCITED_SUFFIX = (
    " (non presente nel Payload di questo mese: se lo menzioni, non citare un "
    "id per questa affermazione)."
)

_CONTINUITY_HEADER = "Continuità rispetto al mese precedente (fatti calcolati, non da indovinare):"

_FIRST_REPORT_STATEMENT = (
    "Questo è il primo Report per questo Cliente: non fare alcun riferimento a "
    "mesi precedenti."
)

_NOTHING_SIGNIFICANT_CHANGED_STATEMENT = (
    "Nulla di significativo è cambiato rispetto al mese precedente: dillo "
    "esplicitamente nel Report, invece di inventare un cambiamento."
)


def _aspect_identity(aspect: ThemeAspect) -> tuple[str, str, str]:
    return (aspect.transiting_body, aspect.natal_point, aspect.aspect)


def _render_aspect_change(
    change: AspectChange, current_identities: frozenset[tuple[str, str, str]]
) -> str | None:
    template = _ASPECT_STATUS_TEMPLATES.get(change.status)
    if template is None:  # "new" -- never rendered as continuity
        return None
    line = template.format(
        transiting_body=change.aspect.transiting_body,
        aspect=change.aspect.aspect,
        natal_point=change.aspect.natal_point,
    )
    if change.status == "resolved" and _aspect_identity(change.aspect) not in current_identities:
        line += _UNCITED_SUFFIX
    return line


def _render_retrograde_change(
    change: RetrogradeChange, current_bodies: frozenset[str]
) -> str | None:
    template = _RETROGRADE_STATUS_TEMPLATES.get(change.status)
    if template is None:  # "new" -- never rendered as continuity
        return None
    line = template.format(body=change.retrograde.body)
    if change.status == "resolved" and change.retrograde.body not in current_bodies:
        line += _UNCITED_SUFFIX
    return line


def _render_continuity(
    theme_previous: ReportTheme | None,
    theme_current: ReportTheme,
    theme_diff: ThemeDiff | None,
) -> str:
    """Turn ``diff_themes(theme_previous, theme_current)``'s result into the
    prompt's continuity section (Story 4.7).

    Exactly three possible outputs (Design Notes): the first-Report
    statement (``theme_previous is None``); the header plus at least one
    line (a rendered Aspect/Retrograde change, the explicit
    ``nothing_significant_changed`` statement, or both); or ``""`` when there
    is nothing true to render at all -- every changed element this month is
    ``"new"`` and nothing_significant_changed is ``False``, so the header
    would otherwise dangle over an empty list.
    """
    if theme_previous is None:
        return _FIRST_REPORT_STATEMENT
    assert theme_diff is not None, "diff_themes() only returns None when previous is None"

    current_aspect_identities = frozenset(
        _aspect_identity(aspect) for aspect in theme_current.dominant_aspects
    )
    current_retrograde_bodies = frozenset(
        retrograde.body for retrograde in theme_current.standing_retrogrades
    )

    lines = [
        rendered
        for change in theme_diff.aspect_changes
        if (rendered := _render_aspect_change(change, current_aspect_identities)) is not None
    ]
    lines += [
        rendered
        for change in theme_diff.retrograde_changes
        if (rendered := _render_retrograde_change(change, current_retrograde_bodies)) is not None
    ]

    if theme_diff.nothing_significant_changed:
        lines.append(_NOTHING_SIGNIFICANT_CHANGED_STATEMENT)

    if not lines:
        return ""

    return _CONTINUITY_HEADER + "\n" + "\n".join(f"- {line}" for line in lines)


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
    sections_list = "\n".join(f"- {name}" for name in _SECTION_FIELD_NAMES)
    theme_diff = diff_themes(theme_previous, theme_current)
    continuity = _render_continuity(theme_previous, theme_current, theme_diff)
    continuity_block = f"\n\n{continuity}" if continuity else ""

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
        "data in formato ISO): le date sono già proiettate a monte dal codice. "
        "Ogni singolo id presente in payload['day_lists']['giorni_favorevoli'] deve "
        "essere citato da almeno una frase nella Sezione \"giorni_favorevoli\", e ogni "
        "id in payload['day_lists']['giorni_di_attenzione'] deve essere citato da "
        "almeno una frase nella Sezione \"giorni_di_attenzione\": nessun evento di "
        "queste due liste può restare senza una frase che lo descriva."
        f"{continuity_block}\n\n"
        f"--- PAYLOAD (JSON) ---\n{payload_json}\n"
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
