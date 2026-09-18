"""``run_gate()``: check every Claim in a ``GeneratedDraft`` against its
Report Payload (Story 5.2, AD-1/AD-5/AD-6).

Pure (AD-1): no I/O, no model call, no clock -- an identical
``(draft, payload, vocabulary)`` triple always produces a byte-for-byte
identical ``GateResult.violations`` tuple. This is the line the epic's
"send a report without reading it first" promise rests on: every sentence
``core/gate/classify.py::is_claim()`` flags is checked here for citation
presence and factual agreement with the Payload entries it cites, before the
Report ever reaches an exportable state (Story 5.3).

Only what ``is_claim()`` structurally recognizes is checked -- no re-derived
astronomy, no aspect-name or degree checking (Never section, inherited from
Story 5.1). The two dated-list Sections (``giorni_favorevoli``/
``giorni_di_attenzione``) additionally get an unconditional date-token check,
regardless of citation or Claim status (AD-5): those dates are code-projected
upstream (Story 3.7) and the model may never write one itself. The pattern is
reimplemented locally rather than imported from
``shell/adapters/gemini/generator.py`` (AD-1: ``core/`` never imports
``shell/``); it is kept in lockstep with that module by hand.
"""

from __future__ import annotations

import re
from dataclasses import fields as dataclass_fields
from datetime import datetime
from typing import Any

from core.gate.classify import is_claim
from core.types.gate import GateResult, GateViolation, GateVocabulary
from core.types.generation import GeneratedDraft, Sentence

__all__ = ["TRANSLATABLE_VOCABULARY", "body_sign_label", "run_gate"]

#: The two Sections whose dates are code-projected upstream (Story 3.7) --
#: mirrors ``shell/adapters/gemini/generator.py``'s ``_DATE_TOKEN_SECTIONS``.
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

#: Mirrors ``shell/adapters/gemini/generator.py``'s own
#: ``_ITALIAN_MONTH_ABBREVIATIONS`` -- ``set`` deliberately omitted so
#: "set di dati" is not flagged; ``sett`` for settembre is kept.
_ITALIAN_MONTH_ABBREVIATIONS = (
    "gen",
    "feb",
    "mar",
    "apr",
    "mag",
    "giu",
    "lug",
    "ago",
    "sett",
    "ott",
    "nov",
    "dic",
)

#: Mirrors ``shell/adapters/gemini/generator.py``'s own ``_DATE_TOKEN_PATTERN``
#: byte-for-byte (AD-1 forbids importing it): an ISO date, a day-of-month
#: (optionally with a degree-sign ordinal) followed by an Italian month name or
#: common abbreviation, or a numeric ``DD/MM``/``DD.MM``/``DD-MM`` pair
#: (optionally with a ``/YY(YY)`` year). The numeric branch requires a 1-12
#: month and pairs a single-digit day with a zero-padded month, so clock times
#: ("15.30", "9.45") and decimals ("1.5") are not matched.
_DATE_TOKEN_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"  # ISO date, e.g. "2026-01-15"
    r"|\b\d{1,2}°?\s+(?:"
    + "|".join(_ITALIAN_MONTHS + _ITALIAN_MONTH_ABBREVIATIONS)
    + r")\b"  # "15 gennaio" / "1° gen" / "15 gen."
    r"|\b(?:\d{2}[/.\-](?:0?[1-9]|1[0-2])|\d[/.\-](?:0[1-9]|1[0-2]))(?:[/.\-]\d{2,4})?\b",
    # numeric "DD/MM" / "DD.MM" / "DD-MM" (+ optional "/YY(YY)"): "15.01",
    # "15.1", "15/01/2026" match; "15.30", "9.45", "1.5", "13/45" do not
    re.IGNORECASE,
)

#: Italian planet name -> English body name (Payload bodies are English, see
#: ``core/ephemeris/chart.py``'s ``_PLANET_BODIES``). Local to this story
#: (Design Notes): the vocabulary's ten planet words paired with the exact
#: ten English body names the Payload's transit events use.
_BODY_MAP: dict[str, str] = {
    "sole": "sun",
    "luna": "moon",
    "mercurio": "mercury",
    "venere": "venus",
    "marte": "mars",
    "giove": "jupiter",
    "saturno": "saturn",
    "urano": "uranus",
    "nettuno": "neptune",
    "plutone": "pluto",
}

