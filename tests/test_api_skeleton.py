"""Story 11.1: the chart data API skeleton -- bearer auth, the JSON error
envelope, the meta block, and the guarantee that no request body is logged.

The authenticated path is exercised through a probe router included on a built
app, so the skeleton ships no placeholder endpoint of its own.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Iterable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.responses import Response

from core.errors import PlaceResolutionError
from shell.config import Environment, Settings
from shell.http.api.errors import ApiError, ErrorCode, map_exception
from shell.http.api.meta import build_meta, ephemeris_manifest_sha256
from shell.http.app import app as real_app
from shell.http.app import computation_config, create_app, ephemeris_identity
from shell.http.auth import SESSION_COOKIE_NAME, sign_session

SESSION_SECRET_KEY = "test-session-secret-key-at-least-32-chars-long"
AUTH_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
)
#: Argon2 hash of API_TOKEN -- a fixed test token, never a real one.
API_TOKEN = "local-dev-api-token"
API_TOKEN_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$VrXPOGTsyRR6gTi2ciHDSg$"
    "DCHkO83XEwz0r0nTomWVmAYST+0g8aZyL14GwMqf0tU"
)

WITH_TOKEN = Settings(
    environment=Environment.LOCAL,
    database_url="postgresql://astro:astro@localhost:5432/astro_report",
    port=8000,
    auth_password_hash=AUTH_PASSWORD_HASH,
    session_secret_key=SESSION_SECRET_KEY,
    gemini_api_key="test-gemini-api-key",
    gemini_data_terms_verified_at="2026-01-15",
    api_token_hash=API_TOKEN_HASH,
)
WITHOUT_TOKEN = dataclasses.replace(WITH_TOKEN, api_token_hash=None)

BEARER = {"Authorization": f"Bearer {API_TOKEN}"}


class _Echo(BaseModel):
    value: int


def _app(settings: Settings) -> FastAPI:
    """A built app with a probe route on ``/api/v1`` standing in for a real endpoint."""
    application = create_app(settings)

    @application.get("/api/v1/_probe")
    def probe() -> dict[str, str]:
        return {"ok": "yes"}

    @application.post("/api/v1/_echo")
    def echo(body: _Echo) -> dict[str, int]:
        return {"value": body.value}

    @application.get("/api/v1/_place_unresolved")
    def place_unresolved() -> None:
        raise PlaceResolutionError("geocoding", "nothing found")

    @application.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return application


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(WITH_TOKEN), raise_server_exceptions=False)


def _assert_envelope(response: Response, code: str) -> dict[str, Any]:
    body = response.json()
    assert set(body) == {"code", "message", "field"}
    assert body["code"] == code
    assert body["message"]
    return body


# --- Authentication -----------------------------------------------------------


def test_a_valid_token_reaches_the_route(client: TestClient) -> None:
    response = client.get("/api/v1/_probe", headers=BEARER)

    assert response.status_code == 200
    assert response.json() == {"ok": "yes"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": f"Basic {API_TOKEN}"},
        {"Authorization": "Bearer"},
        {"Authorization": f"Token {API_TOKEN}"},
        {"Authorization": "Bearer "},
    ],
)
def test_a_missing_wrong_or_non_bearer_header_is_a_json_401(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/_probe", headers=headers, follow_redirects=False)

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/json"
    body = _assert_envelope(response, "unauthorized")
    assert body["field"] is None


def test_a_session_cookie_alone_does_not_open_the_api(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, sign_session(2**40, SESSION_SECRET_KEY))

    response = client.get("/api/v1/_probe", follow_redirects=False)

    assert response.status_code == 401
    _assert_envelope(response, "unauthorized")


def test_the_bearer_scheme_is_case_insensitive(client: TestClient) -> None:
    response = client.get("/api/v1/_probe", headers={"Authorization": f"bearer {API_TOKEN}"})

    assert response.status_code == 200


def test_a_401_names_the_bearer_scheme(client: TestClient) -> None:
    assert client.get("/api/v1/_probe").headers["www-authenticate"] == "Bearer"


def test_a_valid_token_on_an_html_route_is_ignored(client: TestClient) -> None:
    browser = client.get(
        "/clients", headers=BEARER | {"Accept": "text/html"}, follow_redirects=False
    )
    plain = client.get("/clients", headers=BEARER, follow_redirects=False)

    assert browser.status_code == 302
    assert browser.headers["location"].startswith("/login")
    assert plain.status_code == 401
    assert plain.content == b""


def test_an_unset_token_hash_closes_the_whole_api() -> None:
    closed = TestClient(_app(WITHOUT_TOKEN), raise_server_exceptions=False)

    for headers in (BEARER, {}):
        response = closed.get("/api/v1/_probe", headers=headers)
        assert response.status_code == 401
        _assert_envelope(response, "unauthorized")


# --- The error envelope --------------------------------------------------------


def test_an_unknown_api_path_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/v1/nope", headers=BEARER)

    assert response.status_code == 404
    _assert_envelope(response, "invalid_request")


def test_body_validation_is_invalid_request_naming_the_field(client: TestClient) -> None:
    response = client.post("/api/v1/_echo", headers=BEARER, json={"value": "x"})

    assert response.status_code == 422
    body = _assert_envelope(response, "invalid_request")
    assert body["field"] == "value"


def test_a_typed_core_error_is_mapped_to_its_code(client: TestClient) -> None:
    response = client.get("/api/v1/_place_unresolved", headers=BEARER)

    _assert_envelope(response, "place_unresolved")


def test_an_unhandled_exception_is_internal_error_without_its_detail(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/_boom", headers=BEARER)

    assert response.status_code == 500
    _assert_envelope(response, "internal_error")
    assert "secret internal detail" not in response.text


def test_every_error_code_has_a_status_and_an_italian_message() -> None:
    from shell.http.api.errors import error_response

    assert {code.value for code in ErrorCode} == {
        "invalid_request",
        "birth_time_required",
        "place_unresolved",
        "window_too_long",
        "ephemeris_out_of_range",
        "unauthorized",
        "internal_error",
    }
    for code in ErrorCode:
        response = error_response(code, "subject.birth_time")
        body = json.loads(response.body)
        assert body == {
            "code": code.value,
            "message": body["message"],
            "field": "subject.birth_time",
        }
        assert body["message"].endswith(".")


def test_map_exception_maps_api_errors_and_falls_back_to_internal() -> None:
    assert map_exception(ApiError(ErrorCode.WINDOW_TOO_LONG, "window")) == (
        ErrorCode.WINDOW_TOO_LONG,
        "window",
    )
    assert map_exception(ValueError("x")) == (ErrorCode.INTERNAL_ERROR, None)


def test_an_anonymous_html_miss_is_still_the_bare_401() -> None:
    html_client = TestClient(_app(WITH_TOKEN))

    missing = html_client.get("/definitely-not-a-route", follow_redirects=False)

    # Unauthenticated, so the auth middleware answers before routing -- unchanged.
    assert missing.status_code == 401
    assert missing.content == b""


# --- Docs exposure -------------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/openapi.json", "/docs", "/redoc", "/api/docs", "/api/openapi.json"]
)
def test_no_docs_or_schema_page_lists_the_api(client: TestClient, path: str) -> None:
    response = client.get(path, headers=BEARER)

    assert response.status_code in {401, 404}
    assert "/api/v1" not in response.text


def test_the_real_app_has_no_openapi_schema() -> None:
    assert real_app.openapi_url is None


# --- The meta block ------------------------------------------------------------


def test_meta_carries_the_configuration_and_ephemeris_identity() -> None:
    meta = build_meta(computation_config, ephemeris_identity)

    assert meta["api_version"] == "1"
    assert meta["zodiac"] == "tropical"
    assert meta["computation"] == {
        "version": computation_config.version,
        "content_hash": computation_config.content_hash,
        "house_system": "placidus",
        "orbs": {
            "natal": str(computation_config.orbs.natal),
            "transit": str(computation_config.orbs.transit),
        },
    }
    assert len(meta["ephemeris"]["manifest_sha256"]) == 64


def test_the_manifest_hash_is_stable_and_order_independent() -> None:
    reversed_identity = dataclasses.replace(
        ephemeris_identity, files=tuple(reversed(ephemeris_identity.files))
    )

    assert ephemeris_manifest_sha256(ephemeris_identity) == ephemeris_manifest_sha256(
        reversed_identity
    )
    assert build_meta(computation_config, ephemeris_identity) == build_meta(
        computation_config, ephemeris_identity
    )


def test_a_changed_ephemeris_file_changes_the_manifest_hash() -> None:
    first, *rest = ephemeris_identity.files
    altered = dataclasses.replace(
        ephemeris_identity,
        files=(dataclasses.replace(first, sha256="0" * 64), *rest),
    )

    assert ephemeris_manifest_sha256(altered) != ephemeris_manifest_sha256(ephemeris_identity)


# --- The logging guard ---------------------------------------------------------

#: Everything a subject request carries that must never reach a log record.
_SUBJECT = {
    "birth_date": "1985-03-12",
    "birth_time": "14:30",
    "latitude": "45.4642",
    "longitude": "9.1900",
    "display_name": "Milano, Lombardia, Italia",
}


def _assert_no_subject_data_in_logs(records: Iterable[logging.LogRecord]) -> None:
    """Fail if any record's rendered message mentions a value from ``_SUBJECT``."""
    for record in records:
        rendered = record.getMessage()
        for value in _SUBJECT.values():
            assert value not in rendered, f"log record leaked {value!r}: {rendered}"


