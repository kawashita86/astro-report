"""``tests/_release_validation.py`` -- the shared record-guard scaffolding
lifted out of the four ``docs/release-validation/*.md`` suites
(epic-8-retro-item-62).

The four record modules exercise :func:`load_record_meta` and the fresh-record
side of :func:`assert_record_not_stale` in situ. This module covers the pieces
they do not: the stale-record and future-date failure paths, the ``today``
injection point, the ``meta["checked"]`` type guard, and the
``extract_toml_block`` error message.
"""

from __future__ import annotations

import datetime

import pytest

from tests._release_validation import (
    assert_not_stale,
    assert_record_not_stale,
    extract_toml_block,
)

_TODAY = datetime.date(2026, 8, 28)


def test_assert_not_stale_passes_when_checked_is_within_the_window() -> None:
    assert_not_stale(
        _TODAY - datetime.timedelta(days=550),
        max_age_days=550,
        record_label="example",
        today=_TODAY,
    )


def test_assert_not_stale_raises_once_checked_is_older_than_max_age_days() -> None:
    with pytest.raises(AssertionError, match=r"551 days old \(> 550\)"):
        assert_not_stale(
            _TODAY - datetime.timedelta(days=551),
            max_age_days=550,
            record_label="example",
            today=_TODAY,
        )


def test_assert_not_stale_rejects_a_future_checked_date() -> None:
    with pytest.raises(AssertionError, match="in the future"):
        assert_not_stale(
            _TODAY + datetime.timedelta(days=1),
            max_age_days=550,
            record_label="example",
            today=_TODAY,
        )


def test_assert_not_stale_defaults_today_to_the_real_calendar_date() -> None:
    # A checked date decades in the past must fail against whatever today is.
    with pytest.raises(AssertionError):
        assert_not_stale(
            datetime.date(2000, 1, 1), max_age_days=550, record_label="example"
        )


def test_assert_record_not_stale_flags_a_non_date_checked_field() -> None:
    with pytest.raises(AssertionError, match="must be a bare ISO date"):
        assert_record_not_stale(
            {"checked": "2026-08-27"}, max_age_days=550, record_label="example"
        )


def test_assert_record_not_stale_passes_a_fresh_date_through() -> None:
    assert_record_not_stale(
        {"checked": datetime.date(2000, 1, 1)},
        max_age_days=10_000_000,
        record_label="example",
    )


def test_extract_toml_block_names_the_record_when_no_fenced_block_is_present() -> None:
    with pytest.raises(AssertionError, match="the widget record has no ```toml"):
        extract_toml_block("no fenced block here", record_label="widget")
