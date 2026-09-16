"""View-shaping for the client-facing PDF export (``report_export.html``,
spec-pdf-export-redesign) -- mirrors ``shell/http/draft_view.py`` /
``shell/http/payload_view.py``'s own "view-shaping lives in ``shell/http/``"
pattern: birth-date/time formatting, Sun/Moon/Ascendant extraction, the
report month's Italian label, and the day-list date reshaping this export
alone needs.

Nothing here touches ``draft_view.py``'s own ``render_draft()``/date shape
(``dd/mm/yyyy``, shared by ``report.html`` and the Markdown export) --
``build_export_context()`` takes that function's already-rendered output and
reshapes a copy of it for this one template, per this story's Boundaries.
"""

from __future__ import annotations

import re
from datetime import date as date_type
from datetime import time as time_type
from decimal import Decimal
from typing import Any

from shell.adapters.postgres.client import Client, StoredNatalChart
from shell.adapters.postgres.report_run import ReportRun

__all__ = ["build_export_context"]

#: English sign name (``core/ephemeris/chart.py``'s ``_ZODIAC_SIGNS`` shape,
#: also ``PlanetPosition.sign``'s own value) -> Italian display name.
#: Reimplemented locally rather than importing ``core/gate/run.py``'s private
#: ``_SIGN_MAP`` (keyed the other way, lowercase) -- AD-1 forbids importing a
#: private name across modules regardless, and this module needs the
#: capitalized Italian display form, not the Gate's matching-token form.
_ZODIAC_SIGNS_IT: dict[str, str] = {
    "aries": "Ariete",
    "taurus": "Toro",
    "gemini": "Gemelli",
    "cancer": "Cancro",
    "leo": "Leone",
    "virgo": "Vergine",
    "libra": "Bilancia",
    "scorpio": "Scorpione",
    "sagittarius": "Sagittario",
    "capricorn": "Capricorno",
    "aquarius": "Acquario",
    "pisces": "Pesci",
}

#: Zodiac sign order (English), matching ``core/ephemeris/chart.py``'s own
#: ``_ZODIAC_SIGNS`` -- needed only to decompose ``StoredNatalChart.ascendant``
#: (an absolute longitude, never pre-split into sign/degree, unlike a stored
#: planet) by index by ``divmod(longitude, 30)``, per this story's Design
#: Notes ("reimplemented locally since ``_sign_and_degree`` is private").
_ZODIAC_SIGN_ORDER: tuple[str, ...] = (
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
)

#: Italian month names, 1-indexed (``run.month``'s ``"YYYY-MM"`` -> a spelled
#: header like "Ottobre 2026"; ``Client.birth_date`` -> "21 marzo 1990").
_MONTH_NAMES_IT: dict[int, str] = {
    1: "gennaio",
    2: "febbraio",
    3: "marzo",
    4: "aprile",
    5: "maggio",
    6: "giugno",
    7: "luglio",
    8: "agosto",
    9: "settembre",
    10: "ottobre",
    11: "novembre",
    12: "dicembre",
}

#: Three-letter Italian month abbreviations for the day-list timeline dots
#: (mockup: "OTT", rendered here in title case -- the template's own
#: ``text-transform: uppercase`` does the rest, matching every other label
#: in the design's Style table).
_MONTH_ABBR_IT: dict[int, str] = {
    1: "Gen",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "Mag",
    6: "Giu",
    7: "Lug",
    8: "Ago",
    9: "Set",
    10: "Ott",
    11: "Nov",
    12: "Dic",
}


def _split_degree(degree: Decimal) -> tuple[int, int]:
    """A 0-30 (or 0-360) ``Decimal`` degree into (whole degrees, minutes),
    per this story's Design Notes: ``whole = int(degree)``, ``minutes =
    round((degree - whole) * 60)``, rolling ``minutes == 60`` into
    ``whole += 1`` (a value that rounds up to a full minute at the next
    whole degree, e.g. 29.999 degrees, must never display "29° 60′")."""
    whole = int(degree)
    minutes = round((degree - whole) * 60)
    if minutes == 60:
        whole += 1
        minutes = 0
    return whole, minutes


