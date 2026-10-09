"""Story 11.3: ``POST /api/v1/charts/transits``.

The real app built through ``create_app``; only the session is substituted
(an FK-enforcing in-memory SQLite) so a row-count check can prove the endpoint
writes nothing. Expected values come from calling the ``core/transits`` scans
directly over the same UTC interval.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlmodel import Session, SQLModel

from core.ephemeris.chart import compute_natal_chart
from core.transits.aspects import find_transit_aspects
from core.transits.ingresses import find_ingresses
from core.transits.lunations import find_lunations
from core.transits.stations import find_stations
from core.types.transits import Station
from shell.http.api import transits as transits_module
from shell.http.api.places import get_api_session
from shell.http.app import computation_config, create_app
from tests._fk import fk_enforcing_engine
from tests.test_api_skeleton import BEARER, WITH_TOKEN

MILAN = {
    "latitude": "45.4642",
    "longitude": "9.1900",
    "iana_zone": "Europe/Rome",
    "display_name": "Milano, Lombardia, Italia",
}
# Positions are quantized to 0.0001 degrees, so a slow body's bisected instant moves by seconds
# when the grid phase shifts (local-midnight months drift with daylight saving). Exact equality
# is proved in test_transit_window_seam.py, where the phase is shared.
_TOLERANCE = timedelta(minutes=10)
YEAR = {"start_date": "2026-01-01", "end_date": "2027-01-01"}


def _subject(**overrides: Any) -> dict[str, Any]:
    subject: dict[str, Any] = {
        "label": "Caso di prova",
        "birth_date": "1985-03-12",
        "birth_time": "14:30",
        "time_known": True,
        "place": dict(MILAN),
    }
    subject.update(overrides)
    return subject


def _request(window: dict[str, str] | None = None, **subject: Any) -> dict[str, Any]:
    return {"subject": _subject(**subject), "window": window or dict(YEAR)}


@pytest.fixture
def engine() -> Engine:
    return fk_enforcing_engine(shared_across_threads=True)


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    application: FastAPI = create_app(WITH_TOKEN)

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_api_session] = _session
    yield TestClient(application, raise_server_exceptions=False)


def _post(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post("/api/v1/charts/transits", headers=BEARER, json=body)


def _assert_error(response: Any, code: str, field: str | None) -> None:
    body = response.json()
    assert (body["code"], body["field"]) == (code, field), body
    assert body["message"]


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def year_body() -> dict[str, Any]:
    """The 12-month known-time response, computed once for the module."""
    application = create_app(WITH_TOKEN)
    response = TestClient(application).post(
        "/api/v1/charts/transits", headers=BEARER, json=_request()
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


# --- Known time ----------------------------------------------------------------


def test_a_twelve_month_window_equals_the_core_scans_over_the_same_interval(
    year_body: dict[str, Any],
) -> None:
    start = _instant(year_body["window_utc"]["start"])
    end = _instant(year_body["window_utc"]["end"])
    # Rome is UTC+1 on 1 January in both years.
    assert (start, end) == (
        datetime(2025, 12, 31, 23, tzinfo=UTC),
        datetime(2026, 12, 31, 23, tzinfo=UTC),
    )
    chart = compute_natal_chart(
        datetime(1985, 3, 12, 13, 30, tzinfo=UTC),
        Decimal("45.4642"),
        Decimal("9.1900"),
        computation_config,
    )
    aspects = find_transit_aspects(chart, start, end, computation_config, split_perfections=True)
    records = find_stations(start, end, computation_config)
    stations = [r for r in records if isinstance(r, Station)]

    assert [
        (a["transiting_body"], a["natal_point"], a["aspect"]) for a in year_body["aspects"]
    ] == [(a.transiting_body, a.natal_point, a.aspect) for a in aspects]
    assert len(year_body["stations"]) == len(stations) > 0
    assert any(s["body"] == "mercury" for s in year_body["stations"])
    assert len(year_body["ingresses"]) == len(find_ingresses(chart, start, end, computation_config))
    assert [(m["kind"], m["natal_house"]) for m in year_body["lunations"]] == [
        (m.kind, m.natal_house) for m in find_lunations(chart, start, end)
    ]
    assert len(year_body["lunations"]) >= 24


def test_the_response_carries_meta_subject_and_all_five_event_lists(
    year_body: dict[str, Any],
) -> None:
    assert set(year_body) == {
        "meta",
        "subject",
        "window_utc",
        "aspects",
        "stations",
        "standing_retrogrades",
        "ingresses",
        "lunations",
    }
    assert year_body["subject"]["utc_offset"] == "+01:00"
    assert year_body["meta"]["api_version"]


def test_the_api_window_equals_the_union_of_the_local_monthly_scans(
    client: TestClient, year_body: dict[str, Any]
) -> None:
    monthly: list[dict[str, Any]] = []
    for month in range(1, 13):
        end = f"2026-{month + 1:02d}-01" if month < 12 else "2027-01-01"
        window = {"start_date": f"2026-{month:02d}-01", "end_date": end}
        monthly.append(_post(client, _request(window)).json())

    identity = {
        "stations": ("body", "direction"),
        "ingresses": ("body", "house_entered"),
        "lunations": ("kind",),
    }

    def keyed(bodies: list[dict[str, Any]], key: str, field: str) -> list[tuple[Any, ...]]:
        return sorted(
            (*(item[name] for name in identity[key]), item[field])
            for body in bodies
            for item in body[key]
        )

    for key, field in (
        ("stations", "station_at"),
        ("ingresses", "crossed_at"),
        ("lunations", "occurred_at"),
    ):
        a, b = keyed(monthly, key, field), keyed([year_body], key, field)
        assert len(a) == len(b), key
        for x, y in zip(a, b, strict=True):
            assert x[:-1] == y[:-1], key
            assert abs(_instant(x[-1]) - _instant(y[-1])) <= _TOLERANCE, (key, x, y)

    perfected_monthly = [
        _instant(a["perfected_at"])
        for body in monthly
        for a in body["aspects"]
        if a["perfected_at"]
    ]
    perfected_whole = [
        _instant(a["perfected_at"]) for a in year_body["aspects"] if a["perfected_at"]
    ]
    assert len(perfected_monthly) == len(perfected_whole)
    assert all(
        abs(x - y) <= _TOLERANCE
        for x, y in zip(sorted(perfected_monthly), sorted(perfected_whole), strict=True)
    )


def test_an_aspect_in_orb_when_the_window_opens_is_clamped_to_the_window_start(
    year_body: dict[str, Any],
) -> None:
    start = year_body["window_utc"]["start"]
    assert any(a["orb_entry_at"] == start for a in year_body["aspects"])


def test_an_aspect_still_in_orb_when_the_window_closes_has_no_exit(
    year_body: dict[str, Any],
) -> None:
    assert any(a["orb_exit_at"] is None for a in year_body["aspects"])


def test_a_body_retrograde_for_the_whole_window_is_a_clamped_standing_retrograde(
    client: TestClient,
) -> None:
    body = _post(client, _request({"start_date": "2026-09-01", "end_date": "2026-10-01"})).json()

    saturn = [r for r in body["standing_retrogrades"] if r["body"] == "saturn"]
    assert len(saturn) == 1
    assert saturn[0]["retrograde_start_utc"] == body["window_utc"]["start"]
    assert saturn[0]["retrograde_end_utc"] == body["window_utc"]["end"]


def test_exactly_thirteen_calendar_months_is_accepted(client: TestClient) -> None:
    window = {"start_date": "2026-01-31", "end_date": "2027-02-28"}

    assert _post(client, _request(window)).status_code == 200


def test_one_day_beyond_thirteen_months_is_window_too_long(client: TestClient) -> None:
    window = {"start_date": "2026-01-31", "end_date": "2027-03-01"}

    _assert_error(_post(client, _request(window)), "window_too_long", "window.end_date")


@pytest.mark.parametrize("end_date", ["2026-01-01", "2025-12-31"])
def test_an_empty_or_inverted_window_is_invalid_request(client: TestClient, end_date: str) -> None:
    window = {"start_date": "2026-01-01", "end_date": end_date}

    _assert_error(_post(client, _request(window)), "invalid_request", "window.end_date")


@pytest.mark.parametrize(
    ("window", "field"),
    [
        ({"start_date": "01/01/2026", "end_date": "2026-02-01"}, "window.start_date"),
        ({"start_date": "2026-01-01", "end_date": "2026-13-01"}, "window.end_date"),
        ({"start_date": "2026-02-30", "end_date": "2026-03-30"}, "window.start_date"),
    ],
)
def test_a_malformed_window_date_is_invalid_request_naming_the_key(
    client: TestClient, window: dict[str, str], field: str
) -> None:
    _assert_error(_post(client, _request(window)), "invalid_request", field)


def test_a_missing_window_is_invalid_request(client: TestClient) -> None:
    _assert_error(_post(client, {"subject": _subject()}), "invalid_request", "window")


def test_a_window_outside_the_ephemeris_is_ephemeris_out_of_range(client: TestClient) -> None:
    window = {"start_date": "1700-01-01", "end_date": "1700-02-01"}

    _assert_error(_post(client, _request(window)), "ephemeris_out_of_range", "window.start_date")


# --- Unknown time --------------------------------------------------------------


def test_an_unknown_time_has_no_angle_or_moon_targets_and_no_house_output(
    client: TestClient,
) -> None:
    window = {"start_date": "2026-01-01", "end_date": "2026-04-01"}

    body = _post(client, _request(window, time_known=False, birth_time=None)).json()

    assert body["subject"]["birth_instant_utc"] is None
    assert body["ingresses"] is None
    assert body["lunations"] and all(m["natal_house"] is None for m in body["lunations"])
    points = {a["natal_point"] for a in body["aspects"]}
    assert points and not points & {"ascendant", "midheaven", "moon"}
    assert body["aspects"]


def test_an_unknown_time_scan_agrees_with_the_known_time_scan_on_shared_targets(
    client: TestClient,
) -> None:
    window = {"start_date": "2026-01-01", "end_date": "2026-04-01"}

    known = _post(client, _request(window)).json()
    unknown = _post(client, _request(window, time_known=False, birth_time=None)).json()

    assert [m["occurred_at"] for m in known["lunations"]] == [
        m["occurred_at"] for m in unknown["lunations"]
    ]
    assert known["stations"] == unknown["stations"]


# --- Statelessness and determinism ---------------------------------------------


def test_a_repeat_request_returns_identical_bytes(client: TestClient) -> None:
    window = {"start_date": "2026-01-01", "end_date": "2026-03-01"}

    first = _post(client, _request(window))
    second = _post(client, _request(window))

    assert first.content == second.content


def test_the_endpoint_writes_no_row(client: TestClient, engine: Engine) -> None:
    def counts() -> dict[str, int]:
        with Session(engine) as session:
            return {
                name: session.execute(select(func.count()).select_from(table)).scalar_one()
                for name, table in SQLModel.metadata.tables.items()
            }

    before = counts()
    _post(client, _request({"start_date": "2026-01-01", "end_date": "2026-02-01"}))

    assert counts() == before


def test_the_handler_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(transits_module.transits)


def test_the_endpoint_requires_the_bearer_token(client: TestClient) -> None:
    response = client.post("/api/v1/charts/transits", json=_request())

    assert response.status_code == 401


def test_no_log_record_carries_the_subject_or_the_window(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    secrets = ["1985-03-12", "14:30", "45.4642", "9.1900", "Milano", "Caso di prova", "2026-02-01"]
    window = {"start_date": "2026-01-01", "end_date": "2026-02-01"}

    with caplog.at_level(logging.DEBUG):
        _post(client, _request(window))
        _post(client, _request(window, time_known=False, birth_time=None))
        _post(client, _request({"start_date": "2026-01-01", "end_date": "2028-01-01"}))

    assert any(record.name == "shell.http.api.access" for record in caplog.records)
    for record in caplog.records:
        rendered = record.getMessage()
        for secret in secrets:
            assert secret not in rendered, f"{record.name} leaked {secret!r}: {rendered}"
