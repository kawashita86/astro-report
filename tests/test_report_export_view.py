"""``shell/http/report_export_view.py`` -- direct unit coverage for the
client-facing PDF export's pure view-shaping functions (spec-pdf-export-
redesign), which the HTTP-level tests in ``tests/test_http_report_runs.py``
only exercise indirectly through a real ``/export/pdf`` request.

Covers: the degree/minute split's minute-rollover edge case, the
Ascendant's sign-wraparound at the 0/360-degree boundary, a malformed
planet dict's ``RuntimeError`` guard, the month/date/time formatters, and
``_css_single_quoted_string``'s escaping (including control characters, per
review-loop feedback).
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from uuid import uuid4

import pytest

from shell.adapters.postgres.client import Client, StoredNatalChart
from shell.adapters.postgres.report_run import ReportRun
from shell.http.report_export_view import (
    _ascendant_placement,
    _css_single_quoted_string,
    _degree_label,
    _format_birth_date,
    _format_birth_time,
    _month_label,
    _placement,
    _split_day_list_date,
    _split_degree,
    build_export_context,
)

# --- _split_degree / _degree_label -------------------------------------------------


def test_split_degree_rolls_minutes_60_into_the_next_whole_degree() -> None:
    """Design Notes: ``minutes == 60`` rolls into ``whole += 1`` -- a value
    that rounds up to a full minute at the next whole degree must never
    display as "29° 60′"."""
    assert _split_degree(Decimal("29.999")) == (30, 0)


def test_split_degree_does_not_roll_when_minutes_stay_under_60() -> None:
    assert _split_degree(Decimal("15.5")) == (15, 30)
    assert _split_degree(Decimal("0")) == (0, 0)


def test_degree_label_zero_pads_minutes() -> None:
    assert _degree_label(Decimal("0.5")) == "0° 30′"
    assert _degree_label(Decimal("29.999")) == "30° 00′"


# --- _ascendant_placement: sign-wraparound at the 0/360-degree boundary ------------


def _a_chart(ascendant: str, planets: list[dict] | None = None) -> StoredNatalChart:
    return StoredNatalChart(
        id=uuid4(),
        client_id=uuid4(),
        ascendant=Decimal(ascendant),
        midheaven=Decimal("0"),
        planets=planets or [],
        houses=[],
        aspects=[],
        computation_config_version=1,
        computation_config_content_hash="a" * 64,
        ephemeris_files=[],
    )


def test_ascendant_placement_wraps_the_sign_index_at_exactly_360_degrees() -> None:
    """``divmod(360, 30)`` is ``(12, 0)`` -- without the defensive ``% 12``
    in ``_ascendant_placement``, sign index 12 would be an out-of-range
    ``IndexError`` against the 12-entry zodiac tuple rather than wrapping
    back to Ariete."""
    assert _ascendant_placement(_a_chart("360")) == {
        "sign": "Ariete",
        "degree_label": "0° 00′",
    }


def test_ascendant_placement_just_under_360_degrees_stays_in_pesci() -> None:
    assert _ascendant_placement(_a_chart("359.5")) == {
        "sign": "Pesci",
        "degree_label": "29° 30′",
    }


def test_ascendant_placement_just_over_0_degrees_is_ariete() -> None:
    assert _ascendant_placement(_a_chart("0.1")) == {
        "sign": "Ariete",
        "degree_label": "0° 06′",
    }


# --- _placement: a malformed planet dict raises, never a bare KeyError ------------


def test_placement_raises_runtime_error_for_a_planet_dict_missing_a_key() -> None:
    """Mirrors ``_planet_by_name``'s own ``RuntimeError`` for a missing
    planet -- a malformed/partial planet dict (here, no ``house`` key) is a
    data-integrity bug, never a bare ``KeyError`` that would read like an
    ordinary programming mistake rather than a corrupt stored row."""
    chart = _a_chart("0", planets=[{"name": "sun", "sign": "aries", "degree": "0.5"}])

    with pytest.raises(RuntimeError, match="'sun' planet position has no 'house' key"):
        _placement(chart, "sun")


def test_placement_raises_runtime_error_when_the_named_planet_is_missing() -> None:
    chart = _a_chart("0", planets=[])

    with pytest.raises(RuntimeError, match="has no 'sun' planet position"):
        _placement(chart, "sun")


# --- _month_label / _format_birth_date / _format_birth_time -----------------------


def test_month_label_spells_out_and_capitalizes_the_italian_month() -> None:
    assert _month_label("2026-10") == "Ottobre 2026"
    assert _month_label("2026-01") == "Gennaio 2026"


def test_format_birth_date_spells_out_the_month_no_leading_zero_on_the_day() -> None:
    assert _format_birth_date(date(1990, 3, 21)) == "21 marzo 1990"
    assert _format_birth_date(date(1990, 3, 1)) == "1 marzo 1990"


def test_format_birth_time_is_24_hour_zero_padded() -> None:
    assert _format_birth_time(time(9, 5)) == "09:05"
    assert _format_birth_time(time(23, 0)) == "23:00"


# --- _split_day_list_date -----------------------------------------------------------


def test_split_day_list_date_reads_render_drafts_ddmmyyyy_shape() -> None:
    assert _split_day_list_date("04/10/2026") == (4, "Ott")
    assert _split_day_list_date("31/01/2026") == (31, "Gen")


# --- _css_single_quoted_string: CSS-string escaping ---------------------------------


def test_css_single_quoted_string_escapes_backslash_quote_and_angle_bracket() -> None:
    assert _css_single_quoted_string("O'Brien") == "'O\\'Brien'"
    assert _css_single_quoted_string("back\\slash") == "'back\\\\slash'"
    assert _css_single_quoted_string("<script>") == "'\\3c script>'"


def test_css_single_quoted_string_escapes_newlines_and_control_characters() -> None:
    """Review-loop feedback: backslash/quote/``<`` were escaped, but a raw
    newline (invalid inside an unescaped CSS string -- a parse error, not
    just cosmetic) was not. A Client name is most unlikely to contain a
    literal newline or control character, but the escaper must not produce
    broken CSS if one ever does."""
    assert _css_single_quoted_string("line1\nline2") == "'line1\\a line2'"
    # \x01 (an arbitrary C0 control character) -> the same general hex-escape
    # path as newline, not a special case.
    assert _css_single_quoted_string("a\x01b") == "'a\\1 b'"


def test_css_single_quoted_string_round_trips_plain_text_unchanged() -> None:
    assert _css_single_quoted_string("Giulia Rossi") == "'Giulia Rossi'"


# --- build_export_context: the full assembly, spot-checked -------------------------


def test_build_export_context_passes_through_a_null_birthplace_unchanged() -> None:
    """``build_export_context`` itself does no NULL-handling -- the template
    decides whether to render the *Luogo di nascita* row. This just proves
    the raw ``None`` reaches the context unmodified, not coerced to ``""``
    or dropped from the dict."""
    client = Client(
        id=uuid4(),
        name="Giulia Rossi",
        birth_date=date(1990, 3, 21),
        birth_time=time(10, 30),
        latitude=Decimal("41.9"),
        longitude=Decimal("12.5"),
        iana_zone="Europe/Rome",
        birthplace_name=None,
    )
    run = ReportRun(id=uuid4(), client_id=client.id, month="2026-10")
    chart = _a_chart(
        "86.78",
        planets=[
            {"name": "sun", "sign": "aries", "degree": "0.5", "house": 10},
            {"name": "moon", "sign": "capricorn", "degree": "20.9166666667", "house": 8},
        ],
    )
    rendered = {
        "energia_generale": {"text": "x"},
        "amore": {"text": "x"},
        "lavoro": {"text": "x"},
        "denaro": {"text": "x"},
        "benessere": {"text": "x"},
        "giorni_favorevoli": [],
        "giorni_di_attenzione": [],
        "consiglio_finale": {"text": "x"},
    }

    context = build_export_context(
        client=client, run=run, rendered=rendered, chart=chart, wheel_svg="<svg></svg>"
    )

    assert context["birthplace_name"] is None
    assert context["month_label"] == "Ottobre 2026"
    assert context["sun"]["sign"] == "Ariete"
    assert context["moon"]["sign"] == "Capricorno"