def _degree_label(degree: Decimal) -> str:
    whole, minutes = _split_degree(degree)
    return f"{whole}° {minutes:02d}′"


def _planet_by_name(chart: StoredNatalChart, name: str) -> dict[str, Any]:
    """The one ``chart.planets`` entry named ``name`` (``"sun"``/``"moon"``)
    -- a data-integrity bug if missing, since ``core/ephemeris/chart.py``
    always computes and stores all ten planets plus both Nodes."""
    for planet in chart.planets:
        if planet["name"] == name:
            return planet
    raise RuntimeError(f"StoredNatalChart {chart.id} has no '{name}' planet position.")


def _placement(chart: StoredNatalChart, name: str) -> dict[str, Any]:
    """Sun/Moon: the Italian sign, the degree/minute label and the house --
    ``sign``/``degree`` are already decomposed and stored on the planet
    (``core/types/chart.py``'s ``PlanetPosition``), read back as strings from
    the JSON column (mirrors ``shell/http/chart_wheel.py``'s own
    ``Decimal(planet["longitude"])`` read-back pattern).

    Guards each key's presence explicitly, mirroring ``_planet_by_name``'s
    own ``RuntimeError`` -- a malformed/partial planet dict is a
    data-integrity bug, never a bare ``KeyError`` that would read like an
    ordinary programming mistake rather than a corrupt stored row."""
    planet = _planet_by_name(chart, name)
    for key in ("sign", "degree", "house"):
        if key not in planet:
            raise RuntimeError(
                f"StoredNatalChart {chart.id}'s '{name}' planet position has no '{key}' key."
            )
    sign_en = str(planet["sign"])
    degree = Decimal(planet["degree"])
    return {
        "sign": _ZODIAC_SIGNS_IT[sign_en],
        "degree_label": _degree_label(degree),
        "house": int(planet["house"]),
    }


def _ascendant_placement(chart: StoredNatalChart) -> dict[str, Any]:
    """The Ascendant: ``StoredNatalChart.ascendant`` is an absolute ecliptic
    longitude (0-360), never pre-split into sign/degree the way a stored
    planet is -- decomposed here via ``divmod(longitude, 30)``, matching
    this story's Design Notes."""
    sign_index, degree_in_sign = divmod(chart.ascendant, Decimal(30))
    sign_en = _ZODIAC_SIGN_ORDER[int(sign_index) % 12]
    return {
        "sign": _ZODIAC_SIGNS_IT[sign_en],
        "degree_label": _degree_label(degree_in_sign),
    }


def _format_birth_date(birth_date: date_type) -> str:
    """``date(1990, 3, 21)`` -> ``"21 marzo 1990"`` (Style table: "Header
    dates use the spelled-out month")."""
    return f"{birth_date.day} {_MONTH_NAMES_IT[birth_date.month]} {birth_date.year}"


def _format_birth_time(birth_time: time_type) -> str:
    return f"{birth_time.hour:02d}:{birth_time.minute:02d}"


def _month_label(month: str) -> str:
    """``"2026-10"`` -> ``"Ottobre 2026"`` (``_MONTH_PATTERN`` in
    ``shell/http/routes/report_runs.py`` already guarantees the
    ``"YYYY-MM"`` shape at submission time -- never re-validated here)."""
    year_str, month_str = month.split("-")
    name = _MONTH_NAMES_IT[int(month_str)]
    return f"{name.capitalize()} {year_str}"


def _split_day_list_date(date_ddmmyyyy: str) -> tuple[int, str]:
    """``render_draft()``'s own list-Section date shape (``dd/mm/yyyy``,
    ``shell/http/draft_view.py``'s ``_render_list``) -> (day number, Italian
    month abbreviation) -- this story's one day-list reshaping, local to this
    module (Boundaries: ``draft_view.py``'s own date field is never
    touched)."""
    day_str, month_str, _year_str = date_ddmmyyyy.split("/")
    return int(day_str), _MONTH_ABBR_IT[int(month_str)]


