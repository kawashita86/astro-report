"""``shell/http/report_markdown.py::render_report_markdown`` -- the Markdown
serializer for a passed Report's export (spec-6-2b, epic-6 retro item 47).

Built from a real ``shell/http/draft_view.py::render_draft`` output (not a
hand-rolled ``rendered`` dict), so the content model this asserts on is
exactly the one the PDF template consumes.
"""

from __future__ import annotations

from typing import Any

from core.types.generation import GeneratedDraft, Sentence
from shell.http.draft_view import (
    LIST_SECTION_NAMES,
    SECTION_ORDER,
    SECTION_TITLES,
    render_draft,
)
from shell.http.report_markdown import render_report_markdown

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
            Sentence(text="Prosegue con calma.", entry_ids=("x2",)),
        ),
        amore=(),
        lavoro=(Sentence(text="Buone occasioni professionali.", entry_ids=("x4",)),),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(
            Sentence(text="Venere favorisce gli incontri.", entry_ids=("fav-1",)),
        ),
        giorni_di_attenzione=(),
        consiglio_finale=(Sentence(text="Respira.", entry_ids=()),),
    )


def _render() -> str:
    rendered = render_draft(_a_draft(), _a_payload(), iana_zone=_IANA_ZONE)
    return render_report_markdown(
        rendered,
        client_name="Ada Lovelace",
        section_order=SECTION_ORDER,
        list_section_names=LIST_SECTION_NAMES,
        section_titles=SECTION_TITLES,
    )


def test_the_client_name_is_the_h1_title() -> None:
    markdown = _render()

    assert markdown.startswith("# Ada Lovelace\n")


def test_every_section_appears_once_with_its_italian_heading_in_order() -> None:
    markdown = _render()

    headings = [line for line in markdown.splitlines() if line.startswith("## ")]
    assert headings == [f"## {SECTION_TITLES[name]}" for name in SECTION_ORDER]
    # The raw snake_case field names never leak into the client-facing file.
    # Only underscore-bearing names are real canaries -- `amore` / `lavoro` /
    # `denaro` / `benessere` are ordinary Italian words that occur in prose.
    for name in (
        "energia_generale",
        "giorni_favorevoli",
        "giorni_di_attenzione",
        "consiglio_finale",
    ):
        assert name not in markdown


def test_prose_sections_render_as_their_joined_paragraph() -> None:
    markdown = _render()

    assert "## Energia generale\n\nIl mese si apre con energia. Prosegue con calma." in markdown
    assert "## Lavoro\n\nBuone occasioni professionali." in markdown


def test_an_empty_prose_section_renders_its_heading_and_a_blank_body() -> None:
    markdown = _render()

    # `amore` has no sentences -> heading present, body is the empty string.
    assert "## Amore\n\n\n## Lavoro" in markdown


def test_list_sections_render_one_dash_bullet_per_day_entry_date_prefixed() -> None:
    markdown = _render()

    # 2026-01-10 15:00 UTC -> 09:00 CST; cited, so text is appended. Day-list
    # entries show the date only, never a time-of-day (fix, 2026-09-03).
    assert "- 10/01/2026 — Venere favorisce gli incontri." in markdown
    # 2026-01-18 09:00 UTC -> 03:00 CST; uncited -> date only, still emitted.
    assert "- 18/01/2026\n" in markdown
    # The lone attention entry is uncited too and must not be dropped.
    assert "## Giorni di attenzione\n\n- 15/01/2026" in markdown


def test_the_body_is_the_eight_sections_and_the_name_only() -> None:
    markdown = _render()

    assert "Gate" not in markdown
    assert "Payload" not in markdown
    assert "regenerat" not in markdown
    assert markdown.endswith("\n")
