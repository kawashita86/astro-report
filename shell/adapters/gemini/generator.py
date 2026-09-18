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
import re
from dataclasses import fields as dataclass_fields
from typing import Any, Protocol

from google import genai
from google.genai import types

from core.errors import GenerationError
from core.memory.diff import diff_themes
from core.payload.freeze import canonical_json_bytes
from core.types.generation import GeneratedDraft, Sentence
from core.types.memory import AspectChange, ReportTheme, RetrogradeChange, ThemeAspect, ThemeDiff
from shell.adapters.generation.validation import (
    _DATE_TOKEN_SECTIONS,
    _SECTION_FIELD_NAMES,
    _collect_known_entry_ids,
    _validate_citations,
    _validate_day_list_coverage,
    _validate_no_date_tokens,
)
from shell.ports.generator import StyleGuideVersion

__all__ = ["GeminiGenerator"]

#: Free tier, EEA data terms (AD-9's own technical decision) -- the exactly
#: one Generator adapter this application is configured against.
_MODEL = "gemini-2.5-flash"


def _day_list_count(payload: dict[str, Any], section: str) -> int:
    entries = payload.get("day_lists", {}).get(section, [])
    return len(entries) if isinstance(entries, list) else 0


def _build_id_aliases(known_ids: frozenset[str]) -> dict[str, str]:
    """Real (64-char, content-derived) Payload id -> short alias
    (``"e1"``, ``"e2"``, ...), assigned in sorted real-id order so it is
    stable within one call.

    Gemini's structured-output constraint compiler rejects an ``entry_ids``
    ``enum`` built from the real ids directly once a Payload has enough
    entries -- a real incident hit ``400 INVALID_ARGUMENT: The specified
    schema produces a constraint that has too many states for serving`` with
    ~90 64-char hex ids in the schema. Short aliases keep the schema's enum
    small regardless of how many entries the Payload has, and are also far
    less error-prone for the model to reproduce verbatim than a 64-char hex
    string -- a second, independent benefit against citation transcription
    slips, not just a workaround for the API limit.
    """
    return {real_id: f"e{index}" for index, real_id in enumerate(sorted(known_ids), start=1)}


def _aliased_payload_json(payload: dict[str, Any], aliases: dict[str, str]) -> str:
    """``canonical_json_bytes(payload)``'s text with every real ``"id"``
    value replaced by its short alias, so what the model reads in the
    Payload block and what the schema's ``entry_ids`` enum offers are the
    same short strings -- the model never has to translate between the two.
    """
    text = canonical_json_bytes(payload).decode()
    for real_id, alias in aliases.items():
        text = text.replace(f'"{real_id}"', f'"{alias}"')
    return text


def _translate_aliases_to_real_ids(
    draft: GeneratedDraft, alias_to_id: dict[str, str]
) -> GeneratedDraft:
    """The reverse of ``_build_id_aliases``: every ``entry_id`` the model
    returned is an alias (enforced by the response schema's ``enum``) --
    translate each back to its real Payload id before
    ``_validate_citations``/``_validate_day_list_coverage`` (both of which
    compare against the real, untranslated Payload) ever see it. An alias
    absent from ``alias_to_id`` (should be unreachable given the schema
    constraint) passes through unchanged, so it still surfaces as an unknown
    id at the citation-validation step rather than silently vanishing.
    """
    fields = {
        field.name: tuple(
            Sentence(
                text=sentence.text,
                entry_ids=tuple(alias_to_id.get(alias, alias) for alias in sentence.entry_ids),
            )
            for sentence in getattr(draft, field.name)
        )
        for field in dataclass_fields(draft)
    }
    return GeneratedDraft(**fields)


#: An alias token (``"e12"``, ``"e7"``, ...) appearing inside a sentence's
#: own ``"text"`` -- the model is instructed to put every id only in
#: ``entry_ids``, never in the reader-facing prose, but occasionally does
#: anyway (a real generation shipped "Le numerose retrogradazioni
#: planetarie (e49, e17, e55, e41, e26)" straight to a client-facing
#: Report). ``e`` immediately fused to digits, as a whole word, is not a
#: real Italian token under any circumstance -- unlike the bare word "e"
#: (the conjunction "and"), which this pattern never matches since it
#: requires at least one trailing digit.
_ALIAS_TOKEN_IN_TEXT_PATTERN = re.compile(r"\be\d+\b", re.IGNORECASE)


