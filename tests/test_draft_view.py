"""``shell/http/draft_view.py::render_draft()`` (Story 4.6, AD-6) -- this
story's own I/O & Edge-Case Matrix rows: prose Sections join into one
continuous string, list Sections iterate ``payload["day_lists"]`` entries
first (enriched by any citing Sentence), and an uncited day-list entry still
renders, date only, never dropped.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.types.generation import GeneratedDraft, Sentence
from shell.adapters.postgres.report_draft import _json_safe as _draft_json_safe
from shell.http.draft_view import (
    LIST_SECTION_NAMES,
    PROSE_SECTION_NAMES,
    SECTION_ORDER,
    SECTION_TITLES,
    deserialize_generated_draft,
    render_draft,
)

_IANA_ZONE = "America/Chicago"  # UTC-6 in January (CST, no DST).


def _a_payload() -> dict[str, Any]:
    return {
        "day_lists": {
            "giorni_favorevoli": [
                {
                    "id": "fav-1",
                    "kind": "aspect",
                    "transiting_body": "venus",
                    "natal_point": "sun",
                    "aspect": "trine",
                    "perfected_at": "2026-01-10T15:00:00+00:00",
                    "never_perfected": False,
                    "orb_entry_at": "2026-01-08T12:00:00+00:00",
                    "orb_exit_at": "2026-01-12T12:00:00+00:00",
                },
                {
                    "id": "fav-2",
                    "kind": "lunation",
                    "lunation_kind": "new_moon",
                    "occurred_at": "2026-01-18T09:00:00+00:00",
                    "longitude": "15.0",
                    "natal_house": 3,
                },
            ],
            "giorni_di_attenzione": [
                {
                    "id": "att-1",
                    "kind": "station",
                    "body": "mars",
                    "direction": "retrograde",
                    "station_at": "2026-01-15T09:00:00+00:00",
                    "longitude": "10.0",
                },
            ],
        }
    }


def _a_draft() -> GeneratedDraft:
    return GeneratedDraft(
        energia_generale=(
            Sentence(text="Il mese si apre con energia.", entry_ids=("x1",)),
            Sentence(text="Prosegue con calma.", entry_ids=("x2", "x3")),
        ),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(Sentence(text="Venere favorisce gli incontri.", entry_ids=("fav-1",)),),
        giorni_di_attenzione=(),
        consiglio_finale=(Sentence(text="Respira.", entry_ids=()),),
    )


# --- Prose Sections ----------------------------------------------------------------


def test_prose_sections_join_into_one_continuous_string_no_bullets() -> None:
    rendered = render_draft(_a_draft(), _a_payload(), iana_zone=_IANA_ZONE)

    assert rendered["energia_generale"]["text"] == (
        "Il mese si apre con energia. Prosegue con calma."
    )
    assert isinstance(rendered["energia_generale"]["text"], str)
    assert "\n" not in rendered["energia_generale"]["text"]


def test_prose_sections_keep_their_entry_ids_in_the_returned_structure() -> None:
    rendered = render_draft(_a_draft(), _a_payload(), iana_zone=_IANA_ZONE)

    assert rendered["energia_generale"]["entry_ids"] == ("x1", "x2", "x3")
    assert rendered["consiglio_finale"]["entry_ids"] == ()


def test_an_empty_prose_section_renders_as_an_empty_string() -> None:
    rendered = render_draft(_a_draft(), _a_payload(), iana_zone=_IANA_ZONE)

    assert rendered["amore"]["text"] == ""
    assert rendered["amore"]["entry_ids"] == ()


def test_render_draft_covers_exactly_the_six_prose_sections() -> None:
    assert set(PROSE_SECTION_NAMES) == {
        "energia_generale",
        "amore",
        "lavoro",
        "denaro",
        "benessere",
        "consiglio_finale",
    }


# --- List Sections -------------------------------------------------------------------


def test_list_sections_render_one_item_per_day_list_entry() -> None:
    rendered = render_draft(_a_draft(), _a_payload(), iana_zone=_IANA_ZONE)

    assert len(rendered["giorni_favorevoli"]) == 2
    assert len(rendered["giorni_di_attenzione"]) == 1


def test_a_cited_day_list_entry_is_enriched_with_the_citing_sentence_text() -> None:
    rendered = render_draft(_a_draft(), _a_payload(), iana_zone=_IANA_ZONE)

    fav_1 = next(item for item in rendered["giorni_favorevoli"] if "fav-1" in item["entry_ids"])
    assert fav_1["text"] == "Venere favorisce gli incontri."
    # 2026-01-10 15:00 UTC -> 09:00 CST (UTC-6). Story 9.9: dd/MM/yyyy HH:mm.
    assert fav_1["date"] == "10/01/2026 09:00"


def test_an_uncited_day_list_entry_still_renders_date_only_never_dropped() -> None:
    """I/O & Edge-Case Matrix: "Uncited day-list entry" -- an entry in
    ``payload["day_lists"]`` no Sentence cites is still rendered, date only,
    never dropped."""
    rendered = render_draft(_a_draft(), _a_payload(), iana_zone=_IANA_ZONE)

    fav_2 = next(item for item in rendered["giorni_favorevoli"] if "fav-2" in item["entry_ids"])
    assert fav_2["text"] is None
    # 2026-01-18 09:00 UTC -> 03:00 CST (UTC-6). Story 9.9: dd/MM/yyyy HH:mm.
    assert fav_2["date"] == "18/01/2026 03:00"

    attention = rendered["giorni_di_attenzione"][0]
    assert attention["text"] is None
    assert attention["date"] == "15/01/2026 03:00"


def test_list_sections_are_sorted_chronologically_regardless_of_payload_order() -> None:
    """``payload["day_lists"]`` entries need not already be date-ordered
    (Story 3.7 explicitly left sorting to "a later story/view") -- the
    rendered list must come back sorted oldest-first regardless."""
    payload = {
        "day_lists": {
            "giorni_favorevoli": [
                {
                    "id": "fav-late",
                    "kind": "lunation",
                    "lunation_kind": "full_moon",
                    "occurred_at": "2026-01-25T09:00:00+00:00",
                    "longitude": "15.0",
                    "natal_house": 3,
                },
                {
                    "id": "fav-early",
                    "kind": "aspect",
                    "transiting_body": "venus",
                    "natal_point": "sun",
                    "aspect": "trine",
                    "perfected_at": "2026-01-05T15:00:00+00:00",
                    "never_perfected": False,
                    "orb_entry_at": "2026-01-03T12:00:00+00:00",
                    "orb_exit_at": "2026-01-07T12:00:00+00:00",
                },
                {
                    "id": "fav-mid",
                    "kind": "station",
                    "body": "mars",
                    "direction": "retrograde",
                    "station_at": "2026-01-15T09:00:00+00:00",
                    "longitude": "10.0",
                },
            ],
            "giorni_di_attenzione": [],
        }
    }
    draft = GeneratedDraft(
        energia_generale=(),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(),
    )

    rendered = render_draft(draft, payload, iana_zone=_IANA_ZONE)

    assert [item["entry_ids"][0] for item in rendered["giorni_favorevoli"]] == [
        "fav-early",
        "fav-mid",
        "fav-late",
    ]


def test_render_draft_covers_exactly_the_two_list_sections() -> None:
    assert set(LIST_SECTION_NAMES) == {"giorni_favorevoli", "giorni_di_attenzione"}


# --- SECTION_TITLES <-> SECTION_ORDER parity (epic-6-retro-item-50) -----------------


def test_section_titles_has_exactly_one_italian_heading_per_section_order_name() -> None:
    """The shared ``snake_case -> Italian-title`` map is the single source of
    truth for section headings across ``report.html`` / ``report_draft.html`` /
    ``report_export.html`` / the Markdown export. It must have exactly one
    entry per ``SECTION_ORDER`` name -- so a future ``GeneratedDraft`` field
    (picked up automatically by ``SECTION_ORDER``) cannot ship without an
    Italian heading, and no stale key lingers after a field is removed.
    """
    assert tuple(SECTION_TITLES) == SECTION_ORDER
    assert set(SECTION_TITLES) == set(SECTION_ORDER)
    for name, title in SECTION_TITLES.items():
        assert isinstance(title, str) and title.strip(), name
        assert title[:1] == title[:1].upper(), title  # sentence-cased

    # Not a naive `.replace("_", " ").title()` transform: Italian title casing
    # keeps interior prepositions/articles lowercase ("Giorni di attenzione").
    naive = {name: name.replace("_", " ").title() for name in SECTION_ORDER}
    assert naive != SECTION_TITLES


def test_section_titles_keeps_italian_lowercase_prepositions() -> None:
    assert SECTION_TITLES["giorni_di_attenzione"] == "Giorni di attenzione"
    assert SECTION_TITLES["giorni_favorevoli"] == "Giorni favorevoli"


def test_render_draft_does_not_mutate_its_inputs() -> None:
    draft = _a_draft()
    payload = _a_payload()
    draft_before = _draft_json_safe(draft)
    payload_before = dict(payload)

    render_draft(draft, payload, iana_zone=_IANA_ZONE)

    assert _draft_json_safe(draft) == draft_before
    assert payload == payload_before


# --- deserialize_generated_draft round trip -------------------------------------------


def test_a_day_list_entry_with_an_unrecognized_kind_raises_runtime_error() -> None:
    """epic-4-retro-item-32: ``project_day_lists()`` emits only
    ``aspect``/``lunation``/``station`` kinds, so a fourth ``kind`` in a
    day-list entry means ``freeze_payload()`` produced something impossible.
    ``_entry_date`` raises ``RuntimeError`` (an impossible-state guard,
    consistent with ``report_runs.py``'s other data-integrity guards), never
    a bare ``ValueError`` that would read like input validation."""
    payload = {
        "day_lists": {
            "giorni_favorevoli": [
                {
                    "id": "bogus-1",
                    "kind": "quasar",
                    "perfected_at": "2026-01-10T15:00:00+00:00",
                }
            ],
            "giorni_di_attenzione": [],
        }
    }

    with pytest.raises(RuntimeError) as caught:
        render_draft(_a_draft(), payload, iana_zone=_IANA_ZONE)

    # Exactly RuntimeError, not the bare builtin ValueError it used to raise.
    assert type(caught.value) is RuntimeError
    assert "kind" in str(caught.value)


def test_deserialize_generated_draft_round_trips_a_stored_draft() -> None:
    """The reverse of ``shell/adapters/postgres/report_draft.py``'s own
    ``_json_safe`` encoding: a ``GeneratedDraft`` serialized and read back
    must reconstruct equal to the original."""
    draft = _a_draft()

    stored = _draft_json_safe(draft)
    deserialized = deserialize_generated_draft(stored)

    assert deserialized == draft
