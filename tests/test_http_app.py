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

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shell.config import Environment, Settings
from shell.http.app import app, create_app

LOCAL = Settings(
    environment=Environment.LOCAL,
    database_url="postgresql://astro:astro@localhost:5432/astro_report",
    port=8000,
)
PRODUCTION = Settings(
    environment=Environment.PRODUCTION,
    database_url="postgresql://astro:astro@db.example.eu:5432/astro",
    port=10000,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(LOCAL))


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


# --- Nothing else is exposed --------------------------------------------------


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_no_schema_or_docs_surface(client: TestClient, path: str) -> None:
    """Every surface is authenticated from Story 1.4; a schema endpoint is not."""
    assert client.get(path).status_code == 404


def test_unknown_routes_are_not_found(client: TestClient) -> None:
    assert client.get("/").status_code == 404
