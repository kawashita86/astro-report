"""Provider-neutral draft validation shared by both ``Generator`` adapters
(epic-4-retro-item-24).

``shell/adapters/gemini/generator.py`` originally owned the citation check,
the date-token check, and the constants they need. ``RecordedResponseGenerator``
(``shell/adapters/local/generator.py``) reached into that module's namespace
for them -- and importing it executes ``from google import genai``, so the
local-only, network-free adapter transitively pulled in the Gemini SDK. These
pieces depend on nothing provider-specific (only ``core.*`` and stdlib), so
they live here now; ``gemini/generator.py`` and ``local/generator.py`` both
import them from this module, and the import chain into ``google`` is cut for
the local adapter.

Imports from ``core.*`` and stdlib only -- never ``google``, never
``shell.adapters.gemini``, never ``sqlalchemy``/``sqlmodel``.
"""

from __future__ import annotations

import re
from dataclasses import fields as dataclass_fields
from typing import Any

from core.errors import GenerationError
from core.types.generation import GeneratedDraft

__all__ = [
    "_DATE_TOKEN_PATTERN",
    "_DATE_TOKEN_SECTIONS",
    "_SECTION_FIELD_NAMES",
    "_collect_known_entry_ids",
    "_validate_citations",
    "_validate_no_date_tokens",
]

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

#: Common abbreviated forms of the twelve months. Terminated by ``\b`` in the
#: pattern, so ``3 mar`` matches but ``3 mare`` (sea) does not. ``set`` is
#: deliberately omitted -- "set di dati" is too common a phrase to flag -- while
#: ``sett`` for settembre is kept.
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

#: Best-effort regex heuristic (Design Notes), not a completeness guarantee:
#: an ISO date, a day-of-month (optionally with a degree-sign ordinal, e.g.
#: "1°") followed by an Italian month name or common abbreviation, or a numeric
#: ``DD/MM``/``DD.MM``/``DD-MM`` pair (optionally with a ``/YY(YY)`` year). The
#: numeric branch requires the month field to be 1-12, and a single-digit day
#: to be paired with a zero-padded month, so Italian clock times ("15.30",
#: "9.45") and decimals ("1.5") are not mistaken for dates. Deliberately does
#: not attempt spelled-out ordinals ("il primo gennaio") -- out of scope for a
#: regex.
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
