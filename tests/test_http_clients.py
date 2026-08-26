"""``/clients`` -- one test per row of the story's I/O & Edge-Case Matrix,
plus authentication and the explicit-choice/no-cache-write contract.

The ``Geocoder`` is a fake throughout (``get_geocoder`` is overridden), so
these tests exercise the route's orchestration -- validation, resolution
branching, chart computation, one-transaction persistence -- without a real
network call or the real timezone dataset. Real ``NominatimGeocoder``
resolution behavior is ``tests/test_geocoder_nominatim.py``'s job; real
``compute_natal_chart()`` behavior is ``tests/test_natal_chart.py``'s.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as time_of_day
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from core.errors import EphemerisIntegrityError, PlaceResolutionError
from core.types.chart import Aspect, HouseCusp, NatalChart, PlanetPosition
from core.types.place import PlaceCandidate, ResolvedPlace
from shell.adapters.postgres.client import (
    Client,
    StoredNatalChart,
    correct_client_and_chart,
    create_client_with_chart,
)
from shell.adapters.postgres.report import store_report
from shell.adapters.postgres.report_run import ReportRun
from shell.config import Environment, Settings
from shell.http.app import create_app, get_session
from shell.http.auth import SESSION_COOKIE_NAME, sign_session
from shell.http.routes import clients as clients_module
from shell.http.routes.clients import get_geocoder

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

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same real,
# known-good input tests/test_natal_chart.py and tests/test_client_store.py
# already use.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)

_VALID_FORM = {
    "name": "Ada Lovelace",
    "birth_date": "2026-01-01",
    "birth_time": "00:00",
    "birthplace": "Fort Worth, TX",
}

#: A canned chart standing in for a real ``compute_natal_chart()`` call.
#: Real computation (real ephemeris, real house math) is
#: tests/test_natal_chart.py's job; these HTTP tests only need to prove the
#: route calls `compute_natal_chart()` and persists whatever it returns.
_FAKE_NATAL_CHART = NatalChart(
    ascendant=Decimal("183.0381"),
    midheaven=Decimal("93.0381"),
    planets=(
        PlanetPosition(
            name="sun",
            longitude=Decimal("280.5"),
            sign="capricorn",
            degree=Decimal("10.5"),
            house=4,
            retrograde=False,
        ),
    ),
    houses=(HouseCusp(number=1, longitude=Decimal("183.0381")),),
    aspects=(
        Aspect(body1="sun", body2="moon", aspect="trine", orb=Decimal("1.25"), applying=True),
    ),
)


@dataclass
class _FakeGeocoder:
    """Records every call so "the geocoder was/was not asked again" claims
    are provable rather than assumed."""

    resolve_result: ResolvedPlace | list[PlaceCandidate] | Exception | None = None
    resolve_candidate_result: ResolvedPlace | Exception | None = None
    resolve_calls: list[tuple[str, datetime]] = field(default_factory=list)
    resolve_candidate_calls: list[tuple[PlaceCandidate, datetime]] = field(default_factory=list)

    def resolve(
        self, place_text: str, birth_local_time: datetime
    ) -> ResolvedPlace | list[PlaceCandidate]:
        self.resolve_calls.append((place_text, birth_local_time))
        if isinstance(self.resolve_result, Exception):
            raise self.resolve_result
        assert self.resolve_result is not None
        return self.resolve_result

    def resolve_candidate(
        self, candidate: PlaceCandidate, birth_local_time: datetime
    ) -> ResolvedPlace:
        self.resolve_candidate_calls.append((candidate, birth_local_time))
        if isinstance(self.resolve_candidate_result, Exception):
            raise self.resolve_candidate_result
        assert self.resolve_candidate_result is not None
        return self.resolve_candidate_result


@pytest.fixture
def db_session() -> Session:
    # `check_same_thread=False` + `StaticPool`: `TestClient` dispatches the
    # ASGI app on its own worker thread, distinct from this fixture's thread
    # -- unlike tests/test_client_store.py's identical-looking fixture,
    # which never crosses a thread boundary. Without `StaticPool`, SQLite's
    # default per-thread pooling would hand the other thread a brand new,
    # empty ``:memory:`` database instead of this one.
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


def _use_geocoder(app_instance: FastAPI, geocoder: _FakeGeocoder) -> None:
    app_instance.dependency_overrides[get_geocoder] = lambda: geocoder


def _clients(db_session: Session) -> list[Client]:
    return list(db_session.exec(select(Client)))


def _charts(db_session: Session) -> list[StoredNatalChart]:
    return list(db_session.exec(select(StoredNatalChart)))


@pytest.fixture
def fake_chart_computation(monkeypatch: pytest.MonkeyPatch) -> NatalChart:
    """Stand in for a real ``compute_natal_chart()`` call, matching this
    module's own real-vs-fake boundary (see the module docstring). This also
    sidesteps a real, separate concern: Starlette's ``TestClient`` runs the
    ASGI app on its own worker thread, and pyswisseph's ``set_ephe_path()``
    pins the vendored ephemeris per-thread -- a real ``compute_natal_chart()``
    call from that thread would need its own ``verify_ephemeris_identity()``
    call, which is out of scope for a route-orchestration test.
    """
    monkeypatch.setattr(
        clients_module, "compute_natal_chart", lambda *args, **kwargs: _FAKE_NATAL_CHART
    )
    return _FAKE_NATAL_CHART


# --- Authentication -------------------------------------------------------------


def test_anonymous_get_is_rejected(client: TestClient) -> None:
    assert client.get("/clients/new").status_code == 401


def test_anonymous_post_is_rejected(client: TestClient) -> None:
    assert client.post("/clients", data=_VALID_FORM).status_code == 401


def test_the_form_is_served_to_an_authenticated_caller(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/clients/new")

    assert response.status_code == 200
    assert b"birthplace" in response.content.lower()


# --- Happy path -------------------------------------------------------------------


def test_all_fields_unambiguous_birthplace_persists_client_and_chart(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))

    response = authenticated_client.post("/clients", data=_VALID_FORM)

    assert response.status_code == 200, response.text
    assert "created" in response.text.lower()

    clients = _clients(db_session)
    charts = _charts(db_session)
    assert len(clients) == 1
    assert len(charts) == 1
    assert charts[0].client_id == clients[0].id
    assert clients[0].latitude == _LATITUDE
    assert clients[0].longitude == _LONGITUDE
    assert clients[0].iana_zone == "America/Chicago"


# --- Ambiguous birthplace ----------------------------------------------------------


def test_an_ambiguous_birthplace_shows_candidates_and_persists_nothing(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    candidates = [
        PlaceCandidate(
            display_name="Springfield, Illinois, USA",
            latitude=Decimal("39.7817"),
            longitude=Decimal("-89.6501"),
        ),
        PlaceCandidate(
            display_name="Springfield, Massachusetts, USA",
            latitude=Decimal("42.1015"),
            longitude=Decimal("-72.5898"),
        ),
    ]
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=candidates))
    form = {**_VALID_FORM, "birthplace": "Springfield"}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 200
    assert "Springfield, Illinois, USA" in response.text
    assert "Springfield, Massachusetts, USA" in response.text
    assert _clients(db_session) == []
    assert _charts(db_session) == []


def test_choosing_a_candidate_persists_and_never_re_queries_resolve(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    geocoder = _FakeGeocoder(resolve_candidate_result=_RESOLVED_PLACE)
    _use_geocoder(app_instance, geocoder)

    candidate_value = (
        '{"display_name": "Fort Worth, TX, USA", '
        '"latitude": "32.7358", "longitude": "-97.3453"}'
    )
    form = {**_VALID_FORM, "candidate": candidate_value}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 200, response.text
    assert len(_clients(db_session)) == 1
    assert geocoder.resolve_calls == [], "an explicit choice must never re-query resolve()"
    assert len(geocoder.resolve_candidate_calls) == 1


# --- Missing/blank required field --------------------------------------------------


@pytest.mark.parametrize("missing_field", ["name", "birth_date", "birth_time", "birthplace"])
def test_a_missing_required_field_is_refused_naming_it(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    missing_field: str,
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))
    form = {key: value for key, value in _VALID_FORM.items() if key != missing_field}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 422
    assert missing_field in response.text
    assert _clients(db_session) == []


def test_a_blank_required_field_is_refused(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))
    form = {**_VALID_FORM, "birth_time": "   "}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 422
    assert _clients(db_session) == []


# --- Oversized name (deferred-work item 41) -----------------------------------------


def test_a_name_at_the_maximum_length_is_accepted(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))
    form = {**_VALID_FORM, "name": "A" * 200}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 200, response.text
    clients = _clients(db_session)
    assert len(clients) == 1
    assert clients[0].name == "A" * 200


def test_an_oversized_name_is_refused_naming_it(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))
    form = {**_VALID_FORM, "name": "A" * 201}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 422
    assert "name" in response.text
    assert _clients(db_session) == []


# --- Malformed request body ----------------------------------------------------------


def test_an_oversized_body_is_refused(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))
    form = {**_VALID_FORM, "birthplace": "X" * 100_000}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 422
    assert _clients(db_session) == []


def test_a_non_utf8_body_is_refused(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))

    response = authenticated_client.post(
        "/clients",
        content=b"name=Ada&birth_date=2026-01-01&birth_time=00:00&birthplace=\xff\xfe",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 422
    assert _clients(db_session) == []


# --- Unparsable birth_date/birth_time ---------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [("birth_date", "not-a-date"), ("birth_time", "not-a-time")],
)
def test_an_unparsable_date_or_time_field_is_refused_naming_it(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    field: str,
    value: str,
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))
    form = {**_VALID_FORM, field: value}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 422
    assert f"{field} is invalid" in response.text
    assert _clients(db_session) == []


# --- Malformed resubmitted candidate ------------------------------------------------------


def test_a_malformed_candidate_is_refused(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    geocoder = _FakeGeocoder(resolve_candidate_result=_RESOLVED_PLACE)
    _use_geocoder(app_instance, geocoder)
    form = {**_VALID_FORM, "candidate": "not-json"}

    response = authenticated_client.post("/clients", data=form)

    assert response.status_code == 422
    assert "candidate" in response.text.lower()
    assert _clients(db_session) == []
    assert geocoder.resolve_candidate_calls == []


# --- Resolution failure -------------------------------------------------------------


def test_a_resolution_failure_is_refused_naming_the_step(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    _use_geocoder(
        app_instance,
        _FakeGeocoder(resolve_result=PlaceResolutionError("geocoding", "no match")),
    )

    response = authenticated_client.post("/clients", data=_VALID_FORM)

    assert response.status_code == 422
    assert "geocoding" in response.text
    assert _clients(db_session) == []
    assert _charts(db_session) == []


# --- Chart computation failure --------------------------------------------------------


def test_a_chart_computation_failure_is_refused_and_persists_no_partial_client(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))

    def _raise(*args: object, **kwargs: object) -> None:
        raise EphemerisIntegrityError("simulated ephemeris failure")

    monkeypatch.setattr(clients_module, "compute_natal_chart", _raise)

    response = authenticated_client.post("/clients", data=_VALID_FORM)

    assert response.status_code == 422
    assert "simulated ephemeris failure" in response.text
    assert _clients(db_session) == []
    assert _charts(db_session) == []


# --- Duplicate name -------------------------------------------------------------------


def test_two_clients_with_the_same_name_both_persist_as_distinct_rows(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))

    first = authenticated_client.post("/clients", data=_VALID_FORM)
    second = authenticated_client.post("/clients", data=_VALID_FORM)

    assert first.status_code == 200 and second.status_code == 200
    clients = _clients(db_session)
    assert len(clients) == 2
    assert clients[0].id != clients[1].id
    assert {c.name for c in clients} == {"Ada Lovelace"}


# --- ComputationConfig/EphemerisIdentity recorded --------------------------------------


def test_the_stored_chart_records_computation_config_and_ephemeris_identity(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_RESOLVED_PLACE))

    response = authenticated_client.post("/clients", data=_VALID_FORM)
    assert response.status_code == 200, response.text

    chart = _charts(db_session)[0]
    assert chart.computation_config_version == app_instance.state.computation_config.version
    assert (
        chart.computation_config_content_hash
        == app_instance.state.computation_config.content_hash
    )
    assert {f["filename"] for f in chart.ephemeris_files} == {
        f.filename for f in app_instance.state.ephemeris_identity.files
    }


# --- GET /clients/{client_id}/reports (Story 6.4) ----------------------------------


def _create_client_with_chart(
    app_instance: FastAPI, db_session: Session, *, name: str = "Ada Lovelace"
) -> tuple[Client, StoredNatalChart]:
    """A Client with a real, persisted ``StoredNatalChart`` -- built directly
    (bypassing the ``/clients`` route) since these tests exercise the
    listing route's own query, never chart computation itself."""
    client_row = create_client_with_chart(
        db_session,
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=time_of_day(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=_FAKE_NATAL_CHART,
        computation_config=app_instance.state.computation_config,
        ephemeris_identity=app_instance.state.ephemeris_identity,
    )
    db_session.commit()
    chart = db_session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client_row.id)
    ).one()
    return client_row, chart


