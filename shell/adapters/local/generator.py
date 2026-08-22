"""``RecordedResponseGenerator``: the local-only ``Generator`` port adapter
(Story 4.9) that lets the application run under ``compose.yaml`` without
spending real Gemini quota.

Never a network call, a model call or a filesystem read: it builds every
Section's cited sentences directly from the entry ids already present in the
``payload`` it is given. This is deliberately not a fixed recorded fixture --
a literal recorded Gemini response (a JSON file checked into the repo) would
only be citation-valid against the one Payload it was captured from, since
entry ids are content-derived (AD-4). Deriving sentences from whatever ids
the given ``payload`` actually contains keeps this adapter valid for any
Client/month, in both real local dev and tests.

Holds no state and no injectable client (unlike ``GeminiGenerator``'s
``client`` parameter): there is nothing to fake because there is no network
call to make.
"""

from __future__ import annotations

from typing import Any

from core.types.generation import GeneratedDraft, Sentence
from core.types.memory import ReportTheme
from shell.adapters.gemini.generator import (
    _DATE_TOKEN_SECTIONS,
    _SECTION_FIELD_NAMES,
    _collect_known_entry_ids,
    _validate_citations,
    _validate_no_date_tokens,
)
from shell.ports.generator import StyleGuideVersion

__all__ = ["RecordedResponseGenerator"]

#: A single generic Italian placeholder sentence, reused for every Section --
#: deliberately free of any date-shaped token, so it never trips
#: ``_validate_no_date_tokens`` when it lands in ``giorni_favorevoli``/
#: ``giorni_di_attenzione``.
_PLACEHOLDER_TEXT = (
    "Contenuto segnaposto generato localmente da RecordedResponseGenerator, "
    "senza alcuna chiamata al provider."
)


def _section_subtree(payload: dict[str, Any], name: str) -> Any:
    """The slice of ``payload`` one Section field's placeholder sentence
    cites from -- a day-list (a list of entries) for the two Sections whose
    dates are code-projected upstream, or that Section's own sub-tree of
    ``payload["sections"]`` otherwise. Missing/empty either way is not an
    error (Matrix: "A Section/day-list with zero entries") -- ``.get()``
    with an empty default reads as "no ids here", exactly like a Section
    with no matching events."""
    if name in _DATE_TOKEN_SECTIONS:
        return payload.get("day_lists", {}).get(name, [])
    return payload.get("sections", {}).get(name, {})


class RecordedResponseGenerator:
    """The ``Generator`` port implementation the local environment runs
    against (Story 4.9). ``style_guide``/``theme_previous``/``theme_current``
    are accepted -- the port is fixed and exclusive (AD-3) -- but never read:
    every sentence is derived purely from ``payload``'s own entry ids."""

    def generate(
        self,
        payload: dict,
        style_guide: StyleGuideVersion,
        theme_previous: ReportTheme | None,
        theme_current: ReportTheme,
    ) -> GeneratedDraft:
        fields: dict[str, tuple[Sentence, ...]] = {}
        for name in _SECTION_FIELD_NAMES:
            subtree = _section_subtree(payload, name)
            entry_ids = tuple(sorted(_collect_known_entry_ids(subtree)))
            fields[name] = (Sentence(text=_PLACEHOLDER_TEXT, entry_ids=entry_ids),)

        draft = GeneratedDraft(**fields)
        _validate_citations(draft, payload)
        _validate_no_date_tokens(draft)
        return draft
