"""The application the image actually serves.

Without these, renaming ``/healthz``, changing its status, or breaking
``create_app()`` leaves the suite green and fails at deploy instead — where the
health check is the only thing watching, and a failed health check reads as an
infrastructure problem rather than a code one.

The liveness route is the deploy's proof that migrations finished and the process
came up. It is also, from Story 1.4, the single entry in the unauthenticated
allowlist: it must stay empty of data.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.ephemeris.identity import EphemerisIdentity
from core.types.computation import ComputationConfig
from shell.config import Environment, Settings
from shell.http import app as shell_http_app
from shell.http.app import app, computation_config, create_app, ephemeris_identity
from shell.http.auth import SESSION_COOKIE_NAME, sign_session

#: Argon2 hash of "correct horse battery staple" — a fixed test password,
#: never a real one.
AUTH_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
)
AUTH_PASSWORD = "correct horse battery staple"
SESSION_SECRET_KEY = "test-session-secret-key-at-least-32-chars-long"

LOCAL = Settings(
    environment=Environment.LOCAL,
    database_url="postgresql://astro:astro@localhost:5432/astro_report",
    port=8000,
    auth_password_hash=AUTH_PASSWORD_HASH,
    session_secret_key=SESSION_SECRET_KEY,
    gemini_api_key="test-gemini-api-key",
    gemini_data_terms_verified_at="2026-01-15",
)
PRODUCTION = Settings(
    environment=Environment.PRODUCTION,
    database_url="postgresql://astro:astro@db.example.eu:5432/astro",
    port=10000,
    auth_password_hash=AUTH_PASSWORD_HASH,
    session_secret_key=SESSION_SECRET_KEY,
    gemini_api_key="test-gemini-api-key",
    gemini_data_terms_verified_at="2026-01-15",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(LOCAL))


@pytest.fixture
def authenticated_client(client: TestClient) -> TestClient:
    """A client carrying a valid, unexpired session cookie."""
    expires_at = int(time.time()) + 3600
    client.cookies.set(SESSION_COOKIE_NAME, sign_session(expires_at, LOCAL.session_secret_key))
    return client


# --- The factory --------------------------------------------------------------


def test_create_app_builds_from_explicit_settings() -> None:
    """Settings are passed in, never read here — config has one reader."""
    application = create_app(PRODUCTION)

    assert isinstance(application, FastAPI)
    assert application.state.settings is PRODUCTION


def test_debug_follows_the_environment() -> None:
    assert create_app(LOCAL).debug is True
    assert create_app(PRODUCTION).debug is False


def test_the_module_level_app_exists_for_the_server_to_import() -> None:
    """`uvicorn shell.http.app:app` is what the Dockerfile runs."""
    assert isinstance(app, FastAPI)


def test_engine_construction_enables_pre_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stale pooled connection must be detected and transparently replaced
    before use -- Neon, the managed Postgres provider (`render.yaml`), can
    suspend or drop an idle connection silently."""
    captured_kwargs: dict[str, object] = {}
    real_create_engine = shell_http_app.create_engine

    def spy_create_engine(url: str, **kwargs: object):
        captured_kwargs.update(kwargs)
        return real_create_engine(url, **kwargs)

    monkeypatch.setattr(shell_http_app, "create_engine", spy_create_engine)

    create_app(LOCAL)

    assert captured_kwargs.get("pool_pre_ping") is True


def test_dispose_is_called_once_when_the_app_is_run_as_a_lifespan_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the lifespan's shutdown path -- not app construction itself --
    disposes the engine."""
    application = create_app(LOCAL)
    engine = application.state.engine
    dispose_calls: list[None] = []
    monkeypatch.setattr(engine, "dispose", lambda: dispose_calls.append(None))

    with TestClient(application):
        assert dispose_calls == []

    assert len(dispose_calls) == 1


def test_dispose_is_never_called_without_entering_the_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Today's existing test pattern across the suite -- a bare
    `TestClient(create_app(...))` with no `with` -- never triggers ASGI
    lifespan events, so `dispose()` must never run."""
    application = create_app(LOCAL)
    engine = application.state.engine
    dispose_calls: list[None] = []
    monkeypatch.setattr(engine, "dispose", lambda: dispose_calls.append(None))

    plain_client = TestClient(application)
    plain_client.get("/healthz")

    assert dispose_calls == []


# --- Ephemeris identity: asserted at import time, before anything is served --


def test_ephemeris_identity_is_verified_and_exposed_at_import_time() -> None:
    """Importing this module is what asserts the vendored ephemeris's identity
    (Story 1.3) -- by the time `app` exists, `sepl_18.se1`/`semo_18.se1` have
    already been read, hashed and confirmed against the committed manifest."""
    assert isinstance(ephemeris_identity, EphemerisIdentity)
    assert {f.filename for f in ephemeris_identity.files} == {"sepl_18.se1", "semo_18.se1"}


# --- Computation config: loaded and exposed at import time --------------------


def test_computation_config_is_loaded_and_exposed_at_import_time() -> None:
    """Importing this module is also what loads `data/computation.toml`
    (Story 1.5) -- by the time `app` exists, the file has already been read,
    hashed and validated, exactly like `ephemeris_identity`."""
    assert isinstance(computation_config, ComputationConfig)
    assert computation_config.orbs.natal == Decimal("7.0")
    assert computation_config.orbs.transit == Decimal("2.0")
    assert computation_config.house_system.name == "placidus"