#: Italian sign name -> English sign name (mirrors ``core/ephemeris/chart.py``'s
#: ``_ZODIAC_SIGNS``). No Payload transit-event field this story checks ever
#: carries a sign value (see the category table in Design Notes) -- kept
#: alongside ``_BODY_MAP`` anyway so a sign token translates the same way a
#: planet token does, and a Claim naming only a sign is checked (and, given
#: today's Payload shape, always found ungrounded) rather than silently
#: ignored.
_SIGN_MAP: dict[str, str] = {
    "ariete": "aries",
    "toro": "taurus",
    "gemelli": "gemini",
    "cancro": "cancer",
    "leone": "leo",
    "vergine": "virgo",
    "bilancia": "libra",
    "scorpione": "scorpio",
    "sagittario": "sagittarius",
    "capricorno": "capricorn",
    "acquario": "aquarius",
    "pesci": "pisces",
}

#: Italian casa ordinal -> house number 1-12. Local to this story (mirrors
#: ``_BODY_MAP``/``_SIGN_MAP``): ``GateVocabulary.casa_ordinals`` is an
#: unordered ``frozenset`` of the words alone, carrying no numeric value.
_CASA_ORDINAL_TO_HOUSE: dict[str, int] = {
    "prima": 1,
    "seconda": 2,
    "terza": 3,
    "quarta": 4,
    "quinta": 5,
    "sesta": 6,
    "settima": 7,
    "ottava": 8,
    "nona": 9,
    "decima": 10,
    "undicesima": 11,
    "dodicesima": 12,
}

#: English body canonical key -> Italian display label (Gate-failure panel,
#: Story 9.5 amendment) -- the exact reverse of ``_BODY_MAP``: capitalizing
#: the original Italian word this key came from, since a translated body
#: name is a proper noun in the rendered Italian sentence/card (Design
#: Notes: "afferma Saturno" already reads as a claim about a body, no
#: wrapping noun needed).
_PLANET_LABELS_IT: dict[str, str] = {
    english: italian.capitalize() for italian, english in _BODY_MAP.items()
}

#: English sign canonical key -> Italian display label -- the exact reverse
#: of ``_SIGN_MAP``, same capitalization rule as ``_PLANET_LABELS_IT``.
_SIGN_LABELS_IT: dict[str, str] = {
    english: italian.capitalize() for italian, english in _SIGN_MAP.items()
}

#: The four non-planet natal targets ``core/transits/aspects.py::_natal_targets()``
#: admits as a Payload Aspect's ``natal_point`` alongside the ten planets and
#: two nodes already on ``chart.planets`` (review-loop 2): the natal
#: Ascendant/Midheaven (separate ``NatalChart`` fields) and the two Lunar
#: Nodes. Kept as a distinct map from ``_PLANET_LABELS_IT``/``_SIGN_LABELS_IT``
#: rather than folded in, since these are neither in ``_BODY_MAP`` nor
#: ``_SIGN_MAP`` and have no Italian-vocabulary-word counterpart to reverse.
_ANGLE_NODE_LABELS_IT: dict[str, str] = {
    "ascendant": "Ascendente",
    "midheaven": "Mediocielo",
    "true_node": "Nodo Nord",
    "south_node": "Nodo Sud",
}

#: The two angles among ``_natal_targets()``'s fourteen fixed targets that
#: are themselves a house cusp, by astrological definition -- never data-
#: dependent, so a Claim naming the house of an Aspect whose
#: ``transiting_body``/``natal_point`` is one of these two grounds
#: unconditionally (sprint-change-proposal-2026-09-18). The Lunar Nodes
#: carry no fixed house of their own and are deliberately absent.
_ANGLE_NATAL_POINT_HOUSE: dict[str, int] = {
    "ascendant": 1,
    "midheaven": 10,
}

