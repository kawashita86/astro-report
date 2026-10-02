"""``GeminiGenerator``: the ``Generator`` port implementation this
application runs against (Story 4.5, AD-9) -- exactly one adapter, no
runtime failover to a second provider, ever.

Holds no database handle, no filesystem access and no tool definitions
(AD-3): it is a pure function of ``generate_section()``'s arguments plus one
network call to Gemini per Section (Stories 10.3/10.4: a Report is written one
Section at a time, in parallel, by the ``RunDriver``). The Style Guide and both
``ReportTheme``s are turned into a prompt asking for cited structure, never
free prose (AD-6); the response is parsed against the one-Section shape and
validated -- every cited ``entry_id`` must be present somewhere in ``payload``,
neither ``giorni_favorevoli`` nor ``giorni_di_attenzione`` may contain a
date-shaped token (dates there are code-projected upstream, Story 3.7), and
every entry in ``payload["day_lists"]`` must be cited by at least one sentence
in its own Section -- before the Section's sentences are ever returned.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Protocol

from google import genai
from google.genai import types

from core.errors import GenerationError
from core.memory.diff import diff_themes
from core.payload.freeze import canonical_json_bytes
from core.types.generation import Sentence
from core.types.memory import AspectChange, ReportTheme, RetrogradeChange, ThemeAspect, ThemeDiff
from shell.adapters.generation.validation import (
    _DATE_TOKEN_SECTIONS,
    _SECTION_FIELD_NAMES,
    _collect_known_entry_ids,
    _validate_section_citations,
    _validate_section_day_list_coverage,
    _validate_section_no_date_tokens,
)
from shell.config import DEFAULT_GEMINI_MODEL
from shell.ports.generator import StyleGuideVersion

__all__ = ["GeminiGenerator"]


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


#: An alias token (``"e12"``, ``"e7"``, ...) appearing inside a sentence's
#: own ``"text"`` -- the model is instructed to put every id only in
#: ``entry_ids``, never in the reader-facing prose, but often does anyway (a
#: real generation shipped "Le numerose retrogradazioni planetarie (e49, e17,
#: e55, e41, e26)" straight to a client-facing Report). ``e`` immediately fused
#: to digits, as a whole word, is not a real Italian token under any
#: circumstance -- unlike the bare word "e" (the conjunction "and"), which this
#: pattern never matches since it requires at least one trailing digit.
_ALIAS_TOKEN_IN_TEXT_PATTERN = re.compile(r"\be\d+\b", re.IGNORECASE)

#: A bracketed run of alias tokens, "(e49)" or "(e49, e17 e e55)", with the space
#: before it -- removed whole so no empty parentheses are left behind.
_ALIAS_GROUP_PATTERN = re.compile(
    r"\s*[(\[]\s*e\d+(?:\s*(?:,|;|\be\b|\bed\b)\s*e\d+)*\s*[)\]]", re.IGNORECASE
)


def _strip_alias_tokens_from_text(
    section: str, sentences: tuple[Sentence, ...], known_aliases: frozenset[str]
) -> tuple[Sentence, ...]:
    """Clean leaked id aliases out of reader-facing prose instead of rejecting the draft.

    A leaked alias is a formatting slip, not a wrong fact: the model meant to cite that
    entry. So the token is removed from the text and, outside the date-list Sections
    (whose schema pins exactly one id per sentence), added to the sentence's
    ``entry_ids`` when it is not already there -- the Gate still checks the sentence
    against every entry it cites. Rejecting cost a whole regeneration per slip and
    exhausted the attempt bound on most runs (Story 10.7).
    """
    cleaned: list[Sentence] = []
    for sentence in sentences:
        leaked = _ALIAS_TOKEN_IN_TEXT_PATTERN.findall(sentence.text)
        if not leaked:
            cleaned.append(sentence)
            continue
        text = _ALIAS_GROUP_PATTERN.sub("", sentence.text)
        text = _ALIAS_TOKEN_IN_TEXT_PATTERN.sub("", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        entry_ids = sentence.entry_ids
        if section not in _DATE_TOKEN_SECTIONS:
            extra = tuple(
                dict.fromkeys(
                    a.lower()
                    for a in leaked
                    if a.lower() in known_aliases and a.lower() not in entry_ids
                )
            )
            entry_ids = entry_ids + extra
        cleaned.append(Sentence(text=text, entry_ids=entry_ids))
    return tuple(cleaned)


def _build_section_response_schema(
    section: str, known_ids: frozenset[str], *, day_list_count: int
) -> dict[str, Any]:
    """One-Section counterpart of :func:`_build_response_schema` (Story
    10.3): an object with a single ``sentences`` array -- an object, not a
    bare array, so the structured-output root stays an object. The sentence
    shape, the alias ``enum`` and the day-list pinning (exactly one id per
    sentence, array length equal to the Payload's day-list count) are the
    same as the whole-report schema's, for this Section only.
    """
    entry_id_schema: dict[str, Any] = {"type": "string", "enum": sorted(known_ids)}
    entry_ids_schema: dict[str, Any] = {"type": "array", "items": entry_id_schema}
    sentences_schema: dict[str, Any]
    if section in _DATE_TOKEN_SECTIONS:
        entry_ids_schema = {**entry_ids_schema, "minItems": 1, "maxItems": 1}
        sentences_schema = {"minItems": day_list_count, "maxItems": day_list_count}
    else:
        sentences_schema = {}
    sentences_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "entry_ids": entry_ids_schema},
            "required": ["text", "entry_ids"],
        },
        **sentences_schema,
    }
    return {
        "type": "object",
        "properties": {"sentences": sentences_schema},
        "required": ["sentences"],
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

    def __init__(self, api_key: str, model: str, thinking_budget: int | None = None) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._thinking_budget = thinking_budget

    def generate_content(
        self, *, system_instruction: str, prompt: str, response_schema: dict[str, Any]
    ) -> str | None:
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_json_schema=response_schema,
                # Hidden "thinking" tokens dominated a Section's latency (10-60 s for a
                # ~1,000-token answer); a bounded budget keeps it near 10 s (Story 10.7).
                thinking_config=(
                    None
                    if self._thinking_budget is None
                    else types.ThinkingConfig(thinking_budget=self._thinking_budget)
                ),
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

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_GEMINI_MODEL,
        thinking_budget: int | None = None,
        client: _GeminiClient | None = None,
    ) -> None:
        self._client = client or _GoogleGenAIClient(api_key, model, thinking_budget)

    def generate_section(
        self,
        section: str,
        payload: dict,
        style_guide: StyleGuideVersion,
        theme_previous: ReportTheme | None,
        theme_current: ReportTheme,
        written_sections: Mapping[str, tuple[Sentence, ...]] | None = None,
    ) -> tuple[Sentence, ...]:
        if section not in _SECTION_FIELD_NAMES:
            raise ValueError(f"unknown Section {section!r}; expected one of {_SECTION_FIELD_NAMES}")
        aliases = _build_id_aliases(_collect_known_entry_ids(payload))
        alias_to_id = {alias: real_id for real_id, alias in aliases.items()}

        try:
            system_instruction = _build_system_instruction(style_guide)
            prompt = _build_section_prompt(
                section, payload, theme_previous, theme_current, aliases, written_sections
            )
        except GenerationError:
            raise
        except Exception as error:
            raise GenerationError(
                "prompt_construction",
                f"building the system instruction / prompt failed: {error}",
            ) from error

        response_schema = _build_section_response_schema(
            section,
            frozenset(aliases.values()),
            day_list_count=_day_list_count(payload, section),
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
        if "sentences" not in data:
            raise GenerationError(
                "parsing", f"the model response is missing the 'sentences' list for {section!r}."
            )
        sentences = _parse_sentences(section, data["sentences"])
        sentences = _strip_alias_tokens_from_text(section, sentences, frozenset(aliases.values()))
        sentences = tuple(
            Sentence(
                text=sentence.text,
                entry_ids=tuple(alias_to_id.get(alias, alias) for alias in sentence.entry_ids),
            )
            for sentence in sentences
        )
        _validate_section_citations(section, sentences, payload)
        _validate_section_no_date_tokens(section, sentences)
        _validate_section_day_list_coverage(section, sentences, payload)
        return sentences


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
    "Questo è il primo Report per questo Cliente: non fare alcun riferimento a mesi precedenti."
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


#: The Section-specific instruction appended last by
#: :func:`_build_section_prompt` (Story 10.3). Everything before it -- system
#: instruction, Payload, continuity -- is identical for all eight calls, so
#: the provider's implicit prompt cache can serve the shared prefix.
_SECTION_FRAMING = (
    "Scrivi UNA sola Sezione del Report mensile, come struttura citata e non come "
    'prosa libera, e restituisci un oggetto JSON con la chiave "sentences".\n\n'
    'Ogni frase ha due campi: "text" (la frase in italiano) e "entry_ids" (gli id '
    "degli eventi del Payload su cui la frase si basa -- ogni affermazione specifica "
    'deve citare almeno un id valido). Nel Payload ogni evento porta un "id" breve '
    '(es. "e12"): usa esattamente questi identificativi brevi in "entry_ids", mai un '
    'id diverso, più lungo o inventato. Gli id vanno SOLO in "entry_ids": il campo '
    '"text" è prosa rivolta al lettore finale e non deve mai contenere un id, una '
    'sua parte, o un riferimento tra parentesi come "(e12)".\n\n'
    "Ogni giorno o data che scrivi deve venire dai campi dell'evento che citi. Un "
    'aspetto con "never_perfected": true e "perfected_at": null non diventa mai '
    "esatto nel mese: non scrivere MAI una data di perfezionamento per lui (né "
    '"si perfezionerà il 24 gennaio" né simili); puoi dire solo che entra in orbita '
    '(da "orb_entry_at") o che resta attivo. Se per un evento il Payload non dà una '
    "data, non indicarne nessuna.\n\n"
    "Date: scrivi solo giorni esatti presi dai campi (perfected_at, orb_entry_at, "
    "orb_exit_at, station_at, crossed_at, occurred_at, retrograde_start_utc, "
    "retrograde_end_utc) degli eventi che citi nella stessa frase, un giorno per "
    'evento. MAI intervalli ("tra il 14 e il 23 gennaio"), approssimazioni ("intorno '
    'al 10 gennaio", "verso metà mese") o giorni di tua invenzione: se vuoi indicare '
    'un periodo, usa parole generiche senza numeri ("nella seconda metà del mese"), '
    "e non scrivere nessun giorno che non sia nel campo di un evento citato."
)


#: What each Section is *for* in the whole Report. The eight Sections are written in
#: parallel from the same events, so without a role each one retells the month's headline
#: transits (Consiglio finale most of all); measured by counting six-word runs repeated
#: across Sections (Story 10.7).
_SECTION_BRIEFS: dict[str, str] = {
    "energia_generale": (
        "Ruolo: il quadro generale del mese. Presenta qui, una volta sola, i due o tre "
        "eventi dominanti; le altre Sezioni non li rispiegheranno."
    ),
    "amore": (
        "Ruolo: solo ciò che gli eventi significano per le relazioni e gli affetti. "
        "Non riscrivere il quadro generale del mese né spiegare di nuovo i grandi "
        "transiti dei pianeti lenti: sono già in energia_generale. Se citi un evento "
        "condiviso, nominalo in poche parole e dedica la frase al suo effetto su questa area."
    ),
    "lavoro": (
        "Ruolo: solo ciò che gli eventi significano per il lavoro e la carriera. "
        "Non riscrivere il quadro generale del mese né spiegare di nuovo i grandi "
        "transiti dei pianeti lenti: sono già in energia_generale. Se citi un evento "
        "condiviso, nominalo in poche parole e dedica la frase al suo effetto su questa area."
    ),
    "denaro": (
        "Ruolo: solo ciò che gli eventi significano per le risorse e il denaro. "
        "Non riscrivere il quadro generale del mese né spiegare di nuovo i grandi "
        "transiti dei pianeti lenti: sono già in energia_generale. Se citi un evento "
        "condiviso, nominalo in poche parole e dedica la frase al suo effetto su questa area."
    ),
    "benessere": (
        "Ruolo: solo ciò che gli eventi significano per la salute, l'energia e il "
        "benessere. Non riscrivere il quadro generale del mese né spiegare di nuovo i "
        "grandi transiti dei pianeti lenti: sono già in energia_generale. Se citi un "
        "evento condiviso, nominalo in poche parole e dedica la frase al suo effetto "
        "su questa area."
    ),
    "consiglio_finale": (
        "Ruolo: la chiusura pratica. NON nominare i transiti, i pianeti o le date già "
        "descritti nelle Sezioni scritte e non riassumerle: traduci il mese in due o "
        "quattro indicazioni concrete da mettere in pratica e chiudi con una sola "
        "immagine finale."
    ),
}


def _section_brief(section: str) -> str:
    return _SECTION_BRIEFS.get(section, "")


def _section_instruction(
    section: str,
    payload: dict[str, Any],
    written_sections: Mapping[str, tuple[Sentence, ...]] | None,
) -> str:
    lines = [f'{_SECTION_FRAMING}\n\nLa Sezione da scrivere è "{section}".']
    brief = _section_brief(section)
    if brief:
        lines.append(brief)
    if section in _DATE_TOKEN_SECTIONS:
        count = _day_list_count(payload, section)
        lines.append(
            f"Questa Sezione non deve MAI contenere una data (né un giorno del mese con "
            "un nome di mese, né una data in formato ISO): le date sono già proiettate a "
            f"monte dal codice. Contiene esattamente {count} eventi in "
            f"payload['day_lists']['{section}']: scrivi esattamente {count} frasi, una "
            'per ciascun evento, ognuna con un solo id in "entry_ids" (mai più di uno). '
            "Non accorpare più eventi sotto la stessa frase: ogni frase descrive un solo "
            "evento."
        )
    if section == "consiglio_finale" and written_sections:
        written = "\n".join(
            f"[{name}] {sentence.text}"
            for name in _SECTION_FIELD_NAMES
            if name != section
            for sentence in written_sections.get(name, ())
        )
        lines.append(
            "Le Sezioni precedenti, già scritte, sono qui sotto: il consiglio finale deve "
            "essere coerente con esse e non ripeterle. Questi testi non portano id; "
            "continua a citare solo id del Payload.\n"
            f"--- SEZIONI GIÀ SCRITTE ---\n{written}"
        )
    return "\n\n".join(lines)


def _build_section_prompt(
    section: str,
    payload: dict[str, Any],
    theme_previous: ReportTheme | None,
    theme_current: ReportTheme,
    aliases: dict[str, str],
    written_sections: Mapping[str, tuple[Sentence, ...]] | None,
) -> str:
    """Payload and continuity first (the same bytes for every Section of a
    Report), the Section-specific instruction last."""
    payload_json = _aliased_payload_json(payload, aliases)
    theme_diff = diff_themes(theme_previous, theme_current)
    continuity = _render_continuity(theme_previous, theme_current, theme_diff)
    continuity_block = f"\n\n{continuity}" if continuity else ""
    return (
        f"--- PAYLOAD (JSON) ---\n{payload_json}\n"
        f"{continuity_block}\n\n"
        f"{_section_instruction(section, payload, written_sections)}"
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
                f"Section {section!r}, sentence {index}: 'entry_ids' must be a list of strings.",
            )
        sentences.append(Sentence(text=text, entry_ids=tuple(entry_ids)))
    return tuple(sentences)
