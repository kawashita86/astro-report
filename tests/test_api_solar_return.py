"""Story 11.5: ``POST /api/v1/charts/solar-return``.

Same app, FK-enforcing in-memory database and bearer fixtures as the synastry
endpoint tests; the computation itself is covered in ``tests/test_returns_core.py``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlmodel import Session, SQLModel

from shell.http.api.places import get_api_session
from shell.http.api.router import router
from shell.http.app import create_app
from tests._fk import fk_enforcing_engine
from tests.test_api_skeleton import BEARER, WITH_TOKEN

DURHAM = {
    "latitude": "36.0",
    "longitude": "-78.9",
    "iana_zone": "America/New_York",
    "display_name": "Durham, NC, US",
}
MILAN = {
    "latitude": "45.4667",
    "longitude": "9.2",
    "iana_zone": "Europe/Rome",
    "display_name": "Milano, Lombardia, Italia",
}
FORT_WORTH = {
    "latitude": "32.7358",
    "longitude": "-97.3453",
    "iana_zone": "America/Chicago",
    "display_name": "Fort Worth, TX, US",
}


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


def _row_counts(engine: Engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            name: session.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in SQLModel.metadata.tables.items()
        }


def _assert_error(response: Any, code: str, field: str | None) -> None:
    body = response.json()
    assert (body["code"], body["field"]) == (code, field), body
    assert body["message"]


def _subject(**overrides: Any) -> dict[str, Any]:
    subject: dict[str, Any] = {
        "label": "Case1",
        "birth_date": "2024-02-29",
        "birth_time": "05:12",
        "time_known": True,
        "place": dict(DURHAM),
    }
    subject.update(overrides)
    return subject


def _request(year: int = 2026, **extra: Any) -> dict[str, Any]:
    subject_overrides = extra.pop("subject", {})
    return {"subject": _subject(**subject_overrides), "year": year, **extra}


def _post(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post("/api/v1/charts/solar-return", headers=BEARER, json=body)


def test_birthplace_default_returns_every_block(client: TestClient) -> None:
    response = _post(client, _request())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "meta", "subject", "return_instant_utc", "location", "chart", "comparison",
    }  # fmt: skip
    assert body["return_instant_utc"] == "2026-02-28T21:45:38Z"
    assert body["location"] == DURHAM | {"latitude": "36.0000", "longitude": "-78.9000"}
    assert body["subject"]["chart_instant_utc"] == body["return_instant_utc"]
    assert body["subject"]["birth_instant_utc"] == "2024-02-29T10:12:00Z"
    assert len(body["chart"]["houses"]) == 12 and body["chart"]["house_rulers"]
    comparison = body["comparison"]
    assert set(comparison) == {
        "rs_ascendant_in_natal_house", "rs_planets_in_natal_houses", "rs_to_natal_aspects",
    }  # fmt: skip
    assert 1 <= comparison["rs_ascendant_in_natal_house"] <= 12
    assert set(comparison["rs_to_natal_aspects"][0]) == {"rs_body", "natal_body", "aspect", "orb"}
    assert [e["body"] for e in comparison["rs_planets_in_natal_houses"]][-1] == "south_node"


def test_relocated_keeps_the_instant_and_changes_the_angles(client: TestClient) -> None:
    home = _post(client, _request()).json()
    milan = _post(client, _request(location=MILAN)).json()

    assert milan["return_instant_utc"] == home["return_instant_utc"]
    assert milan["location"]["display_name"] == MILAN["display_name"]
    assert milan["chart"]["ascendant"] != home["chart"]["ascendant"]
    assert milan["chart"]["planets"][0]["longitude"] == home["chart"]["planets"][0]["longitude"]
    assert milan["chart"]["ascendant"] == "213.3820"  # Astro.com: Scorpio 3°22'53"


def test_a_birthday_near_new_year_falls_in_the_requested_year(client: TestClient) -> None:
    subject = {"birth_date": "2026-01-01", "birth_time": "00:00", "place": dict(FORT_WORTH)}
    body = _post(client, _request(2027, subject=subject)).json()

    assert body["return_instant_utc"] == "2027-01-01T11:50:33Z"


def test_a_leap_day_birth_in_a_common_year_is_found(client: TestClient) -> None:
    body = _post(client, _request(2025)).json()

    assert body["return_instant_utc"] == "2025-02-28T15:58:19Z"


def test_the_birth_year_returns_the_birth_instant(client: TestClient) -> None:
    subject = {"birth_date": "2026-01-01", "birth_time": "00:00", "place": dict(FORT_WORTH)}
    body = _post(client, _request(2026, subject=subject)).json()

    assert body["return_instant_utc"] == body["subject"]["birth_instant_utc"]


def test_the_return_sun_equals_the_natal_sun(client: TestClient) -> None:
    body = _post(client, _request()).json()

    assert abs(Decimal(body["chart"]["planets"][0]["longitude"]) - Decimal("340.3122")) < Decimal(
        "0.0003"
    )


def test_unknown_time_is_birth_time_required(client: TestClient) -> None:
    response = _post(client, _request(subject={"time_known": False, "birth_time": None}))

    assert response.status_code == 422
    _assert_error(response, "birth_time_required", "subject.time_known")


def test_a_year_before_the_birth_year_is_invalid(client: TestClient) -> None:
    _assert_error(_post(client, _request(2023)), "invalid_request", "year")


@pytest.mark.parametrize("year", [1700, 2400])
def test_a_year_outside_the_ephemeris_is_out_of_range(client: TestClient, year: int) -> None:
    subject = {"birth_date": "1850-06-01"} if year == 1700 else {}
    _assert_error(_post(client, _request(year, subject=subject)), "ephemeris_out_of_range", "year")


def test_a_return_beyond_the_last_covered_year_is_out_of_range(client: TestClient) -> None:
    subject = {"birth_date": "2000-12-31", "birth_time": "23:59"}

    response = _post(client, _request(2399, subject=subject))

    assert response.status_code == 422
    _assert_error(response, "ephemeris_out_of_range", "year")


def test_a_dst_gap_in_the_birth_time_names_the_subject(client: TestClient) -> None:
    subject = {"birth_date": "2026-03-29", "birth_time": "02:30", "place": dict(MILAN)}

    _assert_error(
        _post(client, _request(2027, subject=subject)), "invalid_request", "subject.birth_time"
    )


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"year": "2026"}, "year"),
        ({"year": 2026, "location": {**MILAN, "latitude": "91"}}, "location.latitude"),
        ({"year": 2026, "location": {**MILAN, "iana_zone": "Nowhere/Land"}}, "location.iana_zone"),
    ],
)
def test_parse_errors_name_the_field(client: TestClient, body: dict[str, Any], field: str) -> None:
    request = {"subject": _subject(), **body}

    _assert_error(_post(client, request), "invalid_request", field)


def test_a_repeat_is_byte_identical_and_writes_no_row(client: TestClient, engine: Engine) -> None:
    before = _row_counts(engine)

    first = _post(client, _request(location=MILAN))
    second = _post(client, _request(location=MILAN))

    assert first.content == second.content
    assert _row_counts(engine) == before


def test_it_requires_the_bearer_token(client: TestClient) -> None:
    assert client.post("/api/v1/charts/solar-return", json=_request()).status_code == 401


def test_the_route_is_a_sync_handler() -> None:
    route = next(
        r
        for r in router.routes
        if isinstance(r, APIRoute) and r.path.endswith("/charts/solar-return")
    )
    assert not asyncio.iscoroutinefunction(route.endpoint)


def test_the_response_is_canonical_json(client: TestClient) -> None:
    content = _post(client, _request()).content

    assert (
        content
        == json.dumps(
            json.loads(content), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    )
