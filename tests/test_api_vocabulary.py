"""Story 11.6: ``GET /api/v1/vocabulary/it`` -- the Italian words, served from
the one shared module the operator UI also reads.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from core.gate.run import body_sign_label
from core.payload.freeze import canonical_json_bytes
from shell.http.api import vocabulary as vocabulary_module
from shell.http.api.router import router
from shell.http.app import create_app, gate_vocabulary
from shell.http.stage_view import _format_entry_value
from shell.vocabulary import ASPECT_LABELS_IT, BODY_IDS, DIRECTION_LABELS_IT, SIGN_IDS
from tests.test_api_skeleton import BEARER, WITH_TOKEN, WITHOUT_TOKEN

URL = "/api/v1/vocabulary/it"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(WITH_TOKEN))


def test_a_valid_bearer_gets_the_vocabulary(client: TestClient) -> None:
    response = client.get(URL, headers=BEARER)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == {
        "vocabulary_version",
        "content_hash",
        "gate",
        "bodies",
        "signs",
        "aspects",
        "directions",
    }
    assert "meta" not in body
    assert body["vocabulary_version"] == gate_vocabulary.version
    assert body["content_hash"] == gate_vocabulary.content_hash
    gate = body["gate"]
    assert set(gate["planets"]) == gate_vocabulary.planets
    assert set(gate["signs"]) == gate_vocabulary.signs
    assert set(gate["casa_ordinals"]) == gate_vocabulary.casa_ordinals
    assert (gate["retrogrado"], gate["stazionario"]) == (
        gate_vocabulary.retrogrado,
        gate_vocabulary.stazionario,
    )


def test_ids_are_the_glossary_ids_and_labels_are_the_operator_ui_italian(
    client: TestClient,
) -> None:
    body = client.get(URL, headers=BEARER).json()

    assert set(body["bodies"]) == {
        "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus",
        "neptune", "pluto", "true_node", "south_node", "ascendant", "midheaven",
    }  # fmt: skip
    assert set(body["signs"]) == set(SIGN_IDS) and len(SIGN_IDS) == 12
    assert set(body["aspects"]) == {"conjunction", "sextile", "square", "trine", "opposition"}
    assert set(body["directions"]) == {"retrograde", "direct"}
    for body_id in BODY_IDS:
        assert body["bodies"][body_id] == body_sign_label(body_id) != body_id
    for sign_id in SIGN_IDS:
        assert body["signs"][sign_id] == body_sign_label(sign_id) != sign_id
    assert body["bodies"]["sun"] == "Sole"
    assert body["bodies"]["true_node"] == "Nodo Nord"
    assert body["aspects"]["square"] == "Quadratura"
    assert body["directions"]["retrograde"] == "Retrogrado"


def test_every_planet_and_sign_gate_word_has_a_label(client: TestClient) -> None:
    body = client.get(URL, headers=BEARER).json()

    labels = {label.lower() for label in body["bodies"].values()}
    assert set(body["gate"]["planets"]) <= labels
    assert set(body["gate"]["signs"]) == {label.lower() for label in body["signs"].values()}


def test_the_operator_ui_renders_the_same_aspect_and_direction_strings() -> None:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Rome")
    for aspect, label in ASPECT_LABELS_IT.items():
        assert _format_entry_value("aspect", aspect, zone) == label
    for direction, label in DIRECTION_LABELS_IT.items():
        assert _format_entry_value("direction", direction, zone) == label
    assert ASPECT_LABELS_IT["square"] == "Quadratura"
    assert DIRECTION_LABELS_IT == {"retrograde": "Retrogrado", "direct": "Diretto"}


def test_a_repeat_is_byte_identical_and_canonical(client: TestClient) -> None:
    first = client.get(URL, headers=BEARER).content
    second = client.get(URL, headers=BEARER).content

    assert first == second
    assert first == canonical_json_bytes(json.loads(first))


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong-token"}, {"Authorization": "Basic x"}]
)
def test_a_missing_or_wrong_bearer_is_a_json_401(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get(URL, headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_without_a_configured_token_every_call_is_401() -> None:
    response = TestClient(create_app(WITHOUT_TOKEN)).get(URL, headers=BEARER)

    assert response.status_code == 401


def test_the_route_is_a_sync_handler() -> None:
    route = next(
        r for r in router.routes if isinstance(r, APIRoute) and r.path.endswith("/vocabulary/it")
    )
    assert route.endpoint is vocabulary_module.italian_vocabulary
    assert not asyncio.iscoroutinefunction(route.endpoint)


def test_aspect_labels_cover_every_aspect_the_engine_can_assign() -> None:
    from core.ephemeris.chart import _ASPECTS

    assert set(ASPECT_LABELS_IT) == {name for name, _ in _ASPECTS}
