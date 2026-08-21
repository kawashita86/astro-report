"""Render a persisted ``GeneratedDraft`` into prose Francesco could read
aloud on a call (Story 4.6, AD-6).

The one and only place a ``GeneratedDraft``'s cited sentences are turned into
continuous prose or a dated list -- ``shell/runner/driver.py``'s
``draft_ready`` stage persists the raw, cited structure verbatim
(``shell/adapters/postgres/report_draft.py``); rendering happens here, at
view time, in ``shell/http/`` (mirrors ``shell/http/payload_view.py``'s own
AD-12 shape: "local-time conversion happens only in ``shell/http/``," never
baked into storage, for the same reason -- a stored citation must mean the
same thing years later regardless of how it is displayed today).

Citations are never discarded here, only reshaped for reading: every
returned Section still carries the ``entry_ids`` its prose or its list items
rest on.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any

from core.types.generation import GeneratedDraft, Sentence
from shell.http.payload_view import localize_payload

__all__ = [
    "LIST_SECTION_NAMES",
    "PROSE_SECTION_NAMES",
    "SECTION_ORDER",
    "deserialize_generated_draft",
    "render_draft",
]

#: Sections 1-5 and 8, in ``GeneratedDraft``'s own fixed order (AD-6) --
#: render as one continuous string each, never bullet fragments.
PROSE_SECTION_NAMES: tuple[str, ...] = (
    "energia_generale",
    "amore",
    "lavoro",
    "denaro",
    "benessere",
    "consiglio_finale",
)

#: Sections 6-7: the code-projected dated day lists (Story 3.7) -- rendered
#: as one item per ``payload["day_lists"]`` entry, in list form, never gated
#: by whether a Sentence cites it (this story's Design Notes).
LIST_SECTION_NAMES: tuple[str, ...] = ("giorni_favorevoli", "giorni_di_attenzione")

#: All eight ``GeneratedDraft`` field names, in the model's own fixed order
#: (AD-6) -- introspected rather than hand-listed, mirrors
#: ``shell/adapters/gemini/generator.py``'s own ``_SECTION_FIELD_NAMES``, so a
#: future ``GeneratedDraft`` field is picked up automatically here too. Public
#: so a template/route can render Sections 1-8 in this true order rather than
#: grouping all prose Sections before all list Sections (which would put
#: Section 8, ``consiglio_finale``, ahead of Sections 6-7 -- wrong for prose
#: meant to be read aloud as a script, in order).
SECTION_ORDER: tuple[str, ...] = tuple(field.name for field in dataclass_fields(GeneratedDraft))

#: The date field that names "the day" for one day-list entry, keyed by the
#: entry's own ``"kind"`` tag (``core/payload/freeze.py``'s ``_tag_event``,
#: reused verbatim by ``shell/runner/driver.py``'s own event tagging): an
#: Aspect Perfection's ``perfected_at`` (the only kind ``project_day_lists()``
#: admits with a non-``None`` one), a Lunation's ``occurred_at``, a
#: Station's ``station_at``.
_DATE_FIELD_BY_KIND: dict[str, str] = {
    "aspect": "perfected_at",
    "lunation": "occurred_at",
    "station": "station_at",
}


def deserialize_generated_draft(stored: dict[str, Any]) -> GeneratedDraft:
    """The reverse of ``shell/adapters/postgres/report_draft.py``'s own
    ``_json_safe`` encoding: ``ReportDraft.draft`` (JSON, verbatim) back into
    a real ``GeneratedDraft`` -- read back, never recomputed, mirroring
    ``shell/runner/driver.py``'s own "read back" pattern for every other
    stage's stored output.
    """
    return GeneratedDraft(
        **{
            name: tuple(
                Sentence(text=sentence["text"], entry_ids=tuple(sentence["entry_ids"]))
                for sentence in stored[name]
            )
            for name in SECTION_ORDER
        }
    )


def _entry_ids(sentences: tuple[Sentence, ...]) -> tuple[str, ...]:
    return tuple(entry_id for sentence in sentences for entry_id in sentence.entry_ids)


def _render_prose(sentences: tuple[Sentence, ...]) -> dict[str, Any]:
    """One continuous string, ``sentences`` joined in the model's own order
    -- no bullets -- alongside every ``entry_id`` the Section's sentences
    rest on, so a citation is reshaped for reading, never discarded."""
    return {
        "text": " ".join(sentence.text for sentence in sentences),
        "entry_ids": _entry_ids(sentences),
    }


def _entry_date(entry: dict[str, Any]) -> str:
    field = _DATE_FIELD_BY_KIND.get(entry.get("kind"))
    if field is None:
        raise ValueError(f"day-list entry has an unrecognized or missing 'kind': {entry!r}")
    return entry[field]


def _citing_text(entry_id: str, sentences: tuple[Sentence, ...]) -> str | None:
    """The joined text of every Sentence citing ``entry_id`` -- ``None`` if no
    Sentence cites it (an uncited entry still renders, date only, per this
    story's I/O & Edge-Case Matrix)."""
    texts = [sentence.text for sentence in sentences if entry_id in sentence.entry_ids]
    return " ".join(texts) if texts else None


def _render_list(
    list_name: str,
    sentences: tuple[Sentence, ...],
    payload: dict[str, Any],
    *,
    iana_zone: str,
) -> list[dict[str, Any]]:
    """One item per ``payload["day_lists"][list_name]`` entry -- the
    code-projected, authoritative source (Story 3.7) -- enriched with any
    citing Sentence's text and localized to ``iana_zone``. A Sentence's
    ``entry_ids`` only enrich an entry, never gate whether it appears (this
    story's Design Notes): every entry is emitted, cited or not.
    """
    entries = payload["day_lists"][list_name]
    localized_entries = localize_payload({"entries": entries}, iana_zone=iana_zone)["entries"]
    return [
        {
            "date": _entry_date(entry),
            "text": _citing_text(entry["id"], sentences),
            "entry_ids": (entry["id"],),
        }
        for entry in localized_entries
    ]


def render_draft(
    draft: GeneratedDraft, payload: dict[str, Any], *, iana_zone: str
) -> dict[str, Any]:
    """``draft``'s eight Sections rendered for a reader: keyed by Section
    name, ``PROSE_SECTION_NAMES`` (Sections 1-5, 8) each mapping to
    ``{"text": ..., "entry_ids": (...)}`` and ``LIST_SECTION_NAMES``
    (Sections 6-7) each mapping to a list of
    ``{"date": ..., "text": ..., "entry_ids": (...)}`` items, one per
    ``payload["day_lists"]`` entry.

    Never mutates ``draft`` or ``payload`` -- ``entry_ids`` are carried
    forward into the rendered structure, never discarded (this story's
    Acceptance Criteria): rendering reshapes the persisted, cited draft for
    reading, it does not strip what it rests on.
    """
    rendered: dict[str, Any] = {}
    for name in PROSE_SECTION_NAMES:
        rendered[name] = _render_prose(getattr(draft, name))
    for name in LIST_SECTION_NAMES:
        rendered[name] = _render_list(name, getattr(draft, name), payload, iana_zone=iana_zone)
    return rendered
