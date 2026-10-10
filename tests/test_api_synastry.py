"""Story 11.4: ``POST /api/v1/charts/synastry``.

Reuses the real app, FK-enforcing in-memory database and bearer fixtures of the
natal endpoint tests; the computation itself is covered in
``tests/test_synastry_core.py``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlmodel import Session, SQLModel

from core.ephemeris.chart import compute_natal_chart
from core.synastry.composite import midpoint, midpoint_cusps
from core.synastry.inter_aspects import inter_aspects, known_points
from shell.http.api.places import get_api_session
from shell.http.api.router import router
from shell.http.app import computation_config, create_app
from tests._fk import fk_enforcing_engine
from tests.test_api_skeleton import BEARER, WITH_TOKEN

MILAN = {
    "latitude": "45.4642",
    "longitude": "9.1900",
    "iana_zone": "Europe/Rome",
    "display_name": "Milano, Lombardia, Italia",
}

ROME = {
    "latitude": "41.9028",
    "longitude": "12.4964",
    "iana_zone": "Europe/Rome",
    "display_name": "Roma, Lazio, Italia",
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


def _person(**overrides: Any) -> dict[str, Any]:
    person: dict[str, Any] = {
        "label": "A",
        "birth_date": "1985-03-12",
        "birth_time": "14:30",
        "time_known": True,
        "place": dict(MILAN),
    }
    person.update(overrides)
    return person


def _request(**b_overrides: Any) -> dict[str, Any]:
    b = _person(label="B", birth_date="1990-07-04", birth_time="05:15", place=dict(ROME))
    b.update(b_overrides)
    return {"subject_a": _person(), "subject_b": b}


def _post(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post("/api/v1/charts/synastry", headers=BEARER, json=body)


def test_both_known_returns_every_block(client: TestClient) -> None:
    response = _post(client, _request())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "meta", "subjects", "natal_a", "natal_b", "inter_aspects", "overlays", "composite",
    }  # fmt: skip
    assert body["meta"]["computation"]["version"] == 2
    assert body["meta"]["computation"]["orbs"]["synastry"] == "7.0"
    assert [s["label"] for s in body["subjects"]] == ["A", "B"]
    assert body["natal_a"]["ascendant"] and body["natal_b"]["houses"]
    assert body["inter_aspects"]
    assert set(body["inter_aspects"][0]) == {"body_a", "body_b", "aspect", "orb"}
    bodies = [entry["body"] for entry in body["overlays"]["a_in_b"]]
    assert bodies[0] == "sun" and "south_node" in bodies and "ascendant" not in bodies
    assert all(1 <= e["house"] <= 12 for e in body["overlays"]["b_in_a"])
    composite = body["composite"]
    assert composite["ascendant"] and composite["midheaven"] and len(composite["houses"]) == 12
    assert all(p["house"] is not None for p in composite["planets"])
    assert all(a["applying"] is None for a in composite["aspects"])


def test_the_values_equal_the_engine(client: TestClient) -> None:
    body = _post(client, _request()).json()
    chart_a = compute_natal_chart(
        datetime(1985, 3, 12, 13, 30, tzinfo=UTC), Decimal("45.4642"), Decimal("9.19"),
        computation_config,
    )  # fmt: skip
    chart_b = compute_natal_chart(
        datetime(1990, 7, 4, 3, 15, tzinfo=UTC), Decimal("41.9028"), Decimal("12.4964"),
        computation_config,
    )  # fmt: skip

    composite = body["composite"]
    assert composite["ascendant"] == str(midpoint(chart_a.ascendant, chart_b.ascendant))
    assert composite["midheaven"] == str(midpoint(chart_a.midheaven, chart_b.midheaven))
    assert [h["longitude"] for h in composite["houses"]] == [
        str(h.longitude) for h in midpoint_cusps(chart_a.houses, chart_b.houses)
    ]
    sun = next(p for p in composite["planets"] if p["name"] == "sun")
    assert sun["longitude"] == str(
        midpoint(chart_a.planets[0].longitude, chart_b.planets[0].longitude)
    )
    expected = inter_aspects(
        known_points(chart_a), known_points(chart_b), computation_config.orbs.synastry
    )
    assert [
        (i["body_a"], i["body_b"], i["aspect"], i["orb"]) for i in body["inter_aspects"]
    ] == [(i.body_a, i.body_b, i.aspect, str(i.orb)) for i in expected]


def test_one_unknown_time_nulls_only_what_needs_its_houses(client: TestClient) -> None:
    body = _post(client, _request(time_known=False, birth_time=None)).json()

    assert body["overlays"]["a_in_b"] is None
    assert body["overlays"]["b_in_a"] is not None
    sides = {(i["body_a"], i["body_b"]) for i in body["inter_aspects"]}
    assert not any(b in ("moon", "ascendant", "midheaven") for _, b in sides)
    composite = body["composite"]
    assert composite["ascendant"] is None and composite["midheaven"] is None
    assert composite["houses"] is None
    assert all(p["house"] is None for p in composite["planets"])
    assert not any("moon" in (a["body1"], a["body2"]) for a in composite["aspects"])
    assert body["natal_b"]["houses"] is None and body["natal_a"]["houses"]


def test_both_unknown(client: TestClient) -> None:
    request = _request(time_known=False, birth_time=None)
    request["subject_a"] = _person(time_known=False, birth_time=None)

    body = _post(client, request).json()

    assert body["overlays"] == {"a_in_b": None, "b_in_a": None}
    assert body["composite"]["houses"] is None and body["composite"]["ascendant"] is None
    assert not any(
        "moon" in (i["body_a"], i["body_b"]) or "ascendant" in (i["body_a"], i["body_b"])
        for i in body["inter_aspects"]
    )


def test_a_dst_gap_in_b_names_subject_b(client: TestClient) -> None:
    response = _post(client, _request(birth_date="2026-03-29", birth_time="02:30"))

    assert response.status_code == 422
    _assert_error(response, "invalid_request", "subject_b.birth_time")


def test_a_dst_gap_in_a_names_subject_a(client: TestClient) -> None:
    request = _request()
    request["subject_a"] = _person(birth_date="2026-03-29", birth_time="02:30")

    _assert_error(_post(client, request), "invalid_request", "subject_a.birth_time")


@pytest.mark.parametrize(
    ("side", "override", "field"),
    [
        ("subject_b", {"birth_date": "not-a-date"}, "subject_b.birth_date"),
        ("subject_a", {"place": {**MILAN, "latitude": "91"}}, "subject_a.place.latitude"),
        ("subject_b", {"birth_time": None}, "subject_b.birth_time"),
        ("subject_a", {"birth_date": "1700-01-01"}, "subject_a.birth_date"),
    ],
)
def test_parse_errors_name_the_subject(
    client: TestClient, side: str, override: dict[str, Any], field: str
) -> None:
    request = _request()
    request[side] = {**request[side], **override}

    response = _post(client, request)

    body = response.json()
    assert body["field"] == field, body


def test_a_missing_subject_is_invalid_request(client: TestClient) -> None:
    response = _post(client, {"subject_a": _person()})

    _assert_error(response, "invalid_request", "subject_b")


def test_a_repeat_is_byte_identical_and_writes_no_row(client: TestClient, engine: Engine) -> None:
    before = _row_counts(engine)

    first = _post(client, _request())
    second = _post(client, _request())

    assert first.content == second.content
    assert _row_counts(engine) == before


def test_it_requires_the_bearer_token(client: TestClient) -> None:
    assert client.post("/api/v1/charts/synastry", json=_request()).status_code == 401


def test_the_route_is_a_sync_handler() -> None:
    route = next(
        r for r in router.routes if isinstance(r, APIRoute) and r.path.endswith("/charts/synastry")
    )
    assert not asyncio.iscoroutinefunction(route.endpoint)


def test_the_response_is_canonical_json(client: TestClient) -> None:
    content = _post(client, _request()).content

    assert content == json.dumps(
        json.loads(content), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
