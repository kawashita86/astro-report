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
from dataclasses import replace
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
from core.gate.run import run_gate
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.gate import GateViolation
from core.types.generation import GeneratedDraft, Sentence
from core.types.payload import Payload, SectionPayload
from core.types.place import ResolvedPlace
from core.types.transits import Station, TransitAspectEvent
from shell.adapters.gemini.generator import GeminiGenerator
from shell.adapters.local.generator import RecordedResponseGenerator
from shell.adapters.postgres.client import Client, create_client_with_chart
from shell.adapters.postgres.gate_result import store_gate_result
from shell.adapters.postgres.report_draft import store_report_draft
from shell.adapters.postgres.report_payload import store_report_payload
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from shell.config import Environment, Settings
from shell.gate import DEFAULT_VOCABULARY_PATH, load_gate_vocabulary
from shell.http.app import create_app, get_session
from shell.http.auth import SESSION_COOKIE_NAME, sign_session
from shell.http.routes.report_runs import get_generator
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

PRODUCTION = Settings(
    environment=Environment.PRODUCTION,
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
def fake_drive(app_instance: FastAPI, monkeypatch: pytest.MonkeyPatch):
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

    ``get_generator`` is also overridden with a fake, never a real
    ``GeminiGenerator`` -- mirrors ``tests/test_http_clients.py``'s own
    ``get_geocoder`` override: ``_fake_drive`` never actually calls the
    ``generator`` it receives, so nothing here needs a working one, only
    something structurally accepted where a ``Generator`` is expected.
    """
    import shell.http.routes.report_runs as report_runs_module

    def _fake_drive(
        session,
        run,
        *,
        natal_chart,
        config,
        ephemeris_identity,
        sections_config,
        generator,
        vocabulary,
    ):
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
    app_instance.dependency_overrides[get_generator] = lambda: object()
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


# --- Story 4.6: GET /report-runs/{run_id}/draft ------------------------------------


def _a_generated_draft_for(frozen: dict) -> GeneratedDraft:
    """A ``GeneratedDraft`` citing ``frozen``'s own ``giorni_favorevoli``
    entry -- ``frozen`` comes from ``_a_frozen_payload_with_one_aspect()``,
    so the entry id is real and content-hashed, not made up."""
    fav_entry_id = frozen["day_lists"]["giorni_favorevoli"][0]["id"]
    return GeneratedDraft(
        energia_generale=(Sentence(text="Un mese equilibrato.", entry_ids=()),),
        amore=(Sentence(text="Venere sostiene i legami.", entry_ids=(fav_entry_id,)),),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(Sentence(text="Ottimo per gli incontri.", entry_ids=(fav_entry_id,)),),
        giorni_di_attenzione=(),
        consiglio_finale=(Sentence(text="Respira.", entry_ids=()),),
    )


def test_getting_the_draft_without_a_session_is_401(client: TestClient) -> None:
    response = client.get("/report-runs/01a01abf-0000-7000-8000-000000000000/draft")

    assert response.status_code == 401


def test_getting_the_draft_for_an_unknown_run_is_404(authenticated_client: TestClient) -> None:
    response = authenticated_client.get(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/draft"
    )

    assert response.status_code == 404


def test_getting_the_draft_for_a_run_with_no_stored_draft_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row (mirrors ``view_report_payload``'s own): the run exists but
    hasn't reached ``draft_ready`` yet -> 404."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 404


def test_getting_the_draft_renders_prose_and_list_sections_localized_to_the_clients_zone(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    store_report_draft(
        db_session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=draft,
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 200
    assert "Un mese equilibrato." in response.text
    assert "Venere sostiene i legami." in response.text
    assert "Ottimo per gli incontri." in response.text
    # ada's client.iana_zone is America/Chicago (UTC-6 in January):
    # 2026-01-10 15:00 UTC (perfected_at) -> 09:00 local.
    assert "2026-01-10 09:00:00 CST" in response.text


def test_getting_the_draft_shows_the_latest_attempt_when_more_than_one_exists(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O & Edge-Case Matrix row 5, "Reading the draft mid-regeneration"
    (Story 5.4): more than one ``ReportDraft`` row can exist for a run once
    it has regenerated at least once -- the route must render the latest
    (highest-``attempt``) row, never an arbitrary or the first one."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    store_report_draft(
        db_session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=_a_generated_draft_for(frozen),
        attempt=0,
    )
    second_draft = GeneratedDraft(
        energia_generale=(Sentence(text="Un mese di ripartenza.", entry_ids=()),),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(),
    )
    store_report_draft(
        db_session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=second_draft,
        attempt=1,
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 200
    assert "Un mese di ripartenza." in response.text
    assert "Un mese equilibrato." not in response.text


def test_the_poll_view_links_to_the_draft_once_it_is_ready(
    authenticated_client: TestClient, db_session: Session, fake_drive
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="draft_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/draft"' in response.text


def test_the_poll_view_has_no_draft_link_before_draft_ready(
    authenticated_client: TestClient, db_session: Session, fake_drive
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="payload_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert "View Draft" not in response.text


class _StubAppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


class _StubApp:
    def __init__(self, settings: Settings) -> None:
        self.state = _StubAppState(settings)


class _StubRequest:
    """The one attribute path ``get_generator`` reads off a real ``Request``
    (``request.app.state.settings``) -- a real ``Request`` cannot be built
    without an ASGI scope, and this dependency needs nothing else from one."""

    def __init__(self, settings: Settings) -> None:
        self.app = _StubApp(settings)


def test_get_generator_builds_a_real_gemini_generator_from_the_apps_configured_key() -> None:
    """``fake_drive`` (used by every other test here) overrides ``get_generator``
    with a fake, so nothing else in this module exercises the real dependency
    itself -- this proves ``get_generator`` wires ``request.app.state.settings
    .gemini_api_key`` into a real ``GeminiGenerator`` under ``Environment
    .PRODUCTION``, mirroring how ``get_geocoder`` is exercised directly in
    ``tests/test_http_clients.py`` (Story 4.9: ``LOCAL`` now returns
    ``RecordedResponseGenerator`` instead, see the test below).
    """
    generator = get_generator(_StubRequest(PRODUCTION))  # type: ignore[arg-type]

    assert isinstance(generator, GeminiGenerator)


def test_get_generator_returns_the_recorded_response_generator_under_local() -> None:
    """Story 4.9: local development runs generation against recorded
    responses, not the live provider, so ``docker compose up`` never spends
    real Gemini quota."""
    generator = get_generator(_StubRequest(LOCAL))  # type: ignore[arg-type]

    assert isinstance(generator, RecordedResponseGenerator)


# --- Story 4.8: a terminally failed run ---------------------------------------------


def _a_failed_run(client_id) -> ReportRun:
    """A ``ReportRun`` already marked terminally failed at ``draft_ready``
    (Story 4.8) -- ``drive()`` short-circuits on ``failed_at`` before ever
    touching the Generator, so no ``fake_drive``/real Gemini call is needed
    for either test below."""
    return ReportRun(
        client_id=client_id,
        month="2026-01",
        stage="payload_ready",
        failed_at=datetime(2026, 1, 20, 12, 0, 0, tzinfo=UTC),
        failure_reason="stage 'draft_ready' failed 5 consecutive times: simulated rate limit",
    )


def test_a_failed_runs_poll_fragment_shows_the_reason_with_no_hx_trigger(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O & Edge-Case Matrix: "Polling a failed run" -- the poll fragment
    shows the reason, without ``hx-trigger``, so Francesco sees why without
    the page polling forever."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_failed_run(ada.id)
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert "simulated rate limit" in response.text
    assert "hx-trigger" not in response.text


def test_the_draft_view_for_a_failed_run_still_404s(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O & Edge-Case Matrix: "Draft view for a failed run" -- no
    ``ReportDraft`` row exists for a failed run (no partial, exportable
    Report), so ``GET /report-runs/{id}/draft`` still 404s."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_failed_run(ada.id)
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 404


# --- Story 5.5: seeing exactly what failed and what it contradicts ------------------


def _a_bound_exhausted_run(client_id) -> ReportRun:
    """A ``ReportRun`` in Story 5.4's exact regeneration-bound-exhausted
    terminal state: ``stage`` stays ``"draft_ready"`` (never rewound back,
    unlike a run mid-regeneration), ``failed_at``/``failure_reason`` are set,
    and (unlike ``_a_failed_run``, Story 4.8's generic stage-failure shape)
    a ``ReportDraft`` row for this run does exist -- mirrors
    ``shell/runner/driver.py``'s ``except GateFailedError`` branch once
    ``regeneration_count`` exceeds ``_MAX_REGENERATIONS``."""
    return ReportRun(
        client_id=client_id,
        month="2026-01",
        stage="draft_ready",
        regeneration_count=4,
        failed_at=datetime(2026, 1, 20, 12, 0, 0, tzinfo=UTC),
        failure_reason="regeneration bound exhausted after 4 attempts: "
        "Refusing to advance past the Groundedness Gate: 1 violation(s) against the Payload.",
    )


def test_getting_the_draft_for_a_bound_exhausted_run_shows_gate_violations_and_failure_reason(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """AC1: Francesco opens the draft view of a Report that exhausted its
    regeneration bound and sees the Report text, each failing Claim's
    section/sentence/detail, and the run's failure reason -- the violations
    are read from the persisted ``StoredGateResult`` row that actually
    recorded this run's failure (Story 5.6), not recomputed against the
    currently loaded vocabulary (epic-5-retro-item-38)."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_bound_exhausted_run(ada.id)
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    # "marte" is a closed-vocabulary planet token (Story 5.1), so this
    # sentence is a Claim (Story 5.2's `is_claim()`); citing nothing at all
    # is an unconditional "empty_citation" violation, regardless of what it
    # asserts -- the simplest, deterministic way to force a real
    # `run_gate()` failure without depending on the Payload's own contents.
    ungrounded_draft = GeneratedDraft(
        energia_generale=(Sentence(text="Marte è retrogrado.", entry_ids=()),),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(),
    )
    store_report_draft(
        db_session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=ungrounded_draft,
        attempt=3,
    )
    # The real Gate check that actually failed this run (mirrors
    # `shell/runner/driver.py`'s own `except GateFailedError` write, and
    # `tests/test_runner_driver.py:60,68`'s own vocabulary loading) --
    # `store_gate_result` is what Story 5.6 built and this story wires up.
    vocabulary = load_gate_vocabulary(DEFAULT_VOCABULARY_PATH)
    gate_result = run_gate(ungrounded_draft, frozen, vocabulary)
    store_gate_result(
        db_session,
        run=run,
        passed=gate_result.passed,
        regeneration_count=run.regeneration_count,
        vocabulary_version=gate_result.vocabulary_version,
        violations=gate_result.violations,
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 200
    assert "Marte è retrogrado." in response.text
    assert "empty_citation" in response.text
    assert "energia_generale" in response.text
    assert "sentence is a Claim" in response.text
    assert run.failure_reason in response.text


def test_getting_the_draft_for_a_run_with_multiple_gate_results_shows_only_the_latest(
    authenticated_client: TestClient, db_session: Session, app_instance: FastAPI
) -> None:
    """I/O & Edge-Case Matrix row 4: more than one ``StoredGateResult`` row
    can exist for a run once it has regenerated more than once (Story 5.4) --
    the row with the highest ``regeneration_count`` is always the one that
    actually caused the terminal failure, so it is the one shown, even when
    the currently loaded vocabulary (``request.app.state.gate_vocabulary``)
    has since diverged from every stored row. This is exactly the drift
    epic-5-retro-item-38 closes: the response must not depend on the live
    vocabulary at all.

    Rows are inserted out of ``regeneration_count`` order (3, then 0, then
    1) -- ``StoredGateResult.id`` is a time-sortable ``uuid7``, so inserting
    in ascending ``regeneration_count`` order would let a query that merely
    orders by insertion/id order pass this test too. Inserting out of order
    means only a query that actually orders by ``regeneration_count``
    descending can pick the right row. ``regeneration_count=3`` (not 2) is
    used for the row that caused the failure: ``_a_bound_exhausted_run()``
    sets ``run.regeneration_count = 4`` and ``shell/runner/driver.py``'s
    ``_MAX_REGENERATIONS`` is 3, so the check that actually pushed the count
    past the bound ran at the pre-increment value of 3, matching how
    ``drive()``'s ``except GateFailedError`` block calls ``store_gate_result``
    before incrementing ``run.regeneration_count``.

    Also proves ``report_run_id`` isolation: a second ``ReportRun`` gets its
    own ``StoredGateResult`` row with distinguishable violation text, and
    that text must never appear in the first run's draft view -- a
    regression that weakened or dropped the ``report_run_id`` filter would
    still pass every other test here, since they only ever seed rows for
    the one run under test."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_bound_exhausted_run(ada.id)
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    store_report_draft(
        db_session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=draft,
        attempt=3,
    )
    for count in (3, 0, 1):
        store_gate_result(
            db_session,
            run=run,
            passed=False,
            regeneration_count=count,
            vocabulary_version=1,
            violations=(
                GateViolation(
                    kind="empty_citation",
                    section="lavoro",
                    sentence=f"regeneration {count} sentence",
                    entry_ids=(),
                    detail=f"detail for regeneration {count}",
                ),
            ),
        )
    other_client = _create_client_with_real_chart(db_session, name="Grace Hopper")
    other_run = _a_bound_exhausted_run(other_client.id)
    db_session.add(other_run)
    db_session.commit()
    other_frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=other_run, frozen=other_frozen)
    store_report_draft(
        db_session,
        run=other_run,
        style_guide_version=1,
        sections_config_version=other_frozen["sections_config_version"],
        draft=_a_generated_draft_for(other_frozen),
        attempt=3,
    )
    store_gate_result(
        db_session,
        run=other_run,
        passed=False,
        regeneration_count=3,
        vocabulary_version=1,
        violations=(
            GateViolation(
                kind="empty_citation",
                section="lavoro",
                sentence="other run's sentence",
                entry_ids=(),
                detail="other run's detail",
            ),
        ),
    )
    db_session.commit()
    # Diverge the live vocabulary so a live recomputation (the bug this
    # story fixes) would find *zero* violations against `draft`/`frozen` --
    # none of the closed-vocabulary tokens match anything any more -- while
    # every stored row above still has one. If the route were still calling
    # `run_gate()` live, this assertion would fail.
    live_vocabulary = app_instance.state.gate_vocabulary
    app_instance.state.gate_vocabulary = replace(
        live_vocabulary,
        version=live_vocabulary.version + 1,
        planets=frozenset(),
        signs=frozenset(),
        casa_ordinals=frozenset(),
        retrogrado="not-a-real-token",
        stazionario="not-a-real-token-2",
    )

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 200
    assert "regeneration 3 sentence" in response.text
    assert "detail for regeneration 3" in response.text
    assert "regeneration 0 sentence" not in response.text
    assert "regeneration 1 sentence" not in response.text
    assert "other run's sentence" not in response.text
    assert "other run's detail" not in response.text


def test_getting_the_draft_for_a_generic_failure_with_a_grounded_draft_still_shows_the_reason(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Regression: a run can be marked terminally failed (``failed_at`` set)
    by a *generic*, non-``GateFailedError`` failure at the ``gate_passed``
    stage -- e.g. a DB error inside ``store_report()`` after the Gate has
    already passed in-memory -- leaving behind a latest ``ReportDraft`` with
    no matching ``StoredGateResult`` row at all (the Gate never failed for
    this run, so nothing was ever written), which is why ``violations``
    defaults to an empty list here. The "Gate failures" section must still
    render ``run.failure_reason`` in that case -- it must not be gated
    behind ``violations`` being non-empty, since ``view_report_draft`` sets
    ``run`` in context whenever ``run.failed_at is not None``, independent
    of whether a ``StoredGateResult`` row exists."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(
        client_id=ada.id,
        month="2026-01",
        stage="draft_ready",
        failed_at=datetime(2026, 1, 20, 12, 0, 0, tzinfo=UTC),
        failure_reason="stage 'gate_passed' failed 5 consecutive times: simulated DB error",
    )
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    grounded_draft = _a_generated_draft_for(frozen)
    store_report_draft(
        db_session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=grounded_draft,
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 200
    assert "Gate failures" in response.text
    # Not the raw `run.failure_reason in response.text`: Jinja2's
    # autoescaping turns the apostrophes in "stage 'gate_passed'..." into
    # HTML entities, so a substring free of quoting is checked instead
    # (mirrors `test_a_failed_runs_poll_fragment_shows_the_reason_with_no_hx_trigger`).
    assert "simulated DB error" in response.text
    gate_failures_section = response.text.split('<section id="gate-failures">')[1].split(
        "</section>"
    )[0]
    assert "<ul>" not in gate_failures_section
    assert "Cited entries" not in gate_failures_section


def test_getting_the_draft_for_a_passing_run_shows_no_gate_failures_block(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O & Edge-Case Matrix row 2: a passing run's draft view (``failed_at``
    is ``None``) is unchanged -- no Gate recomputation, no "Gate failures"
    block, even though the underlying draft in this test cites nothing more
    grounded than the bound-exhausted-run test above would produce a
    violation for."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    store_report_draft(
        db_session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=draft,
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 200
    assert "Gate failures" not in response.text