#: The Italian wrapping-noun phrase for a checkable category whose bare
#: value(s) are not self-descriptive on their own (a house number, a
#: day-of-month number) -- ``"body/sign"`` needs no entry here: a translated
#: planet/sign name already reads as a claim about that thing and gets no
#: wrapper (Design Notes); ``"retrograde"`` is handled by its own fixed
#: phrasing in ``_invented_detail``/``_contradicted_detail`` and never
#: reaches this map. ``.get(kind, kind)`` degrades to the raw kind token for
#: an unrecognized kind rather than raising (mirrors
#: ``violation_kind_label``'s own defensive-fallback convention).
_CATEGORY_LABELS_IT: dict[str, str] = {
    "house": "la casa",
    "date": "il giorno",
}

#: Which cited-entry ``"kind"`` supplies a fact for each checkable category,
#: and which field(s) of that kind carry it -- the Design Notes category
#: table, reimplemented as data these extraction functions read.
#:
#: ``"aspect"`` carries three: ``perfected_at`` (the exact date, ``None`` for
#: a never-perfected Aspect) alongside ``orb_entry_at``/``orb_exit_at`` (the
#: orb window's start/end) -- the Style Guide's own §4 explicitly invites
#: describing "la finestra in cui l'aspetto è operativo (fase applicante e
#: separante)", so a date drawn from either boundary is exactly as grounded
#: as the perfection date itself (sprint-change-proposal-2026-09-18: a real
#: generation cited an Aspect's ``orb_exit_at`` day and was flagged as
#: hallucinated when only ``perfected_at`` counted). The other three kinds
#: carry no orb window at all -- one date each, unchanged.
_DATE_FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "aspect": ("perfected_at", "orb_entry_at", "orb_exit_at"),
    "station": ("station_at",),
    "ingress": ("crossed_at",),
    "lunation": ("occurred_at",),
}

#: The Italian words this module can translate into a Payload-comparable
#: value, keyed by the ``GateVocabulary`` word-list field each one must stay
#: in lockstep with (epic-5-retro-item-41). Pure derived data -- a
#: comprehension over the three translation maps above, no I/O, ``run_gate()``
#: stays byte-for-byte deterministic -- exposed so ``shell/gate.py``'s loader
#: can cross-check the shipped vocabulary against it at startup and refuse to
#: start on a ``planets``/``signs``/``casa_ordinals`` word this module has no
#: translation for (which ``is_claim()`` would still flag as a Claim, leaving
#: that category checked as an empty asserted set and able to pass
#: ungrounded).
TRANSLATABLE_VOCABULARY: dict[str, frozenset[str]] = {
    "planets": frozenset(_BODY_MAP),
    "signs": frozenset(_SIGN_MAP),
    "casa_ordinals": frozenset(_CASA_ORDINAL_TO_HOUSE),
}


def body_sign_label(value: str) -> str:
    """The Italian display label for one Payload-internal English body/sign
    canonical key (``_BODY_MAP``/``_SIGN_MAP`` *values*, e.g. ``"saturn"``,
    ``"leo"``) or natal angle/node token (``_ANGLE_NODE_LABELS_IT``), checked
    in that order; ``value`` unchanged for anything else (defensive
    fallback, mirrors ``violation_kind_label``/``_CATEGORY_LABELS_IT.get``'s
    convention elsewhere in this module).

    The single place this translation lives (Design Notes) -- imported by
    ``shell/http/stage_view.py`` too, so the ``detail`` sentence and a
    cited-entry card's body-name fields never drift out of sync against two
    hand-duplicated tables.
    """
    for mapping in (_PLANET_LABELS_IT, _SIGN_LABELS_IT, _ANGLE_NODE_LABELS_IT):
        label = mapping.get(value)
        if label is not None:
            return label
    return value


def _values_phrase(kind: str, values: frozenset[Any]) -> str:
    """The Italian phrase naming one category's value set inside a
    ``detail`` sentence: a translated body/sign label needs no wrapping
    noun (self-descriptive once translated, Design Notes); a bare house/day
    number is not self-descriptive on its own and gets one via
    ``_CATEGORY_LABELS_IT``."""
    if kind == "body/sign":
        return ", ".join(sorted(body_sign_label(str(value)) for value in values))
    joined = ", ".join(sorted(str(value) for value in values))
    return f"{_CATEGORY_LABELS_IT.get(kind, kind)} {joined}"


def _contains_word(text: str, token: str) -> bool:
    """Whether ``token`` appears in ``text`` as a whole word -- mirrors
    ``core/gate/classify.py``'s own ``_contains_token()``."""
    return re.search(rf"\b{re.escape(token)}\b", text) is not None


