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

__all__ = ["run_gate"]

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

#: Mirrors ``shell/adapters/gemini/generator.py``'s own ``_DATE_TOKEN_PATTERN``
#: byte-for-byte (AD-1 forbids importing it): an ISO date, a day-of-month
#: (optionally with a degree-sign ordinal) followed by an Italian month name,
#: or a numeric ``DD/MM``/``DD-MM`` pair.
_DATE_TOKEN_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"  # ISO date, e.g. "2026-01-15"
    r"|\b\d{1,2}°?\s+(?:" + "|".join(_ITALIAN_MONTHS) + r")\b"  # "15 gennaio" / "1° gennaio"
    r"|\b\d{1,2}[/-]\d{1,2}\b",  # "15/01" / "15-01"
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

#: Which cited-entry ``"kind"`` supplies a fact for each checkable category,
#: and which field(s) of that kind carry it -- the Design Notes category
#: table, reimplemented as data these extraction functions read.
_DATE_FIELD_BY_KIND: dict[str, str] = {
    "aspect": "perfected_at",
    "station": "station_at",
    "ingress": "crossed_at",
    "lunation": "occurred_at",
}


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


def _body_sign_facts(entries: list[dict[str, Any]]) -> frozenset[str]:
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
    return frozenset(facts)


def _house_facts(entries: list[dict[str, Any]]) -> frozenset[int]:
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
    return frozenset(facts)


def _date_facts(entries: list[dict[str, Any]]) -> frozenset[int]:
    facts: set[int] = set()
    for entry in entries:
        field = _DATE_FIELD_BY_KIND.get(entry.get("kind"))
        if field is None:
            continue
        value = entry.get(field)
        if isinstance(value, str):
            facts.add(datetime.fromisoformat(value).day)
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
    """``GateViolation.detail`` for ``"invented_fact"`` -- worded, not a raw
    Python repr (Story 5.5 surfaces this directly to Francesco). Retrograde
    is boolean-valued internally but is always worded "the body is
    retrograde", never a ``True``/``False`` repr (code-review finding #3)."""
    if kind == "retrograde":
        return (
            "claims the body is retrograde, but none of the cited entries assert a "
            "retrograde/direct fact."
        )
    values = ", ".join(sorted(str(item) for item in asserted))
    return f"claims {kind} {values}, but none of the cited entries assert a {kind} fact."


def _contradicted_detail(kind: str, unmatched: frozenset[Any], gathered: frozenset[Any]) -> str:
    """``GateViolation.detail`` for ``"contradicted_fact"`` -- names only the
    unmatched claimed value(s), not the Claim's full asserted set (see
    ``_category_violation``'s docstring). Retrograde worded the same way
    ``_invented_detail`` is."""
    if kind == "retrograde":
        cited = ", ".join(sorted("retrograde" if value else "not retrograde" for value in gathered))
        return f"claims the body is retrograde, but the cited entries indicate: {cited}."
    unmatched_values = ", ".join(sorted(str(item) for item in unmatched))
    gathered_values = ", ".join(sorted(str(item) for item in gathered))
    return f"claims {kind} {unmatched_values}, but the cited entries assert {gathered_values}."


def _category_violation(
    *,
    kind: str,
    section: str,
    sentence: Sentence,
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
        )
    unmatched = asserted - gathered
    if unmatched:
        return GateViolation(
            kind="contradicted_fact",
            section=section,
            sentence=sentence.text,
            entry_ids=sentence.entry_ids,
            detail=_contradicted_detail(kind, unmatched, gathered),
        )
    return None


def _check_claim(
    *,
    section: str,
    sentence: Sentence,
    entry_index: dict[str, dict[str, Any]],
    vocabulary: GateVocabulary,
) -> list[GateViolation]:
    if not sentence.entry_ids:
        return [
            GateViolation(
                kind="empty_citation",
                section=section,
                sentence=sentence.text,
                entry_ids=sentence.entry_ids,
                detail="sentence is a Claim (contains a closed-vocabulary token) but cites no "
                "Payload entry.",
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
            gathered=_body_sign_facts(entries),
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
            gathered=_house_facts(entries),
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
            gathered=_retrograde_facts(entries),
            asserted=frozenset({True}),
        )
        if violation is not None:
            violations.append(violation)

    return violations


def _check_date_token(section: str, sentence: Sentence) -> GateViolation | None:
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
            f"sentence contains a date-shaped token; dates in Section {section!r} are "
            "code-projected upstream and must never be written by the model."
        ),
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
    violations: list[GateViolation] = []

    for section_field in dataclass_fields(draft):
        section = section_field.name
        sentences: tuple[Sentence, ...] = getattr(draft, section)
        for sentence in sentences:
            if is_claim(sentence.text, vocabulary):
                violations.extend(
                    _check_claim(
                        section=section,
                        sentence=sentence,
                        entry_index=entry_index,
                        vocabulary=vocabulary,
                    )
                )
            date_token_violation = _check_date_token(section, sentence)
            if date_token_violation is not None:
                violations.append(date_token_violation)

    return GateResult(
        passed=not violations,
        vocabulary_version=vocabulary.version,
        violations=tuple(violations),
    )