def test_no_request_body_or_birth_data_reaches_any_log_record(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        client.post("/api/v1/_echo", headers=BEARER, json={"value": 1, "subject": _SUBJECT})
        client.post("/api/v1/_echo", headers={}, json={"value": 1, "subject": _SUBJECT})
        client.post("/api/v1/_echo", headers=BEARER, json={"value": "x", "subject": _SUBJECT})

    assert any(record.name == "shell.http.api.access" for record in caplog.records)
    _assert_no_subject_data_in_logs(caplog.records)


def test_the_access_line_carries_method_path_status_duration_and_version(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="shell.http.api.access"):
        client.get("/api/v1/_probe", headers=BEARER)

    [record] = [r for r in caplog.records if r.name == "shell.http.api.access"]
    message = record.getMessage()
    assert "GET" in message and "/api/v1/_probe" in message and "200" in message
    assert " ms" in message
    assert f"v{computation_config.version}" in message


def test_the_guard_detects_a_logged_request_body(caplog: pytest.LogCaptureFixture) -> None:
    """Negative test: the guard above must fail when a handler logs a body."""
    leaky = logging.getLogger("leaky.handler")

    with caplog.at_level(logging.INFO):
        leaky.info("received %s", json.dumps(_SUBJECT))

    with pytest.raises(AssertionError, match="leaked"):
        _assert_no_subject_data_in_logs(caplog.records)
