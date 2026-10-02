"""The export template's block layout keeps WeasyPrint fast (Story 10.1).

``report_export.html`` once nested prose in ~20 flex/grid containers, which
WeasyPrint re-measures word by word (3.5 s locally, 20-25 s on the VPS). This
renders a realistic-length report with a real natal wheel and guards both the
time budget and the absence of flex/grid on prose cards, so the cost cannot
creep back in unnoticed.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session
from weasyprint import HTML

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import create_client_with_chart
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.weasyprint.render import html_to_pdf
from shell.computation import load_computation_config
from shell.http import app as _app  # noqa: F401  (import order: breaks a circular import)
from shell.http.report_export_view import build_export_context
from shell.http.routes import report_runs as report_runs_module
from tests._fk import fk_enforcing_engine

_BUDGET_SECONDS = 1.2
_SENTENCE = (
    "La configurazione del mese invita a rallentare e a guardare con attenzione "
    "ai rapporti che contano, senza forzare le decisioni che non sono ancora mature. "
)


def _prose(sentences: int) -> str:
    return (_SENTENCE * sentences).strip()


def _day_entries(count: int) -> list[dict[str, Any]]:
    return [
        {"date": f"{3 * i + 2:02d}/01/2026", "text": _prose(1)} for i in range(count)
    ]


def _realistic_rendered() -> dict[str, Any]:
    return {
        "energia_generale": {"text": _prose(2)},
        "amore": {"text": _prose(2)},
        "lavoro": {"text": _prose(2)},
        "denaro": {"text": _prose(2)},
        "benessere": {"text": _prose(2)},
        "giorni_favorevoli": _day_entries(3),
        "giorni_di_attenzione": _day_entries(3),
        "consiglio_finale": {"text": _prose(2)},
    }


def render_export_html(rendered: dict[str, Any] | None = None) -> str:
    config = load_computation_config()
    place = ResolvedPlace(
        latitude=Decimal("45.4642"),
        longitude=Decimal("9.19"),
        iana_zone="Europe/Rome",
        utc_offset=timedelta(hours=1),
    )
    chart = compute_natal_chart(
        datetime(1990, 5, 17, 7, 30, tzinfo=UTC), place.latitude, place.longitude, config
    )
    engine = fk_enforcing_engine()
    with Session(engine) as session:
        client = create_client_with_chart(
            session,
            name="Ada Lovelace",
            birth_date=date(1990, 5, 17),
            birth_time=dtime(9, 30),
            resolved_place=place,
            natal_chart=chart,
            computation_config=config,
            ephemeris_identity=verify_ephemeris_identity(),
        )
        run = ReportRun(client_id=client.id, month="2026-01")
        session.add(run)
        session.commit()
        stored_chart = report_runs_module.current_chart_for_client(session, client.id)
        wheel_svg = report_runs_module._build_wheel_svg(
            client, stored_chart, config.orbs.natal
        )
        context = build_export_context(
            client=client,
            run=run,
            rendered=rendered if rendered is not None else _realistic_rendered(),
            chart=stored_chart,
            wheel_svg=wheel_svg,
        )
    return report_runs_module._templates.get_template("report_export.html").render(context)


@pytest.fixture(scope="module")
def export_html() -> str:
    return render_export_html()


def test_html_to_pdf_stays_within_the_time_budget(export_html: str) -> None:
    base_url = report_runs_module._TEMPLATES_BASE_URL
    pdf = html_to_pdf(export_html, base_url=base_url)  # warm-up (fonts, caches)
    assert pdf.startswith(b"%PDF")

    timings = []
    for _ in range(3):
        started = time.perf_counter()
        html_to_pdf(export_html, base_url=base_url)
        timings.append(time.perf_counter() - started)

    assert min(timings) <= _BUDGET_SECONDS, timings


def _day_list_card_pages(document: Any) -> list[list[int]]:
    """For each ``.day-list-card`` in document order, the pages it spans."""
    pages: dict[int, list[int]] = {}

    def walk(box: Any, number: int) -> None:
        element = getattr(box, "element", None)
        if element is not None and "day-list-card" in (element.get("class") or "").split():
            spans = pages.setdefault(id(element), [])
            if number not in spans:
                spans.append(number)
            return
        for child in getattr(box, "children", ()):
            walk(child, number)

    order: list[int] = []
    for number, page in enumerate(document.pages, start=1):
        before = set(pages)
        walk(page._page_box, number)
        order += [key for key in pages if key not in before]
    return [pages[key] for key in order]


def test_long_day_lists_stack_instead_of_paginating_side_by_side() -> None:
    # A real month yields ~20 favourable and ~10 caution entries, so both
    # day-list cards span pages. Side by side (two floats) WeasyPrint
    # fragmented them out of step: blank pages, one caution entry per page,
    # Consiglio finale painted over the lists, and NaN-height backgrounds.
    rendered = _realistic_rendered()
    rendered["giorni_favorevoli"] = [
        {"date": f"{i + 1:02d}/01/2026", "text": _prose(2)} for i in range(18)
    ]
    rendered["giorni_di_attenzione"] = [
        {"date": f"{3 * i + 1:02d}/01/2026", "text": _prose(3)} for i in range(8)
    ]
    document = HTML(
        string=render_export_html(rendered),
        base_url=report_runs_module._TEMPLATES_BASE_URL,
    ).render()

    favorevoli, attenzione = _day_list_card_pages(document)
    assert max(favorevoli) <= min(attenzione), (favorevoli, attenzione)
    # The split floats also drew card backgrounds with a NaN height, which
    # PDF readers report as a syntax error.
    assert b" nan " not in document.write_pdf(uncompressed_pdf=True)


_ALLOWED_FLEX_SELECTORS = {".data-row", ".placement-row"}


def _flex_grid_offenders(css: str) -> list[str]:
    """Selectors in ``css`` that use flex/grid though they are neither a
    small fixed-size row nor an icon-plus-heading ``*-header`` row."""
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    flex_selectors = [
        selector.strip()
        for selector, body in rules
        if re.search(r"display:\s*(inline-)?(flex|grid)|flex-direction|grid-template", body)
    ]
    return [
        s
        for s in flex_selectors
        if s not in _ALLOWED_FLEX_SELECTORS and not re.fullmatch(r"\.[a-z-]+-header", s)
    ]


def test_prose_cards_do_not_use_flex_or_grid() -> None:
    template = (
        Path(report_runs_module._TEMPLATES_DIR) / "report_export.html"
    ).read_text(encoding="utf-8")
    assert _flex_grid_offenders(template.split("</style>")[0]) == []


def test_the_guard_detects_a_flex_prose_card() -> None:
    css = ".domain-card { display: flex; flex-direction: column; }"
    assert _flex_grid_offenders(css) == [".domain-card"]
    assert _flex_grid_offenders(".placement-row { display: flex; }") == []
