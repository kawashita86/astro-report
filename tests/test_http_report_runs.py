"""``POST /clients/{client_id}/report-runs`` and ``GET /report-runs/{run_id}``
-- Story 3.5's own I/O & Edge-Case Matrix rows, exercised end-to-end through
the real app/session wiring, mirroring ``tests/test_http_clients.py``.

The Client and its Natal Chart are created with a real ``compute_natal_chart()``
call (this route never calls it itself -- it only reads the already-stored
chart back via ``deserialize_natal_chart``). ``drive()`` itself is faked
(the ``fake_drive`` fixture) for tests that reach it: Starlette's
``TestClient`` runs the ASGI app on its own worker thread, and pyswisseph's
``set_ephe_path()`` pins the vendored ephemeris per-thread, so a real
``drive()`` call touching ``core/transits/*`` from that thread needs its own
``verify_ephemeris_identity()`` call -- out of scope here, mirroring
``tests/test_http_clients.py``'s own real-vs-fake boundary. Real stage
behavior is ``tests/test_runner_driver.py``'s job; these tests only prove
the routes' own orchestration -- auth, 404s, the redirect, the HTMX
fragment/full-page split.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as time_of_day
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import Client, create_client_with_chart
from shell.adapters.postgres.report_run import ReportRun
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
)

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_client_store.py/tests/test_http_clients.py use.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)


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


@pytest.fixture
def fake_drive(monkeypatch: pytest.MonkeyPatch):
    """Stand in for a real ``drive()`` call, mirroring
    ``tests/test_http_clients.py``'s own real-vs-fake boundary
    (``fake_chart_computation``): Starlette's ``TestClient`` runs the ASGI app
    on its own worker thread, and pyswisseph's ``set_ephe_path()`` pins the
    vendored ephemeris per-thread -- a real ``drive()`` call reaching
    ``core/transits/*`` from that thread would need its own
    ``verify_ephemeris_identity()`` call, out of scope for a
    route-orchestration test. Real stage-advancement behavior (both real
    registered stages, real backoff, real month resolution) is
    ``tests/test_runner_driver.py``'s job; these HTTP tests only need to
    prove the routes call ``drive()``, persist whatever it returns, and
    render/redirect correctly around it.
    """
    import shell.http.routes.report_runs as report_runs_module

    def _fake_drive(session, run, *, natal_chart, config, ephemeris_identity, sections_config):
        if run.stage is None:
            run.month_start_utc = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
            run.month_end_utc = datetime(2026, 2, 1, 6, 0, 0, tzinfo=UTC)
            run.stage = "natal_ready"
            session.add(run)
            session.commit()
        if run.stage == "natal_ready":
            run.transit_events = []
            run.stage = "transits_ready"
            session.add(run)
            session.commit()
        return run

    monkeypatch.setattr(report_runs_module, "drive", _fake_drive)
    return _fake_drive


def _create_client_with_real_chart(db_session: Session, *, name: str = "Ada Lovelace") -> Client:
    natal_chart = compute_natal_chart(
        _BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG
    )
    client_row = create_client_with_chart(
        db_session,
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=time_of_day(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=natal_chart,
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    db_session.commit()
    return client_row


def _report_runs(db_session: Session) -> list[ReportRun]:
    return list(db_session.exec(select(ReportRun)))


# --- Authentication -------------------------------------------------------------


def test_anonymous_post_is_rejected(client: TestClient, db_session: Session) -> None:
    ada = _create_client_with_real_chart(db_session)

    response = client.post(f"/clients/{ada.id}/report-runs", data={"month": "2026-01"})

    assert response.status_code == 401


def test_anonymous_get_is_rejected(client: TestClient, db_session: Session) -> None:
    response = client.get("/report-runs/01a01abf-0000-7000-8000-000000000000")

    assert response.status_code == 401


# --- Happy path -------------------------------------------------------------------


def test_starting_a_run_creates_it_drives_it_and_redirects_to_the_poll_view(
    authenticated_client: TestClient, db_session: Session, fake_drive
) -> None:
    ada = _create_client_with_real_chart(db_session)

    response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )

    assert response.status_code == 303
    runs = _report_runs(db_session)
    assert len(runs) == 1
    run = runs[0]
    assert response.headers["location"] == f"/report-runs/{run.id}"
    # Both registered stages are local-only (Design Notes) so a real drive()
    # call inside this same request already finishes them.
    assert run.stage == "transits_ready"
    assert run.month_start_utc == datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
    assert run.transit_events is not None


def test_the_poll_view_shows_the_current_stage(
    authenticated_client: TestClient, db_session: Session, fake_drive
) -> None:
    ada = _create_client_with_real_chart(db_session)
    start_response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )
    location = start_response.headers["location"]

    response = authenticated_client.get(location)

    assert response.status_code == 200
    assert "transits_ready" in response.text


def test_polling_an_already_completed_run_is_a_noop_and_still_shows_its_stage(
    authenticated_client: TestClient, db_session: Session, fake_drive
) -> None:
    ada = _create_client_with_real_chart(db_session)
    start_response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )
    location = start_response.headers["location"]

    first_poll = authenticated_client.get(location)
    second_poll = authenticated_client.get(location)

    assert first_poll.status_code == 200
    assert second_poll.status_code == 200
    assert "transits_ready" in second_poll.text
    runs = _report_runs(db_session)
    assert len(runs) == 1


def test_an_htmx_poll_request_gets_a_fragment_without_the_full_page_shell(
    authenticated_client: TestClient, db_session: Session, fake_drive
) -> None:
    ada = _create_client_with_real_chart(db_session)
    start_response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )
    location = start_response.headers["location"]

    full_page = authenticated_client.get(location)
    fragment = authenticated_client.get(location, headers={"HX-Request": "true"})

    assert "<html" in full_page.text.lower()
    assert "<html" not in fragment.text.lower()
    assert "transits_ready" in fragment.text


# --- Error paths -------------------------------------------------------------------


def test_starting_a_run_for_an_unknown_client_is_404(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/clients/01a01abf-0000-7000-8000-000000000000/report-runs", data={"month": "2026-01"}
    )

    assert response.status_code == 404


def test_polling_an_unknown_run_is_404(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/report-runs/01a01abf-0000-7000-8000-000000000000")

    assert response.status_code == 404


@pytest.mark.parametrize("month", ["not-a-month", "2026-13", "2026-1", "2026", ""])
def test_a_malformed_month_is_422(
    authenticated_client: TestClient, db_session: Session, month: str
) -> None:
    ada = _create_client_with_real_chart(db_session)

    response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": month}
    )

    assert response.status_code == 422
    assert _report_runs(db_session) == []


def test_starting_a_run_for_a_client_with_no_stored_chart_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    client_row = Client(
        name="No Chart Yet",
        birth_date=date(2026, 1, 1),
        birth_time=time_of_day(0, 0),
        latitude=_LATITUDE,
        longitude=_LONGITUDE,
        iana_zone="America/Chicago",
    )
    db_session.add(client_row)
    db_session.commit()

    response = authenticated_client.post(
        f"/clients/{client_row.id}/report-runs", data={"month": "2026-01"}
    )

    assert response.status_code == 404
