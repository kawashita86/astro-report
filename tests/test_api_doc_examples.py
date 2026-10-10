"""Story 11.6: every example response in ``docs/api/chart-data-v1.md`` is the
byte-exact answer the running API gives to the request printed above it.

The plugin team writes against that document, so an example that has drifted
from the code is worse than none. The test rebuilds each example in-process
(places through a fake geocoder, so no network) and compares both the request
block and the response block with what is committed; the guard is a plain
function so a negative test can prove it fails on a hand edit.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from shell.adapters.nominatim.geocoder import NominatimGeocoder
from shell.http.api.places import get_api_session, get_place_geocoder
from shell.http.app import create_app
from tests._fk import fk_enforcing_engine
from tests.test_api_natal import _Geolocator, _Location, _Zones
from tests.test_api_skeleton import BEARER, WITH_TOKEN

DOC_FILE = Path(__file__).resolve().parent.parent / "docs" / "api" / "chart-data-v1.md"

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


def _person(
    label: str, birth_date: str, birth_time: str | None, place: dict[str, str]
) -> dict[str, Any]:
    return {
        "label": label,
        "birth_date": birth_date,
        "birth_time": birth_time,
        "time_known": birth_time is not None,
        "place": dict(place),
    }


#: name -> (method, path, request body or None). The pinned requests; changing
#: one changes the document and is a deliberate act.
EXAMPLES: dict[str, tuple[str, str, dict[str, Any] | None]] = {
    "places-resolve": ("POST", "/api/v1/places/resolve", {"query": "Milano"}),
    "natal": (
        "POST",
        "/api/v1/charts/natal",
        {"subject": _person("Caso di prova", "1985-03-12", "14:30", MILAN)},
    ),
    "natal-time-unknown": (
        "POST",
        "/api/v1/charts/natal",
        {"subject": _person("Caso di prova", "1985-03-12", None, MILAN)},
    ),
    "transits": (
        "POST",
        "/api/v1/charts/transits",
        {
            "subject": _person("Caso di prova", "1985-03-12", "14:30", MILAN),
            "window": {"start_date": "2026-01-01", "end_date": "2026-02-01"},
        },
    ),
    "synastry": (
        "POST",
        "/api/v1/charts/synastry",
        {
            "subject_a": _person("A", "1985-03-12", "14:30", MILAN),
            "subject_b": _person("B", "1990-07-04", "05:15", ROME),
        },
    ),
    "synastry-one-time-unknown": (
        "POST",
        "/api/v1/charts/synastry",
        {
            "subject_a": _person("A", "1985-03-12", None, MILAN),
            "subject_b": _person("B", "1990-07-04", "05:15", ROME),
        },
    ),
    "solar-return": (
        "POST",
        "/api/v1/charts/solar-return",
        {"subject": _person("Caso di prova", "1985-03-12", "14:30", MILAN), "year": 2026},
    ),
    "vocabulary": ("GET", "/api/v1/vocabulary/it", None),
}

_EXAMPLE_PATTERN = re.compile(r"<!-- example:([a-z0-9-]+) -->(.*?)<!-- /example -->", re.DOTALL)
_JSON_BLOCK_PATTERN = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def pretty(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def generate_examples() -> dict[str, list[str]]:
    """name -> the JSON blocks the document must hold for it, in order:
    the pretty request (if any) then the byte-exact response."""
    engine: Engine = fk_enforcing_engine(shared_across_threads=True)
    geolocator = _Geolocator([_Location("Milano, Lombardia, Italia", 45.46427, 9.18951)])
    application: FastAPI = create_app(WITH_TOKEN)

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    def _geocoder(session: Session = Depends(get_api_session)) -> NominatimGeocoder:
        return NominatimGeocoder(session, geolocator=geolocator, timezone_finder=_Zones())

    application.dependency_overrides[get_api_session] = _session
    application.dependency_overrides[get_place_geocoder] = _geocoder
    client = TestClient(application)
    blocks: dict[str, list[str]] = {}
    for name, (method, path, body) in EXAMPLES.items():
        response = client.request(method, path, headers=BEARER, json=body)
        assert response.status_code == 200, (name, response.text)
        entry = [] if body is None else [pretty(body)]
        entry.append(response.content.decode("utf-8"))
        blocks[name] = entry
    return blocks


def documented_examples(doc: str) -> dict[str, list[str]]:
    return {
        match.group(1): _JSON_BLOCK_PATTERN.findall(match.group(2))
        for match in _EXAMPLE_PATTERN.finditer(doc)
    }


def render_example(name: str, blocks: list[str]) -> str:
    """One example as the document prints it."""
    method, path, body = EXAMPLES[name]
    parts = [f"<!-- example:{name} -->", f"`{method} {path}`", ""]
    if body is not None:
        parts += ["Request:", "", f"```json\n{blocks[0]}\n```", ""]
    parts += ["Response:", "", f"```json\n{blocks[-1]}\n```", "<!-- /example -->"]
    return "\n".join(parts)


def rewrite_examples(doc: str, generated: dict[str, list[str]]) -> str:
    """``doc`` with every example region replaced by its regenerated form."""
    return _EXAMPLE_PATTERN.sub(
        lambda match: render_example(match.group(1), generated[match.group(1)]), doc
    )


def find_drift(doc: str, generated: dict[str, list[str]]) -> list[str]:
    """Every way the document's examples differ from the regenerated ones."""
    documented = documented_examples(doc)
    problems = [
        f"{name}: missing from the document" for name in generated if name not in documented
    ]
    problems += [f"{name}: not a known example" for name in documented if name not in generated]
    for name, expected in generated.items():
        if name in documented and documented[name] != expected:
            problems.append(f"{name}: differs from the regenerated request/response")
    return problems


