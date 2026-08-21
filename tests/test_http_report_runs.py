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
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.payload import Payload, SectionPayload
from core.types.place import ResolvedPlace
from core.types.transits import Station, TransitAspectEvent
from shell.adapters.postgres.client import Client, create_client_with_chart
from shell.adapters.postgres.report_payload import store_report_payload
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from shell.config import Environment, Settings
from shell.http.app import create_app, get_session
from shell.http.auth import SESSION_COOKIE_NAME, sign_session
from shell.sections import load_sections_config

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
_SECTIONS_CONFIG = load_sections_config()

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


def _empty_section() -> SectionPayload:
    return SectionPayload(
        profile=None, aspects=(), stations=(), standing_retrogrades=(), ingresses=(), lunations=()
    )


def _a_frozen_payload_with_one_aspect() -> dict:
    """One `amore` Aspect with a known, easy-to-check UTC window, plus one
    entry in each day-list -- enough to prove the route localizes an instant
    and renders every one of the eight groupings that actually carry data,
    without needing a full realistic computation. Every other Section/
    per-field grouping (e.g. `amore`'s own `stations`) stays empty, so the
    same fixture also proves an empty grouping's heading is not rendered."""
    event = TransitAspectEvent(
        transiting_body="mars",
        natal_point="venus",
        aspect="trine",
        perfected_at=datetime(2026, 1, 10, 15, 0, 0, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 8, 12, 0, 0, tzinfo=UTC),
        orb_exit_at=datetime(2026, 1, 12, 12, 0, 0, tzinfo=UTC),
    )
    station = Station(
        body="mars",
        direction="retrograde",
        station_at=datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC),
        longitude=Decimal("10.0"),
    )
    amore_section = SectionPayload(
        profile=None,
        aspects=(event,),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    payload = Payload(
        energia_generale=_empty_section(),
        amore=amore_section,
        lavoro=_empty_section(),
        denaro=_empty_section(),
        benessere=_empty_section(),
        consiglio_finale=_empty_section(),
    )
    return freeze_payload(
        payload,
        DayLists(giorni_favorevoli=(event,), giorni_di_attenzione=(station,)),
        config=_COMPUTATION_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


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


# --- Story 3.9: GET /report-runs/{run_id}/payload ---------------------------------


def test_getting_the_payload_without_a_session_is_401(client: TestClient) -> None:
    response = client.get("/report-runs/01a01abf-0000-7000-8000-000000000000/payload")

    assert response.status_code == 401


def test_getting_the_payload_for_an_unknown_run_is_404(authenticated_client: TestClient) -> None:
    """Matrix row: "Unknown run_id" -- no matching ReportRun -> 404."""
    response = authenticated_client.get(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/payload"
    )

    assert response.status_code == 404


def test_getting_the_payload_for_a_run_with_no_stored_payload_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "No ReportPayload for run_id" -- run hasn't reached
    ``payload_ready`` -> 404."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/payload")

    assert response.status_code == 404


def test_getting_the_payload_shows_all_eight_groupings_localized_to_the_clients_zone(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/payload")

    assert response.status_code == 200
    for name in (
        "energia_generale",
        "amore",
        "lavoro",
        "denaro",
        "benessere",
        "consiglio_finale",
        "giorni_favorevoli",
        "giorni_di_attenzione",
    ):
        assert name in response.text
    # ada's client.iana_zone is America/Chicago (UTC-6 in January):
    # 2026-01-08 12:00 UTC (orb_entry_at) -> 06:00 local.
    assert "2026-01-08 06:00:00 CST" in response.text
    # `id` is omitted from a rendered event entry.
    event_id = frozen["sections"]["amore"]["aspects"][0]["id"]
    assert event_id not in response.text


def test_getting_the_payload_hides_empty_groupings(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """`_a_frozen_payload_with_one_aspect()` only populates `amore.aspects`
    plus both day-lists -- every other per-field grouping (`amore.stations`
    included) stays an empty tuple and must not render a heading for it, so
    the page does not dominate the reader with empty categories most months
    will have plenty of."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01")
    db_session.add(run)
    db_session.commit()
    store_report_payload(db_session, run=run, frozen=_a_frozen_payload_with_one_aspect())
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/payload")

    assert response.status_code == 200
    assert "<h3>aspects</h3>" in response.text
    for empty_field_heading in (
        "<h3>stations</h3>",
        "<h3>standing_retrogrades</h3>",
        "<h3>ingresses</h3>",
        "<h3>lunations</h3>",
        "<h3>profile</h3>",
    ):
        assert empty_field_heading not in response.text


def test_the_poll_view_links_to_the_payload_once_it_is_ready(
    authenticated_client: TestClient, db_session: Session, fake_drive
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="payload_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/payload"' in response.text


def test_the_poll_view_has_no_payload_link_before_payload_ready(
    authenticated_client: TestClient, db_session: Session, fake_drive
) -> None:
    ada = _create_client_with_real_chart(db_session)
    start_response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )
    location = start_response.headers["location"]

    response = authenticated_client.get(location)

    assert "View Payload" not in response.text
