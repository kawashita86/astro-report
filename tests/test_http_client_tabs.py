"""Story 9.3 — the shared client-scoped contextual-tab header.

Each of ``/clients/{id}/edit`` (Anagrafica), ``/clients/{id}/chart`` (Tema) and
``/clients/{id}/reports`` (Report) now renders one shared ``_client_tabs.html``
partial in its ``page_header`` block: a breadcrumb ``Clienti / {nome}`` and a
``<nav>`` of three real-link tabs. This walks the story's "Client-scoped screen
render" I/O matrix row across all three routes -- the breadcrumb, the three tab
targets, the single ``aria-current="page"`` tracking the route, and the sidebar
``Clienti`` item being ``is-active`` at the same time (breadcrumb and sidebar
agree).

The stored chart is populated by real ``compute_natal_chart()`` +
``create_client_with_chart()`` (mirrors ``tests/test_http_chart_wheel.py``) so
the ``/chart`` route renders a real SVG rather than a hand-built one.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import Client, create_client_with_chart
from shell.computation import load_computation_config
from shell.config import Environment, Settings
from shell.http.app import create_app, get_session
from shell.http.auth import SESSION_COOKIE_NAME, sign_session

AUTH_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
)
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

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)

_CLIENT_NAME = "Ada Lovelace"

#: (route suffix, the tab that must be active on it, that tab's own href suffix).
_ROUTES = (
    ("/edit", "anagrafica", "/edit"),
    ("/chart", "tema", "/chart"),
    ("/reports", "report", "/reports"),
)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def app_instance() -> FastAPI:
    return create_app(LOCAL)


@pytest.fixture
def client(app_instance: FastAPI, db_session: Session) -> TestClient:
    app_instance.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app_instance)


@pytest.fixture
def authenticated_client(client: TestClient) -> TestClient:
    expires_at = int(time.time()) + 3600
    client.cookies.set(SESSION_COOKIE_NAME, sign_session(expires_at, LOCAL.session_secret_key))
    return client


def _seed_client_with_chart(session: Session) -> Client:
    client_row = create_client_with_chart(
        session,
        name=_CLIENT_NAME,
        birth_date=date(2026, 1, 1),
        birth_time=dt_time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=compute_natal_chart(
            _BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG
        ),
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    session.commit()
    return client_row


def _tab_nav(body: str) -> str:
    match = re.search(r'<nav class="client-tabs".*?</nav>', body, re.S)
    assert match is not None, "the client-tabs <nav> is not rendered"
    return match.group(0)


@pytest.mark.parametrize(("suffix", "active_tab", "active_href_suffix"), _ROUTES)
def test_a_client_scoped_screen_carries_the_shared_tab_header(
    authenticated_client: TestClient,
    db_session: Session,
    suffix: str,
    active_tab: str,
    active_href_suffix: str,
) -> None:
    seeded = _seed_client_with_chart(db_session)

    response = authenticated_client.get(f"/clients/{seeded.id}{suffix}")

    assert response.status_code == 200, response.text
    body = response.text

    # Breadcrumb: `Clienti` links to /clients, then the client's name.
    assert f'<a href="/clients">Clienti</a> / {_CLIENT_NAME}' in body

    nav = _tab_nav(body)
    assert 'aria-label="Sezioni del cliente"' in nav

    # All three tabs are present as real links to their own routes.
    for tab_suffix in ("/edit", "/chart", "/reports"):
        assert f'href="/clients/{seeded.id}{tab_suffix}"' in nav

    # Exactly one tab carries aria-current="page", and it is this route's tab.
    current = re.findall(r'href="([^"]+)"[^>]*aria-current="page"', nav, re.S)
    assert current == [f"/clients/{seeded.id}{active_href_suffix}"], current
    assert nav.count('aria-current="page"') == 1

    # The active tab also carries the is-active class.
    assert re.search(
        rf'href="/clients/{seeded.id}{re.escape(active_href_suffix)}"[^>]*class="is-active"',
        nav,
        re.S,
    ), f"the {active_tab} tab is not marked is-active"

    # The sidebar Clienti item is simultaneously active — breadcrumb and
    # sidebar agree.
    assert re.search(
        r'href="/clients"[^>]*\bclass="is-active"[^>]*aria-current="page"', body, re.S
    ), "the sidebar Clienti item is not marked active"

    # Still exactly one document and one h1.
    assert body.lower().count("<html") == 1
    assert body.count("<h1") == 1