@pytest.fixture(scope="module")
def generated() -> dict[str, list[str]]:
    return generate_examples()


def test_api_doc_examples(generated: dict[str, list[str]]) -> None:
    assert find_drift(DOC_FILE.read_text(encoding="utf-8"), generated) == []


def test_every_api_route_has_a_documented_example() -> None:
    from fastapi.routing import APIRoute

    from shell.http.api.router import router

    routed = {
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    exampled = {(method, path) for method, path, _ in EXAMPLES.values()}
    assert routed <= exampled, sorted(routed - exampled)
    assert {"natal-time-unknown", "synastry-one-time-unknown"} <= set(EXAMPLES)


def test_the_guard_detects_a_hand_edited_response(generated: dict[str, list[str]]) -> None:
    name = "vocabulary"
    original = generated[name][-1]
    doc = f"<!-- example:{name} -->\n```json\n{original}\n```\n<!-- /example -->"
    doc_edited = doc.replace('"sun":"Sole"', '"sun":"Sol"')
    assert doc_edited != doc
    assert find_drift(doc, {name: generated[name]}) == []
    assert find_drift(doc_edited, {name: generated[name]}) == [
        "vocabulary: differs from the regenerated request/response"
    ]


def test_the_guard_detects_a_missing_or_unknown_example(generated: dict[str, list[str]]) -> None:
    one = {"vocabulary": generated["vocabulary"]}
    assert find_drift("", one) == ["vocabulary: missing from the document"]
    stray = "<!-- example:invented -->\n```json\n{}\n```\n<!-- /example -->"
    assert find_drift(stray, {}) == ["invented: not a known example"]


@pytest.mark.skipif(
    os.environ.get("REGENERATE_API_DOC") != "1",
    reason="maintainer action: REGENERATE_API_DOC=1 rewrites the examples in the document",
)
def test_regenerate_the_document_examples(generated: dict[str, list[str]]) -> None:
    doc = DOC_FILE.read_text(encoding="utf-8")
    DOC_FILE.write_text(rewrite_examples(doc, generated), encoding="utf-8")
