"""Story 11.2: ``POST /api/v1/places/resolve`` and ``POST /api/v1/charts/natal``.

The app is the real one, built through ``create_app``; only the session (an
FK-enforcing in-memory SQLite shared across the TestClient's worker threads)
and the geocoder (a recording fake) are substituted.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlmodel import Session, SQLModel

from core.domains.rulers import resolve_house_rulers
from core.ephemeris.chart import compute_natal_chart
from shell.adapters.nominatim.geocoder import NominatimGeocoder
from shell.adapters.postgres.place_cache import PlaceCache
from shell.http.api.places import get_api_session, get_place_geocoder
from shell.http.app import computation_config, create_app
from tests._fk import fk_enforcing_engine
from tests.conformance.runner import compare, load_fixture
from tests.test_api_skeleton import BEARER, WITH_TOKEN

MILAN = {
    "latitude": "45.4642",
    "longitude": "9.1900",
    "iana_zone": "Europe/Rome",
    "display_name": "Milano, Lombardia, Italia",
}


def _subject(**overrides: Any) -> dict[str, Any]:
    subject: dict[str, Any] = {
        "label": "Caso di prova",
        "birth_date": "1985-03-12",
        "birth_time": "14:30",
        "time_known": True,
        "place": dict(MILAN),
    }
    subject.update(overrides)
    return {"subject": subject}


@dataclass
class _Location:
    address: str
    latitude: float
    longitude: float


class _Geolocator:
    def __init__(self, results: list[_Location] | None) -> None:
        self.results = results
        self.calls: list[str] = []

    def geocode(self, query: str, exactly_one: bool) -> list[_Location] | None:
        self.calls.append(query)
        return self.results


class _Zones:
    def timezone_at(self, *, lat: float, lng: float) -> str | None:
        return "Europe/Rome"


@pytest.fixture
def engine() -> Engine:
    return fk_enforcing_engine(shared_across_threads=True)


@pytest.fixture
def geolocator() -> _Geolocator:
    return _Geolocator([_Location("Milano, Lombardia, Italia", 45.46427, 9.18951)])


@pytest.fixture
def client(engine: Engine, geolocator: _Geolocator) -> Iterator[TestClient]:
    application: FastAPI = create_app(WITH_TOKEN)

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    def _geocoder(session: Session = Depends(get_api_session)) -> NominatimGeocoder:
        return NominatimGeocoder(session, geolocator=geolocator, timezone_finder=_Zones())

    application.dependency_overrides[get_api_session] = _session
    application.dependency_overrides[get_place_geocoder] = _geocoder
    yield TestClient(application, raise_server_exceptions=False)


def _row_counts(engine: Engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            name: session.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in SQLModel.metadata.tables.items()
        }


def _natal(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post("/api/v1/charts/natal", headers=BEARER, json=body)


def _assert_error(response: Any, code: str, field: str | None) -> None:
    body = response.json()
    assert (body["code"], body["field"]) == (code, field), body
    assert body["message"]


# --- Charts: known time --------------------------------------------------------


def test_a_known_time_chart_equals_the_engine_field_for_field(client: TestClient) -> None:
    response = _natal(client, _subject())

    assert response.status_code == 200
    body = response.json()
    instant = datetime(1985, 3, 12, 13, 30, tzinfo=UTC)
    expected = compute_natal_chart(
        instant, Decimal("45.4642"), Decimal("9.1900"), computation_config
    )
    chart = body["chart"]
    assert chart["ascendant"] == str(expected.ascendant)
    assert chart["midheaven"] == str(expected.midheaven)
    assert [
        (p["name"], p["longitude"], p["sign"], p["degree"], p["house"], p["retrograde"])
        for p in chart["planets"]
    ] == [
        (p.name, str(p.longitude), p.sign, str(p.degree), p.house, p.retrograde)
        for p in expected.planets
    ]
    assert [(h["number"], h["longitude"]) for h in chart["houses"]] == [
        (h.number, str(h.longitude)) for h in expected.houses
    ]
    assert [
        (a["body1"], a["body2"], a["aspect"], a["orb"], a["applying"]) for a in chart["aspects"]
    ] == [(a.body1, a.body2, a.aspect, str(a.orb), a.applying) for a in expected.aspects]
    assert [
        (r["house"], r["sign"], r["traditional_ruler"], r["modern_ruler"], r["co_ruler"])
        for r in chart["house_rulers"]
    ] == [
        (r.house, r.sign, r.traditional_ruler, r.modern_ruler, r.co_ruler)
        for r in resolve_house_rulers(expected, computation_config)
    ]


def test_the_subject_echoes_the_instant_offset_and_quantized_place(client: TestClient) -> None:
    body = _natal(client, _subject(place={**MILAN, "latitude": "45.464212345"})).json()

    assert body["subject"]["birth_instant_utc"] == "1985-03-12T13:30:00Z"
    assert body["subject"]["chart_instant_utc"] == "1985-03-12T13:30:00Z"
    assert body["subject"]["utc_offset"] == "+01:00"
    assert body["subject"]["place"]["latitude"] == "45.4642"
    assert body["subject"]["birth_time"] == "14:30:00"
    assert body["meta"]["api_version"] == "1"
    assert body["meta"]["computation"]["content_hash"] == computation_config.content_hash


def test_the_response_matches_the_astro_com_natal_fixture(client: TestClient) -> None:
    from tests.conformance.runner import FIXTURES_DIR

    fixture = load_fixture(FIXTURES_DIR / "near-midnight-birth.toml")
    data = fixture.birth_data
    subject = _subject(
        birth_date=data["date"],
        birth_time=data["time"][:5],
        place={
            "latitude": data["latitude"],
            "longitude": data["longitude"],
            "iana_zone": data["timezone"],
            "display_name": data["place"],
        },
    )

    chart = _natal(client, subject).json()["chart"]

    shaped = {
        "planets": [
            {"name": p["name"], "longitude": p["longitude"], "retrograde": p["retrograde"]}
            for p in chart["planets"]
            if p["name"] != "south_node"
        ],
        "houses": [
            {"number": h["number"], "cusp_longitude": h["longitude"]} for h in chart["houses"]
        ],
        "aspects": [
            {k: a[k] for k in ("body1", "body2", "aspect", "orb")} for a in chart["aspects"]
        ],
    }
    assert compare(fixture.name, fixture.expected, shaped) == []


def test_a_repeat_request_returns_identical_bytes(client: TestClient) -> None:
    first = _natal(client, _subject())
    second = _natal(client, _subject())

    assert first.content == second.content


# --- Charts: unknown time ------------------------------------------------------


def test_an_unknown_time_chart_is_the_noon_chart_without_angles_or_houses(
    client: TestClient,
) -> None:
    body = _natal(client, _subject(time_known=False, birth_time=None)).json()

    assert body["subject"]["birth_instant_utc"] is None
    assert body["subject"]["birth_time"] is None
    assert body["subject"]["chart_instant_utc"] == "1985-03-12T11:00:00Z"
    chart = body["chart"]
    assert chart["ascendant"] is None and chart["midheaven"] is None
    assert chart["houses"] is None and chart["house_rulers"] is None
    for planet in chart["planets"]:
        assert planet["house"] is None
        assert set(planet["range"]) == {"from", "to"}
        assert isinstance(planet["sign_uncertain"], bool)
    assert all("moon" not in (a["body1"], a["body2"]) for a in chart["aspects"])
    assert chart["aspects"], "the day should still have non-Moon aspects"


def test_an_unknown_time_ignores_a_supplied_birth_time(client: TestClient) -> None:
    with_time = _natal(client, _subject(time_known=False)).json()["chart"]
    without = _natal(client, _subject(time_known=False, birth_time=None)).json()["chart"]

    assert with_time == without


def test_a_sun_ingress_day_flags_the_sun_sign_uncertain(client: TestClient) -> None:
    body = _natal(
        client, _subject(time_known=False, birth_time=None, birth_date="2024-03-20")
    ).json()

    sun = next(p for p in body["chart"]["planets"] if p["name"] == "sun")
    assert sun["sign_uncertain"] is True


def test_a_moon_ingress_day_has_a_range_spanning_two_signs(client: TestClient) -> None:
    flagged = []
    for day in range(1, 8):
        body = _natal(
            client,
            _subject(time_known=False, birth_time=None, birth_date=f"2024-03-{day:02d}"),
        ).json()
        moon = next(p for p in body["chart"]["planets"] if p["name"] == "moon")
        flagged.append(moon["sign_uncertain"])
        if moon["sign_uncertain"]:
            assert moon["range"]["from"] != moon["range"]["to"]

    assert any(flagged), "the Moon changes sign roughly every 2.5 days"
    assert not all(flagged)


# --- Charts: errors ------------------------------------------------------------


@pytest.mark.parametrize(
    ("date_", "time_"),
    [("2026-03-29", "02:30"), ("2026-10-25", "02:30")],
    ids=["dst-gap", "dst-fold"],
)
def test_a_dst_gap_or_fold_is_invalid_request_on_birth_time(
    client: TestClient, date_: str, time_: str
) -> None:
    response = _natal(client, _subject(birth_date=date_, birth_time=time_))

    assert response.status_code == 422
    _assert_error(response, "invalid_request", "subject.birth_time")


def test_a_known_time_without_a_time_is_invalid_request(client: TestClient) -> None:
    _assert_error(
        _natal(client, _subject(birth_time=None)), "invalid_request", "subject.birth_time"
    )


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"place": {**MILAN, "iana_zone": "Mars/Olympus"}}, "subject.place.iana_zone"),
        ({"place": {**MILAN, "latitude": "91"}}, "subject.place.latitude"),
        ({"place": {**MILAN, "longitude": "-181"}}, "subject.place.longitude"),
        ({"birth_date": "1985-13-40"}, "subject.birth_date"),
        ({"birth_time": "25:00"}, "subject.birth_time"),
        ({"time_known": "yes"}, "subject.time_known"),
    ],
)
def test_malformed_subject_fields_are_invalid_request_naming_the_key(
    client: TestClient, override: dict[str, Any], field: str
) -> None:
    response = _natal(client, _subject(**override))

    assert response.status_code == 422
    _assert_error(response, "invalid_request", field)


def test_a_year_outside_the_ephemeris_is_ephemeris_out_of_range(client: TestClient) -> None:
    for year in ("1700", "2500"):
        response = _natal(client, _subject(birth_date=f"{year}-06-15"))

        assert response.status_code == 422
        _assert_error(response, "ephemeris_out_of_range", "subject.birth_date")


@pytest.mark.parametrize("birth_date", ["1801-01-01", "2399-12-31"])
def test_the_edges_of_the_supported_span_compute(client: TestClient, birth_date: str) -> None:
    for known in (True, False):
        response = _natal(
            client, _subject(birth_date=birth_date, birth_time="12:00", time_known=known)
        )

        assert response.status_code == 200, response.text


def test_the_endpoints_require_the_bearer_token(client: TestClient) -> None:
    for path in ("/api/v1/charts/natal", "/api/v1/places/resolve"):
        response = client.post(path, json={})

        assert response.status_code == 401


# --- Places --------------------------------------------------------------------


def _resolve(client: TestClient, query: str = "Milano") -> Any:
    return client.post("/api/v1/places/resolve", headers=BEARER, json={"query": query})


def test_an_unambiguous_place_is_listed_with_its_zone_and_cached(
    client: TestClient, engine: Engine
) -> None:
    response = _resolve(client)

    assert response.status_code == 200
    assert response.json() == {
        "candidates": [
            {
                "display_name": "Milano, Lombardia, Italia",
                "iana_zone": "Europe/Rome",
                "latitude": "45.4643",
                "longitude": "9.1895",
            }
        ]
    }
    assert _row_counts(engine)["place_cache"] == 1


def test_a_repeat_of_a_cached_query_gives_the_same_bytes_without_the_geocoder(
    client: TestClient, geolocator: _Geolocator
) -> None:
    first = _resolve(client)
    second = _resolve(client, "  MILANO ")

    assert first.content == second.content
    assert len(geolocator.calls) == 1


def test_an_ambiguous_place_lists_every_candidate_and_caches_nothing(
    client: TestClient, engine: Engine, geolocator: _Geolocator
) -> None:
    geolocator.results = [
        _Location("Venezia, Veneto, Italia", 45.4371, 12.3326),
        _Location("Venezia, Calabria, Italia", 38.0, 16.0),
    ]

    response = _resolve(client, "Venezia")

    assert response.status_code == 200
    candidates = response.json()["candidates"]
    assert [c["display_name"] for c in candidates] == [
        "Venezia, Veneto, Italia",
        "Venezia, Calabria, Italia",
    ]
    assert all(c["iana_zone"] == "Europe/Rome" for c in candidates)
    assert _row_counts(engine)["place_cache"] == 0
    _resolve(client, "Venezia")
    assert len(geolocator.calls) == 2, "today only an unambiguous match is cached (AD-16)"


@pytest.mark.parametrize("results", [None, []])
def test_an_unmatched_query_is_place_unresolved(
    client: TestClient, geolocator: _Geolocator, results: list[_Location] | None
) -> None:
    geolocator.results = results

    response = _resolve(client, "Zzzzzz")

    assert response.status_code == 422
    _assert_error(response, "place_unresolved", None)


@pytest.mark.parametrize("query", ["", "   ", "x" * 201])
def test_an_empty_or_oversized_query_is_invalid_request(client: TestClient, query: str) -> None:
    _assert_error(_resolve(client, query), "invalid_request", "query")


def test_a_resolved_place_round_trips_into_a_subject(client: TestClient) -> None:
    [candidate] = _resolve(client).json()["candidates"]

    response = _natal(client, _subject(place=candidate))

    assert response.status_code == 200


# --- Statelessness and logging -------------------------------------------------


def test_only_place_cache_ever_grows_and_a_natal_request_grows_nothing(
    client: TestClient, engine: Engine
) -> None:
    empty = _row_counts(engine)
    assert not any(empty.values())

    _natal(client, _subject())
    _natal(client, _subject(time_known=False, birth_time=None))
    _natal(client, _subject(birth_date="2026-03-29", birth_time="02:30"))
    assert _row_counts(engine) == empty

    _resolve(client)
    after_resolve = _row_counts(engine)
    assert {name for name, n in after_resolve.items() if n} == {"place_cache"}
    assert after_resolve["place_cache"] == 1
    assert PlaceCache.__tablename__ in after_resolve


def test_no_log_record_carries_the_query_birth_data_or_coordinates(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    secrets = ["1985-03-12", "14:30", "45.4642", "9.1900", "Milano", "Caso di prova", "Zzzzzz"]

    with caplog.at_level(logging.DEBUG):
        _natal(client, _subject())
        _natal(client, _subject(time_known=False, birth_time=None))
        _natal(client, _subject(birth_date="2026-03-29", birth_time="02:30"))
        _natal(client, _subject(birth_date="1700-01-01"))
        _resolve(client)
        _resolve(client, "Zzzzzz")

    assert any(record.name == "shell.http.api.access" for record in caplog.records)
    for record in caplog.records:
        rendered = record.getMessage()
        for secret in secrets:
            assert secret not in rendered, f"{record.name} leaked {secret!r}: {rendered}"