# --- Liveness -----------------------------------------------------------------


def test_healthz_reports_liveness(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 204


def test_healthz_returns_no_data(client: TestClient) -> None:
    """It is unauthenticated, so it must never carry anything worth reading."""
    response = client.get("/healthz")

    assert response.content == b""


def test_healthz_needs_no_credentials(client: TestClient) -> None:
    """Story 1.4's allowlist starts here; an anonymous request must succeed."""
    response = client.get("/healthz", headers={})

    assert response.status_code == 204


def test_healthz_answers_a_head_probe(client: TestClient) -> None:
    """Some health checkers and uptime monitors probe with `HEAD`; a
    `GET`-only route would 405 them instead of reporting the process up."""
    response = client.head("/healthz", headers={})

    assert response.status_code == 204
    assert response.content == b""


def test_healthz_with_a_trailing_slash_is_not_rejected_by_auth(client: TestClient) -> None:
    """A health checker (Render's included) or a hand-typed probe that hits
    `/healthz/` must not get the middleware's empty-body 401: the allowlist
    check tolerates a trailing slash, then Starlette redirects to the
    canonical `/healthz`. A 401 here would fail the deploy's health check."""
    response = client.get("/healthz/", headers={}, follow_redirects=False)

    assert response.status_code != 401
    response = client.get("/healthz/", headers={})
    assert response.status_code == 204


# --- Nothing else is exposed without authentication ---------------------------


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/"])
def test_anonymous_requests_to_anything_outside_the_allowlist_are_uniformly_401(
    client: TestClient, path: str
) -> None:
    """Every surface is authenticated from Story 1.4. An anonymous caller gets
    the same empty-body 401 whether the path is a real, protected route or does
    not exist at all -- the middleware runs ahead of routing, so it never
    leaks which case this is."""
    response = client.get(path)

    assert response.status_code == 401
    assert response.content == b""


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/"])
def test_authenticated_requests_still_get_fastapis_own_404_for_unknown_paths(
    authenticated_client: TestClient, path: str
) -> None:
    """Past the auth checkpoint, an unknown path is just an unknown path:
    `/docs`/`/redoc`/`/openapi.json` were never registered (`docs_url=None`
    etc.) and `/` has no route either."""
    assert authenticated_client.get(path).status_code == 404


# --- Sign-in --------------------------------------------------------------------


def test_login_form_is_served_without_credentials(client: TestClient) -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert b"password" in response.content.lower()


def test_login_form_needs_no_credentials_because_login_is_allowlisted(
    client: TestClient,
) -> None:
    """`/login` is in `shell.http.auth.ALLOWLIST`; an anonymous GET succeeds."""
    assert client.get("/login").status_code == 200


def test_correct_password_sets_the_session_cookie(client: TestClient) -> None:
    response = client.post("/login", data={"password": AUTH_PASSWORD})

    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies


def test_wrong_password_sets_no_cookie(client: TestClient) -> None:
    response = client.post("/login", data={"password": "wrong password"})

    assert SESSION_COOKIE_NAME not in response.cookies


def test_wrong_password_is_a_uniform_failure_response(client: TestClient) -> None:
    response = client.post("/login", data={"password": "wrong password"})

    assert response.status_code == 401


def test_a_non_utf8_login_body_fails_cleanly_rather_than_crashing(client: TestClient) -> None:
    response = client.post(
        "/login",
        content=b"password=\xff\xfe",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies


def test_an_oversized_login_body_fails_cleanly_rather_than_reaching_argon2(
    client: TestClient,
) -> None:
    """The one endpoint reachable without a session must not spend Argon2's
    64 MiB-per-verify cost on an arbitrarily large garbage body."""
    huge_password = "x" * 100_000
    response = client.post("/login", data={"password": huge_password})

    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies


def test_a_login_post_missing_the_password_field_fails_cleanly(client: TestClient) -> None:
    response = client.post(
        "/login",
        content=b"not_password=whatever",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies


def test_the_session_cookie_is_http_only_and_same_site_lax(client: TestClient) -> None:
    response = client.post("/login", data={"password": AUTH_PASSWORD})

    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def test_the_session_cookie_is_secure_only_in_production() -> None:
    local = TestClient(create_app(LOCAL)).post("/login", data={"password": AUTH_PASSWORD})
    production = TestClient(create_app(PRODUCTION)).post(
        "/login", data={"password": AUTH_PASSWORD}
    )

    assert "Secure" not in local.headers["set-cookie"]
    assert "Secure" in production.headers["set-cookie"]


def test_a_session_from_signing_in_authenticates_later_requests(client: TestClient) -> None:
    """A cookie earned by posting the real password behaves like the
    hand-signed one `authenticated_client` uses: it clears the auth
    checkpoint and lets an unknown path reach FastAPI's own routing."""
    login = client.post("/login", data={"password": AUTH_PASSWORD})
    assert SESSION_COOKIE_NAME in login.cookies

    assert client.get("/").status_code == 404