def _index_entries(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every Payload entry, keyed by its own ``"id"`` -- a generic recursive
    walk (mirrors ``shell/adapters/gemini/generator.py``'s
    ``_collect_known_entry_ids``) rather than one hand-written per Section/
    day-list, since an entry id is global and content-derived (AD-4) and the
    same entry may legitimately recur under more than one Section's slice."""
    index: dict[str, dict[str, Any]] = {}

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            entry_id = value.get("id")
            kind = value.get("kind")
            if isinstance(entry_id, str) and isinstance(kind, str):
                index[entry_id] = value
            for item in value.values():
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(payload)
    return index


def _natal_house_by_planet(payload: dict[str, Any]) -> dict[str, int]:
    """Every planet's own natal house, read from the Payload's ``profile``
    sub-objects (``core/payload/assemble.py``'s per-Section natal snapshot)
    (sprint-change-proposal-2026-09-18). A planet's natal house never
    changes across Sections, so any one occurrence grounds a Claim
    regardless of which Section's ``profile`` it came from.

    Distinguished from a ``"house_N"``/``"ascendant"`` profile entry
    (describing what a house itself contains, keyed ``"number"``/
    ``"planets"``/``"ruler"``) by requiring both a string ``"name"`` and an
    integer ``"house"`` field on the same dict -- only a planet's own
    profile entry carries that exact shape."""
    houses: dict[str, int] = {}

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            name = value.get("name")
            house = value.get("house")
            if isinstance(name, str) and isinstance(house, int) and not isinstance(house, bool):
                houses[name.lower()] = house
            for item in value.values():
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(payload)
    return houses


def _natal_sign_by_point(payload: dict[str, Any]) -> dict[str, str]:
    """Every planet's own natal sign, plus the Ascendant's (the only angle
    the Payload's ``profile`` sub-objects record a sign for), read the same
    way ``_natal_house_by_planet()`` reads houses (sprint-change-proposal-
    2026-09-18). A pre-computed field the Payload already carries, not
    astronomy re-derived from a raw degree -- ``_body_sign_facts()``'s own
    Lunation docstring draws exactly this line, forbidding the latter, not
    the former.

    The Ascendant's own profile entry carries no ``"name"`` field (it is
    keyed literally ``"ascendant"``, unlike a planet's own profile entry),
    so it needs the dict key itself to identify, not the shape alone."""
    signs: dict[str, str] = {}

    def _walk(value: Any, key: str | None) -> None:
        if isinstance(value, dict):
            sign = value.get("sign")
            if isinstance(sign, str):
                name = value.get("name")
                house = value.get("house")
                if isinstance(name, str) and isinstance(house, int) and not isinstance(house, bool):
                    signs[name.lower()] = sign.lower()
                elif key == "ascendant":
                    signs["ascendant"] = sign.lower()
            for child_key, child_value in value.items():
                _walk(child_value, child_key)
        elif isinstance(value, list):
            for item in value:
                _walk(item, key)

    _walk(payload, None)
    return signs


def _cited_entries(
    sentence: Sentence, entry_index: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [entry_index[entry_id] for entry_id in sentence.entry_ids if entry_id in entry_index]


# --- Per-category: what the sentence's text asserts --------------------------


def _asserted_bodies_signs(lowered_text: str, vocabulary: GateVocabulary) -> frozenset[str]:
    asserted: set[str] = set()
    for word in vocabulary.planets:
        english = _BODY_MAP.get(word)
        if english is not None and _contains_word(lowered_text, word):
            asserted.add(english)
    for word in vocabulary.signs:
        english = _SIGN_MAP.get(word)
        if english is not None and _contains_word(lowered_text, word):
            asserted.add(english)
    return frozenset(asserted)


def _asserted_houses(lowered_text: str, vocabulary: GateVocabulary) -> frozenset[int]:
    if not _contains_word(lowered_text, "casa"):
        return frozenset()
    asserted: set[int] = set()
    for word in vocabulary.casa_ordinals:
        house = _CASA_ORDINAL_TO_HOUSE.get(word)
        if house is not None and _contains_word(lowered_text, word):
            asserted.add(house)
    return frozenset(asserted)


def _asserted_days_of_month(lowered_text: str, vocabulary: GateVocabulary) -> frozenset[int]:
    matches = re.findall(vocabulary.day_of_month_pattern, lowered_text)
    return frozenset(int(match) for match in matches)


def _asserted_retrograde(lowered_text: str, vocabulary: GateVocabulary) -> bool:
    return _contains_word(lowered_text, vocabulary.retrogrado) or _contains_word(
        lowered_text, vocabulary.stazionario
    )


# --- Per-category: what the cited entries expose ------------------------------


def _body_sign_facts(
    entries: list[dict[str, Any]], natal_sign_by_point: dict[str, str]
) -> frozenset[str]:
    """Story 5.2 amendment: a ``lunation`` entry always asserts ``"moon"``.
    A Lunation *is* the Moon (Delta-lambda between Moon and Sun crossing 0/180
    degrees, ``core/types/transits.py::Lunation``) -- its dataclass carries no
    ``body`` field precisely because that fact never varies, not because the
    body is unknown or unchecked. The original category table (Design Notes,
    ``spec-5-2``) omitted ``lunation`` here, which meant every correctly
    written "Luna Nuova"/"Luna Piena" sentence failed as ``invented_fact``
    for the word "luna" -- a false positive on every single month's Report,
    since a Lunation happens monthly and Italian has no natural way to name
    one without the word. No *transiting* sign fact is added for a Lunation
    itself: its ``longitude`` would let one be derived, but that is
    re-deriving astronomy from a raw degree, which this module's Never
    section forbids (AD-1) -- a Claim naming the Lunation's own current sign
    still correctly fails.

    (sprint-change-proposal-2026-09-18): every body/point gathered above
    also grounds its own *natal* sign, when the Payload's ``profile`` data
    records one -- a different, pre-computed fact ("Luna natale in Toro" is
    not "this month's Luna Piena is in Toro"), not the re-derivation the
    paragraph above forbids.
    """
    facts: set[str] = set()
    for entry in entries:
        kind = entry.get("kind")
        if kind == "aspect":
            for field in ("transiting_body", "natal_point"):
                value = entry.get(field)
                if isinstance(value, str):
                    facts.add(value.lower())
        elif kind in ("station", "standing_retrograde", "ingress"):
            value = entry.get("body")
            if isinstance(value, str):
                facts.add(value.lower())
        elif kind == "lunation":
            facts.add("moon")

    for point in frozenset(facts):
        sign = natal_sign_by_point.get(point)
        if sign is not None:
            facts.add(sign)
    return frozenset(facts)


def _house_facts(
    entries: list[dict[str, Any]],
    natal_house_by_planet: dict[str, int],
    natal_sign_by_point: dict[str, str],
) -> frozenset[int]:
    """(sprint-change-proposal-2026-09-18): alongside an Ingress's own
    ``house_departed``/``house_entered`` and a Lunation's ``natal_house``,
    every body/point a cited entry asserts (``_body_sign_facts``'s own
    extraction, reused rather than re-derived here) grounds one more house:
    a fixed angle (Ascendente/Medio Cielo) via ``_ANGLE_NATAL_POINT_HOUSE``,
    or a planet's own natal house via ``natal_house_by_planet``. A real
    generation hit exactly this: "la tua Venere natale si trova nella
    seconda casa", citing only an Aspect -- true, and present in the
    Payload's ``profile`` data, but previously ungroundable since no cited
    entry kind carried a house field of its own for it."""
    facts: set[int] = set()
    for entry in entries:
        kind = entry.get("kind")
        if kind == "ingress":
            for field in ("house_departed", "house_entered"):
                value = entry.get(field)
                if isinstance(value, int) and not isinstance(value, bool):
                    facts.add(value)
        elif kind == "lunation":
            value = entry.get("natal_house")
            if isinstance(value, int) and not isinstance(value, bool):
                facts.add(value)

    for body in _body_sign_facts(entries, natal_sign_by_point):
        angle_house = _ANGLE_NATAL_POINT_HOUSE.get(body)
        if angle_house is not None:
            facts.add(angle_house)
        natal_house = natal_house_by_planet.get(body)
        if natal_house is not None:
            facts.add(natal_house)
    return frozenset(facts)


def _date_facts(entries: list[dict[str, Any]]) -> frozenset[int]:
    facts: set[int] = set()
    for entry in entries:
        fields = _DATE_FIELDS_BY_KIND.get(entry.get("kind"), ())
        for field in fields:
            value = entry.get(field)
            if not isinstance(value, str):
                # Covers both a missing field and a ``None`` value (an
                # aspect's ``perfected_at`` when ``never_perfected`` is true,
                # or its ``orb_exit_at`` when the window is still open at
                # month end) -- neither contributes a day fact.
                continue
            try:
                facts.add(datetime.fromisoformat(value).day)
            except ValueError:
                # A malformed date field in a cited Payload entry contributes
                # no day fact rather than crashing the whole Gate run.
                continue
    return frozenset(facts)


def _retrograde_facts(entries: list[dict[str, Any]]) -> frozenset[bool]:
    facts: set[bool] = set()
    for entry in entries:
        kind = entry.get("kind")
        if kind == "station":
            facts.add(entry.get("direction") == "retrograde")
        elif kind == "standing_retrograde":
            facts.add(True)
    return frozenset(facts)


def _invented_detail(kind: str, asserted: frozenset[Any]) -> str:
    """``GateViolation.detail`` for ``"invented_fact"`` -- Italian prose,
    worded, not a raw Python repr (Story 5.5 surfaces this directly to
    Francesco). Retrograde is boolean-valued internally but is always
    worded "the body is retrograde", never a ``True``/``False`` repr
    (code-review finding #3)."""
    if kind == "retrograde":
        return "afferma che il corpo è retrogrado, ma nessuna delle voci citate lo conferma."
    return f"afferma {_values_phrase(kind, asserted)}, ma nessuna delle voci citate lo conferma."


def _contradicted_detail(kind: str, unmatched: frozenset[Any], gathered: frozenset[Any]) -> str:
    """``GateViolation.detail`` for ``"contradicted_fact"`` -- Italian
    prose, naming only the unmatched claimed value(s), not the Claim's full
    asserted set (see ``_category_violation``'s docstring). Retrograde
    worded the same way ``_invented_detail`` is."""
    if kind == "retrograde":
        cited = ", ".join(sorted("retrogrado" if value else "diretto" for value in gathered))
        return f"afferma che il corpo è retrogrado, ma le voci citate indicano: {cited}."
    unmatched_phrase = _values_phrase(kind, unmatched)
    gathered_phrase = _values_phrase(kind, gathered)
    return f"afferma {unmatched_phrase}, ma le voci citate confermano {gathered_phrase}."


def _category_violation(
    *,
    kind: str,
    section: str,
    sentence: Sentence,
    sentence_index: int,
    gathered: frozenset[Any],
    asserted: frozenset[Any],
) -> GateViolation | None:
    """The shared invented/contradicted-fact rule (Design Notes): a category
    a Claim asserts is ``"invented_fact"`` when zero of its cited entries
    assert *any* fact in that category, or ``"contradicted_fact"`` when at
    least one asserted value has no matching cited-entry value.

    ``contradicted_fact`` is computed from ``unmatched = asserted - gathered``,
    not from ``asserted.isdisjoint(gathered)`` -- a Claim naming two values in
    one category in a single sentence (e.g. two houses) where only one of
    them is grounded must still fail on the other, not pass because *some*
    asserted value happened to match (code-review finding #1)."""
    if not gathered:
        return GateViolation(
            kind="invented_fact",
            section=section,
            sentence=sentence.text,
            entry_ids=sentence.entry_ids,
            detail=_invented_detail(kind, asserted),
            sentence_index=sentence_index,
        )
    unmatched = asserted - gathered
    if unmatched:
        return GateViolation(
            kind="contradicted_fact",
            section=section,
            sentence=sentence.text,
            entry_ids=sentence.entry_ids,
            detail=_contradicted_detail(kind, unmatched, gathered),
            sentence_index=sentence_index,
        )
    return None


def _check_claim(
    *,
    section: str,
    sentence: Sentence,
    sentence_index: int,
    entry_index: dict[str, dict[str, Any]],
    natal_house_by_planet: dict[str, int],
    natal_sign_by_point: dict[str, str],
    vocabulary: GateVocabulary,
) -> list[GateViolation]:
    if not sentence.entry_ids:
        return [
            GateViolation(
                kind="empty_citation",
                section=section,
                sentence=sentence.text,
                entry_ids=sentence.entry_ids,
                detail="la frase contiene un termine del vocabolario chiuso (è una Claim) "
                "ma non cita alcuna voce del Payload.",
                sentence_index=sentence_index,
            )
        ]

    lowered = sentence.text.lower()
    entries = _cited_entries(sentence, entry_index)
    violations: list[GateViolation] = []

    asserted_bodies_signs = _asserted_bodies_signs(lowered, vocabulary)
    if asserted_bodies_signs:
        violation = _category_violation(
            kind="body/sign",
            section=section,
            sentence=sentence,
            sentence_index=sentence_index,
            gathered=_body_sign_facts(entries, natal_sign_by_point),
            asserted=asserted_bodies_signs,
        )
        if violation is not None:
            violations.append(violation)

    asserted_houses = _asserted_houses(lowered, vocabulary)
    if asserted_houses:
        violation = _category_violation(
            kind="house",
            section=section,
            sentence=sentence,
            sentence_index=sentence_index,
            gathered=_house_facts(entries, natal_house_by_planet, natal_sign_by_point),
            asserted=asserted_houses,
        )
        if violation is not None:
            violations.append(violation)

    asserted_days = _asserted_days_of_month(lowered, vocabulary)
    if asserted_days:
        violation = _category_violation(
            kind="date",
            section=section,
            sentence=sentence,
            sentence_index=sentence_index,
            gathered=_date_facts(entries),
            asserted=asserted_days,
        )
        if violation is not None:
            violations.append(violation)

    if _asserted_retrograde(lowered, vocabulary):
        violation = _category_violation(
            kind="retrograde",
            section=section,
            sentence=sentence,
            sentence_index=sentence_index,
            gathered=_retrograde_facts(entries),
            asserted=frozenset({True}),
        )
        if violation is not None:
            violations.append(violation)

    return violations


def _check_date_token(
    section: str, sentence: Sentence, sentence_index: int
) -> GateViolation | None:
    if section not in _DATE_TOKEN_SECTIONS:
        return None
    if _DATE_TOKEN_PATTERN.search(sentence.text) is None:
        return None
    return GateViolation(
        kind="date_token_in_day_list",
        section=section,
        sentence=sentence.text,
        entry_ids=sentence.entry_ids,
        detail=(
            f"la frase contiene un token con forma di data; le date nella Sezione "
            f"{section!r} sono generate a monte dal codice e non devono mai essere "
            "scritte dal modello."
        ),
        sentence_index=sentence_index,
    )


def run_gate(
    draft: GeneratedDraft, payload: dict[str, Any], vocabulary: GateVocabulary
) -> GateResult:
    """Check every Claim in ``draft`` against ``payload``, plus the
    unconditional Section 6/7 date-token check (AD-5).

    Pure and deterministic (AD-1): no I/O, no model call; identical
    ``(draft, payload, vocabulary)`` always produces a byte-for-byte
    identical ``GateResult.violations`` tuple, in a fixed order (Section
    field order, then sentence index, then: empty citation, body/sign,
    house, date, retrograde, date-token-in-day-list).
    """
    entry_index = _index_entries(payload)
    natal_house_by_planet = _natal_house_by_planet(payload)
    natal_sign_by_point = _natal_sign_by_point(payload)
    violations: list[GateViolation] = []

    for section_field in dataclass_fields(draft):
        section = section_field.name
        sentences: tuple[Sentence, ...] = getattr(draft, section)
        for sentence_index, sentence in enumerate(sentences):
            if is_claim(sentence.text, vocabulary):
                violations.extend(
                    _check_claim(
                        section=section,
                        sentence=sentence,
                        sentence_index=sentence_index,
                        entry_index=entry_index,
                        natal_house_by_planet=natal_house_by_planet,
                        natal_sign_by_point=natal_sign_by_point,
                        vocabulary=vocabulary,
                    )
                )
            date_token_violation = _check_date_token(section, sentence, sentence_index)
            if date_token_violation is not None:
                violations.append(date_token_violation)

    return GateResult(
        passed=not violations,
        vocabulary_version=vocabulary.version,
        vocabulary_content_hash=vocabulary.content_hash,
        violations=tuple(violations),
    )