def _create_passed_report(
    db_session: Session, *, client_id, month: str, natal_chart_id=None
) -> ReportRun:
    """A ``ReportRun`` at ``gate_passed`` plus its ``Report`` row -- the
    listing route joins on ``Report``, so no ``ReportDraft``/``ReportPayload``
    row is needed to exercise it."""
    run = ReportRun(
        client_id=client_id, month=month, stage="gate_passed", natal_chart_id=natal_chart_id
    )
    db_session.add(run)
    db_session.commit()
    store_report(
        db_session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
    )
    db_session.commit()
    return run


def test_getting_the_reports_list_without_a_session_is_401(client: TestClient) -> None:
    response = client.get("/clients/01a01abf-0000-7000-8000-000000000000/reports")

    assert response.status_code == 401


def test_the_reports_list_for_an_unknown_client_is_404(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get(
        "/clients/01a01abf-0000-7000-8000-000000000000/reports"
    )

    assert response.status_code == 404


def test_a_client_with_no_reports_shows_an_empty_list(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    ada, _chart = _create_client_with_chart(app_instance, db_session)

    response = authenticated_client.get(f"/clients/{ada.id}/reports")

    assert response.status_code == 200
    assert "No Reports" in response.text


def test_a_client_with_several_reports_lists_them_by_month_most_recent_first(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    ada, chart = _create_client_with_chart(app_instance, db_session)
    _create_passed_report(db_session, client_id=ada.id, month="2026-01", natal_chart_id=chart.id)
    _create_passed_report(db_session, client_id=ada.id, month="2026-03", natal_chart_id=chart.id)
    _create_passed_report(db_session, client_id=ada.id, month="2026-02", natal_chart_id=chart.id)

    response = authenticated_client.get(f"/clients/{ada.id}/reports")

    assert response.status_code == 200
    positions = [response.text.index(month) for month in ("2026-03", "2026-02", "2026-01")]
    assert positions == sorted(positions), "months must be listed most recent first"


def test_reopening_a_listed_report_reaches_the_existing_report_route(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    ada, chart = _create_client_with_chart(app_instance, db_session)
    run = _create_passed_report(
        db_session, client_id=ada.id, month="2026-01", natal_chart_id=chart.id
    )

    response = authenticated_client.get(f"/clients/{ada.id}/reports")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/report"' in response.text


def test_a_report_run_that_never_passed_the_gate_is_not_listed(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    ada, chart = _create_client_with_chart(app_instance, db_session)
    unpassed = ReportRun(
        client_id=ada.id, month="2026-01", stage="draft_ready", natal_chart_id=chart.id
    )
    db_session.add(unpassed)
    db_session.commit()

    response = authenticated_client.get(f"/clients/{ada.id}/reports")

    assert response.status_code == 200
    assert "2026-01" not in response.text


def test_a_report_against_a_superseded_chart_is_marked_but_still_opens(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    ada, original_chart = _create_client_with_chart(app_instance, db_session)
    run = _create_passed_report(
        db_session, client_id=ada.id, month="2026-01", natal_chart_id=original_chart.id
    )

    # Supersede the chart the run was generated against (Story 2.7).
    correct_client_and_chart(
        db_session,
        client=ada,
        name=ada.name,
        birth_date=ada.birth_date,
        birth_time=ada.birth_time,
        resolved_place=_RESOLVED_PLACE,
        natal_chart=_FAKE_NATAL_CHART,
        computation_config=app_instance.state.computation_config,
        ephemeris_identity=app_instance.state.ephemeris_identity,
    )
    db_session.commit()
    assert db_session.get(StoredNatalChart, original_chart.id).superseded_at is not None, (
        "fixture did not supersede the chart -- test is vacuous"
    )

    response = authenticated_client.get(f"/clients/{ada.id}/reports")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/report"' in response.text
    assert "superseded" in response.text.lower()


def test_a_pre_migration_report_with_no_recorded_chart_is_not_marked_superseded(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    """Matrix row: "Pre-migration Report" -- ``ReportRun.natal_chart_id`` is
    ``NULL`` (a run driven before this story, or one that never reached
    ``natal_ready``), so whether its chart was ever superseded is
    undeterminable -- never marked, not even a false positive."""
    ada, _chart = _create_client_with_chart(app_instance, db_session)
    run = _create_passed_report(
        db_session, client_id=ada.id, month="2026-01", natal_chart_id=None
    )

    response = authenticated_client.get(f"/clients/{ada.id}/reports")

    assert response.status_code == 200
    assert f'href="/report-runs/{run.id}/report"' in response.text
    assert "superseded" not in response.text.lower()


def test_the_reports_list_is_scoped_per_client(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    ada, ada_chart = _create_client_with_chart(app_instance, db_session, name="Ada Lovelace")
    grace, grace_chart = _create_client_with_chart(app_instance, db_session, name="Grace Hopper")
    _create_passed_report(
        db_session, client_id=ada.id, month="2026-01", natal_chart_id=ada_chart.id
    )
    _create_passed_report(
        db_session, client_id=grace.id, month="2026-05", natal_chart_id=grace_chart.id
    )

    ada_response = authenticated_client.get(f"/clients/{ada.id}/reports")
    grace_response = authenticated_client.get(f"/clients/{grace.id}/reports")

    assert "2026-01" in ada_response.text
    assert "2026-05" not in ada_response.text
    assert "2026-05" in grace_response.text
    assert "2026-01" not in grace_response.text