#: Every character ``_css_single_quoted_string()`` must not emit literally:
#: backslash and the quote character (so the value can never break out of
#: its own quotes), ``<`` (so a Client name can never prematurely close the
#: surrounding ``<style>`` element), and every C0 control character plus DEL
#: (0x00-0x1F, 0x7F) -- CSS strings cannot contain a raw, unescaped newline
#: at all (it is a parse error, not just cosmetic), and the rest are
#: escaped alongside it rather than special-cased, since none of them are
#: legitimate in a Client's display name either.
_CSS_STRING_ESCAPE_NEEDED = re.compile(r"[\\'<\x00-\x1f\x7f]")


def _css_escape_one(match: re.Match[str]) -> str:
    char = match.group(0)
    if char == "\\":
        return "\\\\"
    if char == "'":
        return "\\'"
    if char == "<":
        return "\\3c "
    # A CSS hex escape (backslash + hex codepoint + a delimiting space) --
    # the general form, covering every C0 control character and DEL
    # (including newline, `\a `) without a special case per character.
    return f"\\{ord(char):x} "


def _css_single_quoted_string(value: str) -> str:
    """A CSS single-quoted string literal for ``value``, safe to emit
    verbatim (``|safe``, bypassing Jinja's HTML-escaping) inside a
    ``<style>`` block's ``string-set`` declaration -- the footer's running
    ``"{client} · {month}"`` text (Style table). WeasyPrint 69 supports
    neither ``string-set: ... content();`` nor ``leader()`` (both verified
    empirically to silently drop the declaration), so the footer text must
    be a literal CSS string, built here rather than left to Jinja's
    HTML-entity escaping -- which would leave literal ``&#39;`` sequences in
    a Client name containing an apostrophe rather than the character itself.

    See ``_CSS_STRING_ESCAPE_NEEDED`` for exactly what gets escaped and why.
    """
    escaped = _CSS_STRING_ESCAPE_NEEDED.sub(_css_escape_one, value)
    return f"'{escaped}'"


def _day_list(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reshaped = []
    for entry in entries:
        day, month_abbr = _split_day_list_date(entry["date"])
        reshaped.append({"day": day, "month_abbr": month_abbr, "text": entry["text"]})
    return reshaped


def build_export_context(
    *,
    client: Client,
    run: ReportRun,
    rendered: dict[str, Any],
    chart: StoredNatalChart,
    wheel_svg: str,
) -> dict[str, Any]:
    """Every value ``report_export.html`` reads, built from the run's own
    natal chart (``ReportRun.natal_chart_id``, never the Client's current
    chart) plus ``rendered`` (``render_draft()``'s own output, reused
    unchanged and only reshaped here -- never re-rendered from the raw
    draft)."""
    month_label = _month_label(run.month)
    return {
        "client_name": client.name,
        "month_label": month_label,
        "footer_left_css": _css_single_quoted_string(f"{client.name} · {month_label}"),
        "birth_date_label": _format_birth_date(client.birth_date),
        "birth_time_label": _format_birth_time(client.birth_time),
        "birthplace_name": client.birthplace_name,
        "sun": _placement(chart, "sun"),
        "moon": _placement(chart, "moon"),
        "ascendant": _ascendant_placement(chart),
        "wheel_svg": wheel_svg,
        "energia_generale_text": rendered["energia_generale"]["text"],
        "amore_text": rendered["amore"]["text"],
        "lavoro_text": rendered["lavoro"]["text"],
        "denaro_text": rendered["denaro"]["text"],
        "benessere_text": rendered["benessere"]["text"],
        "giorni_favorevoli": _day_list(rendered["giorni_favorevoli"]),
        "giorni_di_attenzione": _day_list(rendered["giorni_di_attenzione"]),
        "consiglio_finale_text": rendered["consiglio_finale"]["text"],
    }
