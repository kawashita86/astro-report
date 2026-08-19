"""``shell/runner/month.py::client_month_interval_utc`` -- Story 3.5's own
I/O & Edge-Case Matrix rows for month resolution."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from shell.adapters.postgres.client import Client
from shell.runner.month import client_month_interval_utc


def _a_client(*, iana_zone: str = "America/Chicago") -> Client:
    return Client(
        name="Ada Lovelace",
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        latitude=Decimal("32.7358"),
        longitude=Decimal("-97.3453"),
        iana_zone=iana_zone,
    )


def test_a_january_month_resolves_to_its_utc_boundaries() -> None:
    client = _a_client()

    start, end = client_month_interval_utc(client, "2026-01")

    # America/Chicago is UTC-6 (CST) in January.
    assert start == datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 2, 1, 6, 0, 0, tzinfo=UTC)


def test_a_december_month_rolls_over_into_the_next_year() -> None:
    client = _a_client()

    start, end = client_month_interval_utc(client, "2026-12")

    assert start == datetime(2026, 12, 1, 6, 0, 0, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, 6, 0, 0, tzinfo=UTC)


def test_the_interval_is_half_open_and_strictly_ordered() -> None:
    client = _a_client()

    start, end = client_month_interval_utc(client, "2026-03")

    assert start < end
    assert start.tzinfo is not None and start.utcoffset() == timedelta(0)
    assert end.tzinfo is not None and end.utcoffset() == timedelta(0)


def test_a_utc_client_month_is_exactly_the_calendar_month() -> None:
    client = _a_client(iana_zone="UTC")

    start, end = client_month_interval_utc(client, "2026-06")

    assert start == datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)


def test_malformed_month_raises_value_error() -> None:
    client = _a_client()

    with pytest.raises(ValueError, match="YYYY-MM"):
        client_month_interval_utc(client, "not-a-month")


def test_a_dst_observing_zone_never_raises_across_a_full_year() -> None:
    """A month boundary a zone's DST transition falls on must still resolve
    to a valid, unambiguous UTC pair (the story's I/O matrix) rather than
    raising -- zoneinfo (PEP 495) always picks a well-defined offset for a
    local time a fold or gap makes ambiguous, so this holds for every month
    of a DST-observing zone's year, not only the ones that happen to sit
    exactly on a transition."""
    client = _a_client(iana_zone="America/Chicago")

    previous_end: datetime | None = None
    for month_number in range(1, 13):
        start, end = client_month_interval_utc(client, f"2026-{month_number:02d}")
        assert start < end
        if previous_end is not None:
            assert start == previous_end, "months must tile with no gap or overlap"
        previous_end = end


def test_unknown_iana_zone_raises_value_error() -> None:
    client = _a_client(iana_zone="Not/A_Real_Zone")

    with pytest.raises(ValueError):
        client_month_interval_utc(client, "2026-01")