def _validate_no_alias_tokens_in_text(draft: GeneratedDraft) -> None:
    for field in dataclass_fields(draft):
        for sentence in getattr(draft, field.name):
            match = _ALIAS_TOKEN_IN_TEXT_PATTERN.search(sentence.text)
            if match is not None:
                raise GenerationError(
                    "alias_token_in_text",
                    f"sentence {sentence.text!r} in Section {field.name!r} leaks the "
                    f"internal id alias {match.group()!r} into reader-facing prose -- "
                    'ids belong only in "entry_ids", never in "text".',
                )


def _build_response_schema(
    known_ids: frozenset[str], *, favorevoli_count: int, attenzione_count: int
) -> dict[str, Any]:
    """Per-call ``_RESPONSE_SCHEMA``: the same eight-Section shape as
    before, but tightened two ways (sprint-change-proposal-2026-09-18) so the
    model structurally cannot reproduce the two failure classes a real
    generation hit:

    1. ``entry_ids`` is constrained to an ``enum`` of this run's actual
       Payload ids, so an unknown/mistyped id can never be emitted --
       eliminates ``citation_validation`` failures by construction rather
       than only detecting them after the fact.
    2. ``giorni_favorevoli``/``giorni_di_attenzione`` get their own sentence
       shape (``entry_ids`` pinned to exactly one id per sentence) and their
       own array length (pinned to the Payload's actual day-list count) --
       one voce per event, never bundled, so ``day_list_coverage_validation``
       and the renderer's one-row-per-id fan-out (``draft_view.py``) can
       never produce the same voce duplicated across several dates. The six
       narrative Sections keep the original unconstrained-length,
       multi-id-per-sentence shape -- bundling several events into one
       flowing sentence is exactly what the Style Guide's prose sections ask
       for.
    """
    entry_id_schema: dict[str, Any] = {"type": "string", "enum": sorted(known_ids)}
    narrative_sentence_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "entry_ids": {"type": "array", "items": entry_id_schema},
        },
        "required": ["text", "entry_ids"],
    }
    day_list_sentence_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "entry_ids": {
                "type": "array",
                "items": entry_id_schema,
                "minItems": 1,
                "maxItems": 1,
            },
        },
        "required": ["text", "entry_ids"],
    }
    day_list_counts = {
        "giorni_favorevoli": favorevoli_count,
        "giorni_di_attenzione": attenzione_count,
    }
    properties: dict[str, Any] = {}
    for name in _SECTION_FIELD_NAMES:
        if name in _DATE_TOKEN_SECTIONS:
            count = day_list_counts[name]
            properties[name] = {
                "type": "array",
                "items": day_list_sentence_schema,
                "minItems": count,
                "maxItems": count,
            }
        else:
            properties[name] = {"type": "array", "items": narrative_sentence_schema}
    return {"type": "object", "properties": properties, "required": list(_SECTION_FIELD_NAMES)}


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
        aliases = _build_id_aliases(_collect_known_entry_ids(payload))
        alias_to_id = {alias: real_id for real_id, alias in aliases.items()}

        try:
            system_instruction = _build_system_instruction(style_guide)
            prompt = _build_prompt(payload, theme_previous, theme_current, aliases)
        except GenerationError:
            raise
        except Exception as error:
            raise GenerationError(
                "prompt_construction",
                f"building the system instruction / prompt failed: {error}",
            ) from error

        response_schema = _build_response_schema(
            frozenset(aliases.values()),
            favorevoli_count=_day_list_count(payload, "giorni_favorevoli"),
            attenzione_count=_day_list_count(payload, "giorni_di_attenzione"),
        )

        try:
            raw = self._client.generate_content(
                system_instruction=system_instruction,
                prompt=prompt,
                response_schema=response_schema,
            )
        except Exception as error:
            raise GenerationError("request", f"the Gemini call failed: {error}") from error

        data = _parse_response(raw)
        draft = _build_draft(data)
        _validate_no_alias_tokens_in_text(draft)
        draft = _translate_aliases_to_real_ids(draft, alias_to_id)
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
    "Questo è il primo Report per questo Cliente: non fare alcun riferimento a " "mesi precedenti."
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
    aliases: dict[str, str],
) -> str:
    payload_json = _aliased_payload_json(payload, aliases)
    sections_list = "\n".join(f"- {name}" for name in _SECTION_FIELD_NAMES)
    theme_diff = diff_themes(theme_previous, theme_current)
    continuity = _render_continuity(theme_previous, theme_current, theme_diff)
    continuity_block = f"\n\n{continuity}" if continuity else ""
    favorevoli_count = _day_list_count(payload, "giorni_favorevoli")
    attenzione_count = _day_list_count(payload, "giorni_di_attenzione")

    return (
        "Genera il Report mensile come struttura citata, non come prosa libera.\n\n"
        "Restituisci esattamente le otto Sezioni seguenti, in questo ordine, come "
        "chiavi dell'oggetto JSON:\n"
        f"{sections_list}\n\n"
        'Ogni Sezione è una lista di frasi; ogni frase ha due campi: "text" (la '
        'frase in italiano) e "entry_ids" (gli id degli eventi del Payload su cui '
        "la frase si basa -- ogni affermazione specifica deve citare almeno un id "
        'valido). Nel Payload qui sotto ogni evento porta un "id" breve (es. '
        '"e12"): usa esattamente questi identificativi brevi in "entry_ids", mai '
        "un id diverso, più lungo o inventato. Questi id vanno SOLO nel campo "
        '"entry_ids": il campo "text" è prosa rivolta al lettore finale e non deve '
        "mai contenere un id, una sua parte, o un riferimento tra parentesi come "
        '"(e12)" o "(e12, e7)" -- il lettore non vede mai il Payload e un simile '
        "riferimento nel testo sarebbe incomprensibile e da correggere.\n\n"
        'Le Sezioni "giorni_favorevoli" e "giorni_di_attenzione" non devono MAI '
        "contenere una data (né un giorno del mese con un nome di mese, né una "
        "data in formato ISO): le date sono già proiettate a monte dal codice.\n\n"
        f'La Sezione "giorni_favorevoli" contiene esattamente {favorevoli_count} '
        "eventi in payload['day_lists']['giorni_favorevoli']: scrivi esattamente "
        f"{favorevoli_count} frasi in questa Sezione, una per ciascun evento, ognuna "
        'con un solo id in "entry_ids" (mai più di uno). Non accorpare più eventi '
        "sotto la stessa frase, anche quando le date sono vicine o gli eventi sembrano "
        "tematicamente simili: ogni frase descrive un solo evento, e il numero totale "
        "di frasi deve corrispondere esattamente al numero di eventi -- il documento "
        "non ha un limite di lunghezza fisso su questa Sezione, si adatta a quanti "
        "eventi il mese ne offre.\n"
        f'La Sezione "giorni_di_attenzione" contiene esattamente {attenzione_count} '
        f"eventi: applica la stessa regola, {attenzione_count} frasi, una per evento, "
        "un solo id ciascuna, nessun accorpamento."
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
        raise GenerationError("parsing", f"Section {section!r} was not a list of sentences.")
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
        if not isinstance(entry_ids, list) or not all(isinstance(item, str) for item in entry_ids):
            raise GenerationError(
                "parsing",
                f"Section {section!r}, sentence {index}: 'entry_ids' must be a list " "of strings.",
            )
        sentences.append(Sentence(text=text, entry_ids=tuple(entry_ids)))
    return tuple(sentences)


def _build_draft(data: dict[str, Any]) -> GeneratedDraft:
    fields: dict[str, tuple[Sentence, ...]] = {}
    for name in _SECTION_FIELD_NAMES:
        if name not in data:
            raise GenerationError("parsing", f"the model response is missing Section {name!r}.")
        fields[name] = _parse_sentences(name, data[name])
    return GeneratedDraft(**fields)
