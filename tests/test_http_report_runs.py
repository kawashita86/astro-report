"""``POST /clients/{client_id}/report-runs`` and ``GET /report-runs/{run_id}``
-- Story 3.5's own I/O & Edge-Case Matrix rows (reshaped for AD-20 by Story
3.10), exercised end-to-end through the real app/session wiring, mirroring
``tests/test_http_clients.py``.

The Client and its Natal Chart are created with a real ``compute_natal_chart()``
call (this route never calls it itself -- it only reads the already-stored
chart back via ``deserialize_natal_chart``). ``advance()`` itself is faked
(the ``fake_advance`` fixture) for tests that reach it: Starlette's
``TestClient`` runs the ASGI app on its own worker thread, and pyswisseph's
``set_ephe_path()`` pins the vendored ephemeris per-thread, so a real
``advance()`` call touching ``core/transits/*`` from that thread needs its own
``verify_ephemeris_identity()`` call -- out of scope here, mirroring
``tests/test_http_clients.py``'s own real-vs-fake boundary. Real stage
behavior is ``tests/test_runner_driver.py``'s job; these tests only prove
the routes' own orchestration -- AD-20's start-does-not-advance /
one-stage-per-poll split, auth, 404s, the redirect, the HTMX
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
from shell.adapters.postgres.export_record import ExportRecord
from shell.adapters.postgres.gate_result import StoredGateResult, store_gate_result
from shell.adapters.postgres.report import Report, store_report
from shell.adapters.postgres.report_draft import ReportDraft, store_report_draft
from shell.adapters.postgres.report_payload import ReportPayload, store_report_payload
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

#: The live Gate vocabulary's sha256 digest -- recorded on ``report`` /
#: ``gate_result`` rows alongside ``vocabulary_version`` (epic-5-retro item 45).
_VOCABULARY_CONTENT_HASH = load_gate_vocabulary(DEFAULT_VOCABULARY_PATH).content_hash

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
def fake_advance(app_instance: FastAPI, monkeypatch: pytest.MonkeyPatch):
    """Stand in for a real ``advance()`` call, mirroring
    ``tests/test_http_clients.py``'s own real-vs-fake boundary
    (``fake_chart_computation``): Starlette's ``TestClient`` runs the ASGI app
    on its own worker thread, and pyswisseph's ``set_ephe_path()`` pins the
    vendored ephemeris per-thread -- a real ``advance()`` call reaching
    ``core/transits/*`` from that thread would need its own
    ``verify_ephemeris_identity()`` call, out of scope for a
    route-orchestration test. Real stage-advancement behavior (one stage per
    call, real backoff, real month resolution, the advisory lock) is
    ``tests/test_runner_driver.py``'s / ``tests/test_runner_advisory_lock.py``'s
    job; these HTTP tests only need to prove the poll route calls
    ``advance()`` once per request, persists whatever it returns, and
    renders correctly around it.

    Like the real ``advance()`` (AD-20, Story 3.10) this moves the run
    forward by **at most one** stage per call -- here only through the first
    two stages, enough to exercise the poll view's stage rendering without a
    real ``core/`` call. ``get_generator`` is also overridden with a fake,
    never a real ``GeminiGenerator`` -- mirrors ``tests/test_http_clients.py``'s
    own ``get_geocoder`` override: ``_fake_advance`` never actually calls the
    ``generator`` it receives.
    """
    import shell.http.routes.report_runs as report_runs_module

    def _fake_advance(
        session,
        run,
        *,
        natal_chart,
        natal_chart_id,
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
            run.natal_chart_id = natal_chart_id
            session.add(run)
            session.commit()
            return run
        if run.stage == "natal_ready":
            run.transit_events = []
            run.stage = "transits_ready"
            session.add(run)
            session.commit()
            return run
        return run

    monkeypatch.setattr(report_runs_module, "advance", _fake_advance)
    app_instance.dependency_overrides[get_generator] = lambda: object()
    return _fake_advance


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


def test_starting_a_run_creates_it_without_advancing_and_redirects_to_the_poll_view(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    """AD-20 (Story 3.10): the start POST only creates the row, commits and
    redirects -- it runs no stage, so ``stage`` is ``None`` and every
    stage-produced column is still ``NULL`` when the redirect returns."""
    ada = _create_client_with_real_chart(db_session)

    response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )

    assert response.status_code == 303
    runs = _report_runs(db_session)
    assert len(runs) == 1
    run = runs[0]
    assert response.headers["location"] == f"/report-runs/{run.id}"
    assert run.stage is None
    assert run.month_start_utc is None
    assert run.month_end_utc is None
    assert run.transit_events is None


def test_starting_a_run_does_not_call_advance(
    authenticated_client: TestClient,
    db_session: Session,
    app_instance: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AD-20: no runner function is called from the start route -- only the
    poll route advances."""
    import shell.http.routes.report_runs as report_runs_module

    ada = _create_client_with_real_chart(db_session)
    calls: list[int] = []

    def _spy_advance(*args, **kwargs):
        calls.append(1)

    monkeypatch.setattr(report_runs_module, "advance", _spy_advance)
    app_instance.dependency_overrides[get_generator] = lambda: object()

    response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert calls == [], "the start route must not call advance()"
    assert len(_report_runs(db_session)) == 1


def test_each_poll_advances_the_run_by_one_stage(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    """AD-20: the first stage runs on the first poll; each subsequent poll
    moves the run forward one stage."""
    ada = _create_client_with_real_chart(db_session)
    start_response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )
    location = start_response.headers["location"]

    # Story 9.5: the poll fragment no longer leaks the raw English stage
    # token -- it renders the stage-track node states and an Italian
    # progress-tense caption instead (`shell/http/stage_view.py`).
    first_poll = authenticated_client.get(location)
    assert first_poll.status_code == 200
    assert "Ricerca dei transiti" in first_poll.text  # active once natal_ready

    second_poll = authenticated_client.get(location)
    assert second_poll.status_code == 200
    assert "Assemblaggio del Payload" in second_poll.text  # active once transits_ready


def test_the_poll_route_invokes_advance_exactly_once_per_request(
    authenticated_client: TestClient,
    db_session: Session,
    app_instance: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AD-20: each poll calls ``advance()`` exactly once -- never in a loop."""
    import shell.http.routes.report_runs as report_runs_module

    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01")
    db_session.add(run)
    db_session.commit()

    calls: list[int] = []

    def _counting_advance(session, run, **kwargs):
        calls.append(1)
        return run

    monkeypatch.setattr(report_runs_module, "advance", _counting_advance)
    app_instance.dependency_overrides[get_generator] = lambda: object()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert calls == [1]


def test_polling_an_already_completed_run_is_a_noop_and_still_shows_its_stage(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    ada = _create_client_with_real_chart(db_session)
    start_response = authenticated_client.post(
        f"/clients/{ada.id}/report-runs", data={"month": "2026-01"}, follow_redirects=False
    )
    location = start_response.headers["location"]

    # fake_advance drains through natal_ready then transits_ready, one per
    # poll, then stops -- further polls are a no-op.
    authenticated_client.get(location)
    authenticated_client.get(location)
    third_poll = authenticated_client.get(location)
    fourth_poll = authenticated_client.get(location)

    assert third_poll.status_code == 200
    assert fourth_poll.status_code == 200
    # fake_advance never reaches a terminal stage, so polling keeps going.
    assert "hx-trigger" in fourth_poll.text
    assert "Assemblaggio del Payload" in fourth_poll.text  # active once transits_ready
    runs = _report_runs(db_session)
    assert len(runs) == 1


def test_an_htmx_poll_request_gets_a_fragment_without_the_full_page_shell(
    authenticated_client: TestClient, db_session: Session, fake_advance
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
    assert "Assemblaggio del Payload" in fragment.text  # active once transits_ready


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
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="payload_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/payload"' in response.text


def test_the_poll_view_has_no_payload_link_before_payload_ready(
    authenticated_client: TestClient, db_session: Session, fake_advance
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
    # epic-6-retro-item-50: the draft view also renders the shared Italian
    # headings, so `section_titles` must be threaded into its context too.
    assert "<h2>Energia generale</h2>" in response.text
    # Story 9.5: the raw snake_case name now legitimately appears once, as
    # the Section's jump-target anchor id -- never anywhere else (a heading,
    # a label) that would leak it to the reader.
    assert response.text.count("energia_generale") == 1
    assert 'id="sezione-energia_generale"' in response.text
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


def test_the_poll_view_links_to_payload_while_the_gate_is_still_running(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    """Story 9.5's I/O Matrix, "Gate running": ``draft_ready`` with no
    failure yet links to Payload, not the (still unvetted) draft."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="draft_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/payload"' in response.text
    assert f'href="/report-runs/{run.id}/draft"' not in response.text


def test_the_poll_view_links_to_the_draft_once_a_gate_failure_exists(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Story 9.5's I/O Matrix, "Gate failure (bound exhausted)": a Gate
    -failed run's poll fragment links to Bozza (``/draft``), so Francesco
    reaches the violation cards from the stage view directly."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_bound_exhausted_run(ada.id)
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
        attempt=run.regeneration_count,
    )
    store_gate_result(
        db_session,
        run=run,
        passed=False,
        regeneration_count=run.regeneration_count,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(
            GateViolation(
                kind="empty_citation",
                section="lavoro",
                sentence="x",
                entry_ids=(),
                detail="y",
            ),
        ),
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/draft"' in response.text
    assert "Vedi bozza" in response.text
    # The two branches are mutually exclusive at draft_ready: once
    # gate_failed is true, Payload is no longer offered in its place.
    assert f'href="/report-runs/{run.id}/payload"' not in response.text
    assert "Vedi Payload" not in response.text


def test_the_poll_view_has_no_draft_link_before_draft_ready(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="payload_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert "Vedi bozza" not in response.text


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
    """``fake_advance`` (used by every other test here) overrides ``get_generator``
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
    (Story 4.8) -- ``advance()`` short-circuits on ``failed_at`` before ever
    touching the Generator, so no ``fake_advance``/real Gemini call is needed
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
    # Story 9.5: the stage track marks the node the run was working toward
    # (Bozza, the one after `payload_ready`) failed.
    assert "stage-track__node--failed" in response.text


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


def _a_bound_exhausted_run(client_id, *, failed_at: datetime | None = None) -> ReportRun:
    """A ``ReportRun`` in Story 5.4's exact regeneration-bound-exhausted
    terminal state: ``stage`` stays ``"draft_ready"`` (never rewound back,
    unlike a run mid-regeneration), ``failed_at``/``failure_reason`` are set,
    and (unlike ``_a_failed_run``, Story 4.8's generic stage-failure shape)
    a ``ReportDraft`` row for this run does exist -- mirrors
    ``shell/runner/driver.py``'s ``except GateFailedError`` branch once
    ``regeneration_count`` exceeds ``_MAX_REGENERATIONS``.

    ``failed_at`` defaults to "now" (Story 9.5): every caller here that also
    persists a *current-cycle* failing ``StoredGateResult`` does so via
    ``store_gate_result()``, whose own ``created_at`` defaults to
    ``datetime.now(UTC)`` too -- the two calls land comfortably inside
    ``_current_cycle_gate_failure``'s ``_GATE_RESULT_CORRELATION_WINDOW`` (2s)
    without the test needing to fake the clock. A caller building the
    review-loop-1 "stale row from an earlier cycle" case passes an explicit,
    far-past ``failed_at`` instead, to land the row *outside* that window on
    purpose."""
    return ReportRun(
        client_id=client_id,
        month="2026-01",
        stage="draft_ready",
        regeneration_count=4,
        failed_at=failed_at if failed_at is not None else datetime.now(UTC),
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
        vocabulary_content_hash=gate_result.vocabulary_content_hash,
        violations=gate_result.violations,
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/draft")

    assert response.status_code == 200
    assert "Marte è retrogrado." in response.text
    # Story 9.5: the raw kind token is now an Italian label, and the
    # violation card links to its Sezione's own anchor.
    assert "Citazione vuota" in response.text
    assert 'href="#sezione-energia_generale"' in response.text
    assert 'id="sezione-energia_generale"' in response.text
    assert "sentence is a Claim" in response.text
    assert run.failure_reason in response.text
    assert "Verifica di fondatezza non superata" in response.text
    assert f'action="/report-runs/{run.id}/regenerate"' in response.text


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
    ``advance()``'s ``except GateFailedError`` block calls ``store_gate_result``
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
            vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
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
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
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
    defaults to an empty list here. The non-Gate ``.panel--danger`` must
    still render ``run.failure_reason`` in that case -- it must not be gated
    behind ``violations`` being non-empty, since ``view_report_draft`` sets
    ``run`` in context whenever ``run.failed_at is not None``, independent
    of whether a ``StoredGateResult`` row exists. No Rigenera form: Story 9.5
    only offers that recovery for a *current-cycle* Gate failure."""
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
    assert "Generazione non riuscita" in response.text
    # Not the raw `run.failure_reason in response.text`: Jinja2's
    # autoescaping turns the apostrophes in "stage 'gate_passed'..." into
    # HTML entities, so a substring free of quoting is checked instead
    # (mirrors `test_a_failed_runs_poll_fragment_shows_the_reason_with_no_hx_trigger`).
    assert "simulated DB error" in response.text
    assert "Verifica di fondatezza non superata" not in response.text
    assert "violation-card" not in response.text
    assert "/regenerate" not in response.text


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
    assert "Verifica di fondatezza non superata" not in response.text
    assert "Generazione non riuscita" not in response.text
    assert "violation-card" not in response.text


# --- Story 9.5: the stage track -----------------------------------------------------


def test_a_running_runs_poll_fragment_shows_all_six_nodes_and_the_active_caption(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="payload_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert response.text.count("stage-track__node") >= 6
    for label in (
        "Tema natale",
        "Transiti",
        "Payload",
        "Bozza",
        "Verifica di fondatezza",
        "Esportazione",
    ):
        assert label in response.text
    assert "stage-track__node--active" in response.text
    assert "Generazione della bozza" in response.text  # payload_ready's own caption
    assert "hx-trigger" in response.text


def test_a_gate_passed_runs_poll_fragment_has_no_hx_trigger(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert "hx-trigger" not in response.text
    # Jinja2 autoescapes the apostrophe as `&#39;`.
    assert "Pronto per l" in response.text and "esportazione" in response.text


def test_an_exported_runs_poll_fragment_shows_every_node_done_with_no_hx_trigger(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="exported")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert "hx-trigger" not in response.text
    assert "Esportato" in response.text
    assert "stage-track__node--pending" not in response.text
    assert "stage-track__node--active" not in response.text
    assert response.text.count("stage-track__node--done") == 6


# --- Story 9.5: POST /report-runs/{run_id}/regenerate -------------------------------


def _a_current_cycle_gate_failed_run(db_session: Session, client_id) -> ReportRun:
    """A Gate-failed run whose ``StoredGateResult`` correlates with
    ``failed_at`` within ``_current_cycle_gate_failure``'s window -- the
    shape the Rigenera route (and the UI that shows it) requires."""
    run = _a_bound_exhausted_run(client_id)
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
        attempt=run.regeneration_count,
    )
    store_gate_result(
        db_session,
        run=run,
        passed=False,
        regeneration_count=run.regeneration_count,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(
            GateViolation(
                kind="empty_citation",
                section="lavoro",
                sentence="x",
                entry_ids=(),
                detail="y",
            ),
        ),
    )
    db_session.commit()
    return run


def test_regenerating_without_a_session_is_401(client: TestClient) -> None:
    response = client.post(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/regenerate"
    )

    assert response.status_code == 401


def test_regenerating_an_unknown_run_is_404(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/regenerate"
    )

    assert response.status_code == 404


def test_regenerating_a_run_that_has_not_failed_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="draft_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.post(f"/report-runs/{run.id}/regenerate")

    assert response.status_code == 404


def test_regenerating_a_run_with_a_non_gate_failure_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """A generic terminal failure (Story 4.8) -- no correlated
    ``StoredGateResult`` -- must not be regenerable: the button is never
    shown for it, and a direct POST must not bypass that."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_failed_run(ada.id)
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.post(f"/report-runs/{run.id}/regenerate")

    assert response.status_code == 404


def test_regenerating_a_gate_failed_run_rewinds_it_for_one_more_attempt(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = _a_current_cycle_gate_failed_run(db_session, ada.id)

    response = authenticated_client.post(
        f"/report-runs/{run.id}/regenerate", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/report-runs/{run.id}"
    db_session.refresh(run)
    assert run.failed_at is None
    assert run.failure_reason is None
    assert run.stage == "payload_ready"
    # AD-10: the driver, never this route, owns the counter -- unchanged.
    assert run.regeneration_count == 4


def test_regenerating_never_calls_advance_and_the_next_poll_runs_draft_ready(
    authenticated_client: TestClient,
    db_session: Session,
    app_instance: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Design Notes' own claim: the route rewinds the row and returns
    without ever calling ``advance()`` -- regeneration itself happens on the
    *next* poll, exactly like ``start_report_run``."""
    import shell.http.routes.report_runs as report_runs_module

    ada = _create_client_with_real_chart(db_session)
    run = _a_current_cycle_gate_failed_run(db_session, ada.id)

    advance_calls: list[str | None] = []

    def _counting_advance(session, run, **kwargs):
        advance_calls.append(run.stage)
        if run.stage == "payload_ready":
            run.stage = "draft_ready"
            session.add(run)
            session.commit()
        return run

    monkeypatch.setattr(report_runs_module, "advance", _counting_advance)
    app_instance.dependency_overrides[get_generator] = lambda: object()

    regen_response = authenticated_client.post(
        f"/report-runs/{run.id}/regenerate", follow_redirects=False
    )
    assert regen_response.status_code == 303
    assert advance_calls == []  # never called inside the regenerate handler

    poll_response = authenticated_client.get(f"/report-runs/{run.id}")

    assert poll_response.status_code == 200
    assert advance_calls == ["payload_ready"]
    db_session.refresh(run)
    assert run.stage == "draft_ready"


def test_a_non_gate_failure_after_an_earlier_superseded_gate_failure_hides_rigenera(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Review-loop 1's own scenario: a run failed the Gate once (a failing
    ``StoredGateResult`` row exists), was rewound via ``/regenerate``, and
    *this* cycle's terminal failure is unrelated to the Gate. The stale row
    must not resurface as if it were current -- no violation cards, no
    Rigenera, on either the poll fragment or ``/draft`` -- and a direct
    ``POST …/regenerate`` must still 404. The stale row's ``created_at`` is
    explicitly backdated (Design Notes) so the test is deterministic
    regardless of how fast it executes."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(
        client_id=ada.id,
        month="2026-01",
        stage="draft_ready",
        regeneration_count=1,
        failed_at=datetime.now(UTC),
        failure_reason="stage 'gate_passed' failed 5 consecutive times: simulated DB error",
    )
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
    # The stale row: a real Gate failure from the cycle *before* the
    # `/regenerate` rewind that led to this run's current, unrelated
    # failure -- backdated well outside the correlation window.
    db_session.add(
        StoredGateResult(
            client_id=ada.id,
            report_run_id=run.id,
            passed=False,
            regeneration_count=0,
            vocabulary_version=1,
            vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
            violations=[
                {
                    "kind": "empty_citation",
                    "section": "lavoro",
                    "sentence": "the stale cycle's sentence",
                    "entry_ids": [],
                    "detail": "the stale cycle's detail",
                }
            ],
            created_at=run.failed_at - timedelta(hours=1),
        )
    )
    db_session.commit()

    poll_response = authenticated_client.get(f"/report-runs/{run.id}")
    assert poll_response.status_code == 200
    assert "the stale cycle's sentence" not in poll_response.text
    assert "Vedi bozza" not in poll_response.text
    assert "simulated DB error" in poll_response.text

    draft_response = authenticated_client.get(f"/report-runs/{run.id}/draft")
    assert draft_response.status_code == 200
    assert "the stale cycle's sentence" not in draft_response.text
    assert "violation-card" not in draft_response.text
    assert "/regenerate" not in draft_response.text
    assert "Generazione non riuscita" in draft_response.text

    regen_response = authenticated_client.post(f"/report-runs/{run.id}/regenerate")
    assert regen_response.status_code == 404


def _a_run_with_a_gate_result_offset_by(db_session: Session, client_id, *, offset) -> ReportRun:
    """A terminally failed run at ``draft_ready`` with exactly one failing
    ``StoredGateResult`` whose ``created_at`` sits ``run.failed_at - offset``
    -- built directly (not via ``store_gate_result()``, which always defaults
    ``created_at`` to "now") so the gap from ``failed_at`` is exact and
    deterministic, for pinning down ``_GATE_RESULT_CORRELATION_WINDOW``'s own
    `` > `` vs `` >= `` boundary (review-loop 2)."""
    run = ReportRun(
        client_id=client_id,
        month="2026-01",
        stage="draft_ready",
        regeneration_count=1,
        failed_at=datetime.now(UTC),
        failure_reason="regeneration bound exhausted after 1 attempts: "
        "Refusing to advance past the Groundedness Gate: 1 violation(s) against the Payload.",
    )
    db_session.add(run)
    db_session.commit()
    db_session.add(
        StoredGateResult(
            client_id=client_id,
            report_run_id=run.id,
            passed=False,
            regeneration_count=0,
            vocabulary_version=1,
            vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
            violations=[
                {
                    "kind": "empty_citation",
                    "section": "lavoro",
                    "sentence": "boundary sentence",
                    "entry_ids": [],
                    "detail": "boundary detail",
                }
            ],
            created_at=run.failed_at - offset,
        )
    )
    db_session.commit()
    return run


def test_a_gate_result_1_9s_before_failed_at_is_still_the_current_cycle(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Just *inside* the 2s correlation window (``_GATE_RESULT_CORRELATION_WINDOW``,
    ``shell/http/routes/report_runs.py``) -- still resolves as a Gate
    failure: the violation panel and Rigenera show."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_run_with_a_gate_result_offset_by(db_session, ada.id, offset=timedelta(seconds=1.9))

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert "Vedi bozza" in response.text


def test_a_gate_result_2_1s_before_failed_at_is_treated_as_a_stale_prior_cycle(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Just *outside* the 2s correlation window -- resolves as a non-Gate
    failure: no violation panel, no Rigenera, even though a failing
    ``StoredGateResult`` row exists for this run."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_run_with_a_gate_result_offset_by(db_session, ada.id, offset=timedelta(seconds=2.1))

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert "Vedi bozza" not in response.text


# --- Story 6.1: GET /report-runs/{run_id}/report -----------------------------------


def _store_passed_report(
    db_session: Session,
    *,
    run: ReportRun,
    frozen: dict,
    draft: GeneratedDraft,
    regeneration_count: int = 0,
    created_at: datetime | None = None,
) -> None:
    """Persist the full chain a passed Gate leaves behind: a ``ReportDraft``,
    a ``Report``, and a passing ``StoredGateResult`` -- mirrors
    ``shell/runner/driver.py``'s own ``_run_gate_passed`` writes.

    ``Report``/``StoredGateResult`` are constructed directly (bypassing
    ``store_report``/``store_gate_result``) whenever ``created_at`` is given:
    neither helper accepts a ``created_at`` override, and both rows are
    immutable once persisted, so there is no way to backdate one after the
    fact -- it must be set at construction time."""
    store_report_draft(
        db_session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=draft,
        attempt=regeneration_count,
    )
    if created_at is None:
        store_report(
            db_session,
            run=run,
            style_guide_version=1,
            payload_schema_version=frozen["schema_version"],
            gate_vocabulary_version=1,
            gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        )
        store_gate_result(
            db_session,
            run=run,
            passed=True,
            regeneration_count=regeneration_count,
            vocabulary_version=1,
            vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
            violations=(),
        )
    else:
        db_session.add(
            Report(
                client_id=run.client_id,
                report_run_id=run.id,
                style_guide_version=1,
                payload_schema_version=frozen["schema_version"],
                gate_vocabulary_version=1,
                gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
                created_at=created_at,
            )
        )
        db_session.add(
            StoredGateResult(
                client_id=run.client_id,
                report_run_id=run.id,
                passed=True,
                regeneration_count=regeneration_count,
                vocabulary_version=1,
                vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
                violations=[],
                created_at=created_at,
            )
        )
    db_session.commit()


def test_getting_the_report_without_a_session_is_401(client: TestClient) -> None:
    response = client.get("/report-runs/01a01abf-0000-7000-8000-000000000000/report")

    assert response.status_code == 401


def test_getting_the_report_for_an_unknown_run_is_404(authenticated_client: TestClient) -> None:
    response = authenticated_client.get(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/report"
    )

    assert response.status_code == 404


def test_getting_the_report_for_a_run_whose_gate_has_not_passed_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Gate not yet passed" -- a ``ReportRun`` exists (even at
    ``draft_ready``, with a real ``ReportDraft``/``ReportPayload`` already
    persisted) but no ``Report`` row exists yet, so the route still 404s --
    gating is on ``Report``'s existence, never on ``run.stage``."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="draft_ready")
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
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 404


def test_getting_the_report_for_a_terminally_failed_run_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """A terminally failed run (Story 4.8/5.4) never has a ``Report`` row --
    a Gate failure never writes one -- so the finished-Report view stays
    404 for it too, exactly like the Draft view's own failed-run row."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_bound_exhausted_run(ada.id)
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 404


def test_getting_the_report_shows_all_eight_sections_and_the_gate_result(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """AC1: a Report that has passed the Gate shows all eight Sections in
    their fixed order plus the Gate result, including a regeneration count
    of 0 for a never-regenerated run. AC2: the Payload view is reachable in
    one interaction from the Report."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    # epic-6-retro-item-50: headings are the shared Italian titles, not the
    # raw snake_case field names.
    for heading in (
        "Energia generale",
        "Amore",
        "Lavoro",
        "Denaro",
        "Benessere",
        "Giorni favorevoli",
        "Giorni di attenzione",
        "Consiglio finale",
    ):
        assert f"<h2>{heading}</h2>" in response.text
    assert "Un mese equilibrato." in response.text
    assert "Venere sostiene i legami." in response.text
    assert "Ottimo per gli incontri." in response.text
    assert "Passed" in response.text
    assert "regenerated 0 times" in response.text
    assert f'href="/report-runs/{run.id}/payload"' in response.text


def test_getting_the_report_shows_the_stored_regeneration_count_not_the_runs_own(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Gate passed after regenerating" -- the regeneration
    count shown is the one persisted on the passing ``StoredGateResult`` row
    (epic-5-retro-item-38's precedent), never read off ``run.regeneration_count``
    directly, even when the two differ."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(
        client_id=ada.id, month="2026-01", stage="gate_passed", regeneration_count=5
    )
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=2)

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    assert "regenerated 2 times" in response.text
    assert "regenerated 5 times" not in response.text


def test_getting_a_report_generated_months_earlier_still_renders_fully(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Report generated months earlier" -- a ``Report``/
    ``StoredGateResult`` pair backdated well into the past renders exactly
    as a fresh one would; nothing about the route's behavior depends on
    row age."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(
        db_session,
        run=run,
        frozen=frozen,
        draft=draft,
        regeneration_count=0,
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    assert "Passed" in response.text
    assert "regenerated 0 times" in response.text
    assert f'href="/report-runs/{run.id}/payload"' in response.text
    assert "Un mese equilibrato." in response.text


def test_getting_the_report_with_multiple_gate_results_picks_the_passing_row(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Proves the ``.order_by(StoredGateResult.regeneration_count.desc())``
    added to the passing-row query picks the actual passing row -- not an
    arbitrary one -- even when earlier failing attempts for the same run
    (Story 5.4 regeneration) left their own ``StoredGateResult`` rows
    behind."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(
        client_id=ada.id, month="2026-01", stage="gate_passed", regeneration_count=2
    )
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    for count in (0, 1):
        store_gate_result(
            db_session,
            run=run,
            passed=False,
            regeneration_count=count,
            vocabulary_version=1,
            vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
            violations=(
                GateViolation(
                    kind="empty_citation",
                    section="lavoro",
                    sentence=f"failing attempt {count}",
                    entry_ids=(),
                    detail=f"detail {count}",
                ),
            ),
        )
    db_session.commit()
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=2)

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    assert "regenerated 2 times" in response.text


def test_getting_the_report_for_a_run_that_has_moved_past_gate_passed_into_exported(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Gating is on the persisted ``Report`` row's existence, never on
    ``run.stage`` -- a run that has since advanced to ``exported`` (Story
    6.2) must still show its Report exactly like one still at
    ``gate_passed``."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="exported")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    for heading in (
        "Energia generale",
        "Amore",
        "Lavoro",
        "Denaro",
        "Benessere",
        "Giorni favorevoli",
        "Giorni di attenzione",
        "Consiglio finale",
    ):
        assert f"<h2>{heading}</h2>" in response.text


@pytest.mark.parametrize("stage", ["gate_passed", "exported"])
def test_the_poll_view_links_to_the_report_once_the_gate_has_passed(
    authenticated_client: TestClient, db_session: Session, fake_advance, stage: str
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage=stage)
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/report"' in response.text


def test_the_poll_view_has_no_report_link_before_the_gate_has_passed(
    authenticated_client: TestClient, db_session: Session, fake_advance
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="draft_ready")
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}")

    assert "View Report" not in response.text


# --- Story 6.2: GET /report-runs/{run_id}/export/pdf --------------------------------


def _export_records(db_session: Session) -> list[ExportRecord]:
    return list(db_session.exec(select(ExportRecord)))


def test_downloading_the_export_pdf_without_a_session_is_401(client: TestClient) -> None:
    response = client.get("/report-runs/01a01abf-0000-7000-8000-000000000000/export/pdf")

    assert response.status_code == 401


def test_downloading_the_export_pdf_for_an_unknown_run_is_404(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/export/pdf"
    )

    assert response.status_code == 404


def test_downloading_the_export_pdf_for_a_run_whose_gate_has_not_passed_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Gate not yet passed" -- gating is on the persisted
    ``Report`` row's existence, never on ``run.stage``, mirroring
    ``view_report``'s own boundary (Story 6.1)."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="draft_ready")
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
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    assert response.status_code == 404
    assert _export_records(db_session) == []


def test_downloading_the_export_pdf_for_a_terminally_failed_run_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """A terminally failed run never has a ``Report`` row, so the export
    route 404s for it too, exactly like the Report view (Story 6.1)."""
    ada = _create_client_with_real_chart(db_session)
    run = _a_bound_exhausted_run(ada.id)
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    assert response.status_code == 404


def test_the_first_export_returns_a_pdf_and_advances_the_run_to_exported(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "First export" -- 200, a real PDF downloads,
    ``run.stage`` becomes ``"exported"``, and exactly one ``ExportRecord``
    row is written."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="report-{run.id}.pdf"'
    )
    assert response.content.startswith(b"%PDF")
    assert run.stage == "exported"
    records = _export_records(db_session)
    assert len(records) == 1
    assert records[0].format == "pdf"
    assert records[0].client_id == ada.id


def test_exporting_an_already_exported_report_again_leaves_the_stage_unchanged(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Repeat export" -- ``run.stage`` stays ``"exported"``, but
    one more ``ExportRecord`` row is written per export."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    first_response = authenticated_client.get(f"/report-runs/{run.id}/export/pdf")
    second_response = authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.content.startswith(b"%PDF")
    assert run.stage == "exported"
    records = _export_records(db_session)
    assert len(records) == 2
    assert {record.format for record in records} == {"pdf"}


def test_exporting_a_run_that_is_already_exported_still_returns_a_pdf(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Same as above, but the run already starts at ``"exported"`` (a fresh
    process picking up an already-exported run) -- the stage stays put and
    one more ``ExportRecord`` row is written."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="exported")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    assert response.status_code == 200
    assert run.stage == "exported"
    assert len(_export_records(db_session)) == 1


def test_the_exported_html_contains_only_the_eight_sections_and_the_clients_name(
    authenticated_client: TestClient,
    db_session: Session,
    app_instance: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boundaries: "The exported PDF contains only the eight Sections and
    the Client's name -- no chart wheel, no Payload, no Gate result, no run
    identifier, no internal metadata." ``html_to_pdf`` is monkeypatched to
    capture the exact HTML string the route hands to WeasyPrint, since a
    real PDF's content streams are not plain-text-searchable -- this proves
    what the route assembles, the one input WeasyPrint ever sees."""
    import shell.http.routes.report_runs as report_runs_module

    captured: dict[str, str] = {}

    def _fake_html_to_pdf(html: str) -> bytes:
        captured["html"] = html
        return b"%PDF-fake"

    monkeypatch.setattr(report_runs_module, "html_to_pdf", _fake_html_to_pdf)

    ada = _create_client_with_real_chart(db_session, name="Ada Lovelace")
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    assert response.status_code == 200
    assert response.content == b"%PDF-fake"
    html = captured["html"]
    assert "Ada Lovelace" in html
    # epic-6-retro-item-50: the client-facing export carries the Italian
    # section titles, not the raw snake_case field names.
    for heading in (
        "Energia generale",
        "Amore",
        "Lavoro",
        "Denaro",
        "Benessere",
        "Giorni favorevoli",
        "Giorni di attenzione",
        "Consiglio finale",
    ):
        assert f"<h2>{heading}</h2>" in html
    # The raw snake_case keys must not leak as headings. Only the
    # underscore-bearing names are safe canaries -- `amore` / `lavoro` /
    # `denaro` / `benessere` are ordinary Italian words that legitimately
    # occur in those sections' prose.
    for name in (
        "energia_generale",
        "giorni_favorevoli",
        "giorni_di_attenzione",
        "consiglio_finale",
    ):
        assert name not in html
    assert "Un mese equilibrato." in html
    assert "Venere sostiene i legami." in html
    assert "Ottimo per gli incontri." in html
    # No chart wheel, no Payload, no Gate result, no run identifier, no
    # internal metadata (this story's Boundaries).
    assert str(run.id) not in html
    assert "Gate" not in html
    assert "Payload" not in html
    assert "gate_passed" not in html
    assert "regenerated" not in html


# --- download_report_pdf's data-integrity-bug guards ---------------------------
#
# Once a Report row exists, download_report_pdf reads back the ReportRun,
# ReportDraft, ReportPayload and Client rows it implies with RuntimeError
# guards, never a 404 (mirrors view_report's own shape, Story 6.1) -- their
# absence at that point is a data-integrity bug, not a not-ready state. Each
# test below builds the full happy-path chain via _store_passed_report, then
# deletes exactly the one row its own guard checks for, so only that guard
# fires. FastAPI's TestClient (raise_server_exceptions=True, the default) lets
# an unhandled RuntimeError from the route propagate straight out of the
# `.get()` call rather than becoming a response, hence `pytest.raises`.


def test_downloading_the_export_pdf_for_a_report_with_a_deleted_report_run_raises(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    run_id = run.id
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    db_session.delete(run)
    db_session.commit()

    with pytest.raises(RuntimeError, match="references a missing ReportRun"):
        authenticated_client.get(f"/report-runs/{run_id}/export/pdf")


def test_downloading_the_export_pdf_for_a_report_with_a_deleted_report_draft_raises(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    for stored_draft in db_session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).all():
        db_session.delete(stored_draft)
    db_session.commit()

    with pytest.raises(RuntimeError, match="has no matching ReportDraft"):
        authenticated_client.get(f"/report-runs/{run.id}/export/pdf")


def test_downloading_the_export_pdf_for_a_report_with_a_deleted_report_payload_raises(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    for stored_payload in db_session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).all():
        db_session.delete(stored_payload)
    db_session.commit()

    with pytest.raises(RuntimeError, match="has no matching ReportPayload"):
        authenticated_client.get(f"/report-runs/{run.id}/export/pdf")


def test_downloading_the_export_pdf_for_a_report_with_a_deleted_client_raises(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    client_row = db_session.get(Client, ada.id)
    assert client_row is not None
    db_session.delete(client_row)
    db_session.commit()

    with pytest.raises(RuntimeError, match="references a missing Client"):
        authenticated_client.get(f"/report-runs/{run.id}/export/pdf")


def test_the_report_view_links_to_the_export_pdf_route(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/export/pdf"' in response.text


# --- spec-6-2b / epic-6 retro item 47: GET /report-runs/{run_id}/export/markdown ---
#
# Structurally identical to the /export/pdf route above -- same
# _load_passed_report_bundle gate, same first-export-advances-stage /
# every-export-writes-an-ExportRecord semantics -- so these mirror the PDF
# cases, differing only in body (Markdown) and ExportRecord.format.


def test_downloading_the_export_markdown_without_a_session_is_401(client: TestClient) -> None:
    response = client.get(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/export/markdown"
    )

    assert response.status_code == 401


def test_downloading_the_export_markdown_for_an_unknown_run_is_404(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/export/markdown"
    )

    assert response.status_code == 404


def test_downloading_the_export_markdown_for_a_run_whose_gate_has_not_passed_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="draft_ready")
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
    )
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/export/markdown")

    assert response.status_code == 404
    assert _export_records(db_session) == []


def test_downloading_the_export_markdown_for_a_terminally_failed_run_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = _a_bound_exhausted_run(ada.id)
    db_session.add(run)
    db_session.commit()

    response = authenticated_client.get(f"/report-runs/{run.id}/export/markdown")

    assert response.status_code == 404


def test_the_first_markdown_export_returns_the_file_and_advances_the_run_to_exported(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "First export" -- 200, a ``.md`` attachment downloads,
    ``run.stage`` becomes ``"exported"``, exactly one ``ExportRecord`` row is
    written with ``format == "markdown"``."""
    ada = _create_client_with_real_chart(db_session, name="Ada Lovelace")
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/export/markdown")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="report-{run.id}.md"'
    )
    body = response.text
    # The eight Italian-titled Sections and the Client's name, nothing else.
    assert body.startswith("# Ada Lovelace\n")
    for heading in (
        "## Energia generale",
        "## Amore",
        "## Lavoro",
        "## Denaro",
        "## Benessere",
        "## Giorni favorevoli",
        "## Giorni di attenzione",
        "## Consiglio finale",
    ):
        assert heading in body
    assert "Un mese equilibrato." in body
    assert "Venere sostiene i legami." in body
    assert "Ottimo per gli incontri." in body
    assert str(run.id) not in body
    assert "Gate" not in body
    assert "Payload" not in body

    assert run.stage == "exported"
    records = _export_records(db_session)
    assert len(records) == 1
    assert records[0].format == "markdown"
    assert records[0].client_id == ada.id


def test_repeating_the_markdown_export_writes_a_new_record_but_leaves_the_stage(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Repeat export" -- ``run.stage`` stays ``"exported"``, one
    more ``ExportRecord(format="markdown")`` row per call."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    first = authenticated_client.get(f"/report-runs/{run.id}/export/markdown")
    second = authenticated_client.get(f"/report-runs/{run.id}/export/markdown")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.text == second.text
    assert run.stage == "exported"
    records = _export_records(db_session)
    assert len(records) == 2
    assert {record.format for record in records} == {"markdown"}


def test_the_report_view_links_to_the_export_markdown_route(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/export/markdown"' in response.text


# --- Story 6.3: elapsed_seconds at export time -------------------------------------


def test_the_first_export_records_elapsed_seconds_from_run_creation(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Export happens" -- ``elapsed_seconds`` reflects the time
    from ``run.created_at`` (Client selection) to the export, in whole
    seconds, and the new row's ``disposition`` starts ``NULL``."""
    ada = _create_client_with_real_chart(db_session)
    created_at = datetime.now(UTC) - timedelta(seconds=100)
    run = ReportRun(
        client_id=ada.id,
        month="2026-01",
        stage="gate_passed",
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)

    response = authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    assert response.status_code == 200
    records = _export_records(db_session)
    assert len(records) == 1
    # Only a lower bound: >= 100 is the deliberate gap set up above. No
    # upper bound -- how long the request itself (including a real PDF
    # render) takes is not this test's concern, and asserting one would
    # make the test flaky under CI load or on slower hardware.
    assert records[0].elapsed_seconds >= 100
    assert records[0].disposition is None


# --- Story 6.3: POST /report-runs/{run_id}/export/disposition ----------------------


def _passed_report_run(db_session: Session) -> ReportRun:
    """Build a passed, exportable ``ReportRun`` -- shared setup for the
    disposition-route tests below."""
    ada = _create_client_with_real_chart(db_session)
    run = ReportRun(client_id=ada.id, month="2026-01", stage="gate_passed")
    db_session.add(run)
    db_session.commit()
    frozen = _a_frozen_payload_with_one_aspect()
    store_report_payload(db_session, run=run, frozen=frozen)
    draft = _a_generated_draft_for(frozen)
    _store_passed_report(db_session, run=run, frozen=frozen, draft=draft, regeneration_count=0)
    return run


def test_recording_disposition_without_a_session_is_401(client: TestClient) -> None:
    response = client.post(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/export/disposition",
        data={"disposition": "as_generated"},
    )

    assert response.status_code == 401


def test_recording_disposition_for_an_unknown_run_is_404(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.post(
        "/report-runs/01a01abf-0000-7000-8000-000000000000/export/disposition",
        data={"disposition": "as_generated"},
    )

    assert response.status_code == 404


def test_recording_disposition_with_no_prior_export_is_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Recording, no prior export" -- a passed Report exists
    but has never been exported, so no ``ExportRecord`` row exists yet."""
    run = _passed_report_run(db_session)

    response = authenticated_client.post(
        f"/report-runs/{run.id}/export/disposition", data={"disposition": "as_generated"}
    )

    assert response.status_code == 404


def test_recording_an_invalid_disposition_with_no_prior_export_is_422_not_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Pins the precedence between the route's two error paths: an invalid
    ``disposition`` value is rejected with 422 before the route ever checks
    whether an ``ExportRecord`` exists, even against a run that has never
    been exported (which would otherwise 404 on its own, per the test
    above)."""
    run = _passed_report_run(db_session)

    response = authenticated_client.post(
        f"/report-runs/{run.id}/export/disposition", data={"disposition": "bogus"}
    )

    assert response.status_code == 422
    assert _export_records(db_session) == []


def test_recording_an_invalid_disposition_value_is_422(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Boundaries: exactly two disposition values -- never a third or free
    text."""
    run = _passed_report_run(db_session)
    authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    response = authenticated_client.post(
        f"/report-runs/{run.id}/export/disposition", data={"disposition": "bogus"}
    )

    assert response.status_code == 422
    assert _export_records(db_session)[0].disposition is None


def test_recording_disposition_the_first_time_redirects_and_sets_it(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Recording, first time" -- redirects to the Report view,
    and the latest ``ExportRecord.disposition`` is now set."""
    run = _passed_report_run(db_session)
    authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    response = authenticated_client.post(
        f"/report-runs/{run.id}/export/disposition",
        data={"disposition": "as_generated"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/report-runs/{run.id}/report"
    records = _export_records(db_session)
    assert len(records) == 1
    assert records[0].disposition == "as_generated"


def test_recording_disposition_a_second_time_is_a_no_op_and_still_redirects(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Recording, already set" -- idempotent, zero rows
    updated: the first recorded choice is never silently overwritten by a
    second, different one."""
    run = _passed_report_run(db_session)
    authenticated_client.get(f"/report-runs/{run.id}/export/pdf")
    authenticated_client.post(
        f"/report-runs/{run.id}/export/disposition", data={"disposition": "as_generated"}
    )

    response = authenticated_client.post(
        f"/report-runs/{run.id}/export/disposition",
        data={"disposition": "edited"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/report-runs/{run.id}/report"
    records = _export_records(db_session)
    assert len(records) == 1
    assert records[0].disposition == "as_generated"


def test_recording_disposition_acts_on_the_latest_export(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Two exports have happened; recording disposition sets it on the
    latest ``ExportRecord``, never the first."""
    run = _passed_report_run(db_session)
    authenticated_client.get(f"/report-runs/{run.id}/export/pdf")
    authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    response = authenticated_client.post(
        f"/report-runs/{run.id}/export/disposition", data={"disposition": "edited"}
    )

    assert response.status_code == 200  # TestClient follows the redirect by default
    records = sorted(_export_records(db_session), key=lambda record: record.created_at)
    assert len(records) == 2
    assert records[0].disposition is None
    assert records[1].disposition == "edited"


# --- Story 6.3: the disposition UI on report.html -----------------------------------


def test_the_report_view_has_no_disposition_ui_before_any_export(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Report view, no export yet" -- neither the disposition
    forms nor a recorded-disposition line render."""
    run = _passed_report_run(db_session)

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    assert 'id="disposition"' not in response.text
    assert "Sent as generated" not in response.text
    assert "Sent, edited first" not in response.text


def test_the_report_view_shows_both_disposition_forms_once_exported(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Report view, disposition pending" -- both one-click
    forms render."""
    run = _passed_report_run(db_session)
    authenticated_client.get(f"/report-runs/{run.id}/export/pdf")

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    assert "Sent as generated" in response.text
    assert "Sent, edited first" in response.text
    assert response.text.count(f'action="/report-runs/{run.id}/export/disposition"') == 2


def test_the_report_view_shows_the_recorded_disposition_and_hides_the_forms(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: "Report view, disposition recorded" -- the recorded
    choice is shown as text, with no buttons to silently overwrite it."""
    run = _passed_report_run(db_session)
    authenticated_client.get(f"/report-runs/{run.id}/export/pdf")
    authenticated_client.post(
        f"/report-runs/{run.id}/export/disposition", data={"disposition": "as_generated"}
    )

    response = authenticated_client.get(f"/report-runs/{run.id}/report")

    assert response.status_code == 200
    assert "Sent as generated" in response.text
    assert "Sent, edited first" not in response.text
    disposition_section = response.text.split('id="disposition"')[1].split("</div>")[0]
    assert "<form" not in disposition_section
    assert "<button" not in disposition_section
