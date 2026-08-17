"""``/clients/{id}/edit`` -- one test per row of Story 2.7's I/O & Edge-Case
Matrix, plus its Acceptance Criteria and the cross-story regression that
``GET /clients/{id}/chart`` reflects a corrected chart.

The ``Geocoder`` is a fake throughout (``get_geocoder`` is overridden), and
``compute_natal_chart`` is monkeypatched on the ``clients`` route module --
mirrors ``tests/test_http_clients.py``'s own fixtures and its docstring's
reasoning: ``TestClient`` dispatches the ASGI app on its own worker thread,
and a real ``compute_natal_chart()`` call from that thread would need its own
``verify_ephemeris_identity()`` call, out of scope for a route-orchestration
test. Charts built here always carry all twelve house cusps and every planet
this project computes -- ``AstrologicalSubjectModel``'s house fields are
required -- since the cross-story regression test renders the corrected chart
through ``GET /clients/{id}/chart``, which builds its Kerykeion subject
directly from whatever is stored (Story 2.6), never by recomputing.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from core.errors import EphemerisIntegrityError, PlaceResolutionError
from core.types.chart import Aspect, HouseCusp, NatalChart, PlanetPosition
from core.types.place import PlaceCandidate, ResolvedPlace
from shell.adapters.postgres.client import Client, StoredNatalChart, create_client_with_chart
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
)

# The Client's original birth data/place -- Fort Worth, TX, mirroring
# tests/test_http_clients.py and tests/test_http_chart_wheel.py's own fixture.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)

# The corrected birth data/place -- a different city, so a correction that
# changes birthplace is provably reflected (AC3).
_NEW_LATITUDE = Decimal("40.7128")
_NEW_LONGITUDE = Decimal("-74.0060")
_NEW_RESOLVED_PLACE = ResolvedPlace(
    latitude=_NEW_LATITUDE,
    longitude=_NEW_LONGITUDE,
    iana_zone="America/New_York",
    utc_offset=timedelta(hours=-5),
)

_VALID_FORM = {
    "name": "Ada Lovelace",
    "birth_date": "2026-01-01",
    "birth_time": "00:00",
    "birthplace": "Fort Worth, TX",
}

_CORRECTION_FORM = {
    "name": "Ada Corrected",
    "birth_date": "2026-01-01",
    "birth_time": "06:00",
    "birthplace": "New York, NY",
}

#: The ten planets, the True Node and the South Node -- every body this
#: project's Natal Chart computes (core/types/chart.py's own docstring).
_STORED_PLANET_NAMES: tuple[str, ...] = (
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
    "true_node",
    "south_node",
)


def _build_natal_chart(base_longitude: Decimal) -> NatalChart:
    """A fully-populated, internally-consistent-enough ``NatalChart`` for
    rendering through ``chart_wheel.build_subject()`` -- every planet this
    project computes, all twelve house cusps, spaced out from
    ``base_longitude`` so two charts built from different bases render
    visibly different SVGs.
    """
    # `+ 5`: nudged off every house cusp below (spaced every 30 degrees from
    # `base_longitude`) so no planet lands exactly on the Ascendant or another
    # cusp -- ChartDrawer skips a slug placed exactly atop another one.
    planets = tuple(
        PlanetPosition(
            name=name,
            longitude=(base_longitude + Decimal(15 * index) + Decimal(5)) % Decimal(360),
            sign="aries",
            degree=Decimal("1.0"),
            house=(index % 12) + 1,
            retrograde=False,
        )
        for index, name in enumerate(_STORED_PLANET_NAMES)
    )
    houses = tuple(
        HouseCusp(
            number=number,
            longitude=(base_longitude + Decimal(30 * (number - 1))) % Decimal(360),
        )
        for number in range(1, 13)
    )
    return NatalChart(
        ascendant=houses[0].longitude,
        midheaven=houses[9].longitude,
        planets=planets,
        houses=houses,
        aspects=(
            Aspect(body1="sun", body2="moon", aspect="trine", orb=Decimal("1.25"), applying=True),
        ),
    )


_OLD_NATAL_CHART = _build_natal_chart(Decimal("10.0"))
_NEW_NATAL_CHART = _build_natal_chart(Decimal("100.0"))


@dataclass
class _FakeGeocoder:
    """Records every call so "the geocoder was/was not asked again" claims
    are provable rather than assumed (mirrors tests/test_http_clients.py)."""

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
    # ASGI app on its own worker thread, distinct from this fixture's thread.
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
def fake_chart_computation(monkeypatch: pytest.MonkeyPatch) -> NatalChart:
    """Stand in for a real ``compute_natal_chart()`` call during a
    correction POST -- see this module's own docstring for why."""
    monkeypatch.setattr(
        clients_module, "compute_natal_chart", lambda *args, **kwargs: _NEW_NATAL_CHART
    )
    return _NEW_NATAL_CHART


def _use_geocoder(app_instance: FastAPI, geocoder: _FakeGeocoder) -> None:
    app_instance.dependency_overrides[get_geocoder] = lambda: geocoder


def _seed_client_with_chart(
    db_session: Session, app_instance: FastAPI, *, name: str = "Ada Lovelace"
) -> Client:
    """A Client with one current ``StoredNatalChart`` row, persisted directly
    (not through the HTTP route) so every correction test starts from a known
    state -- mirrors tests/test_http_chart_wheel.py's own seeding helper.
    """
    client = create_client_with_chart(
        db_session,
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=dt_time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=_OLD_NATAL_CHART,
        computation_config=app_instance.state.computation_config,
        ephemeris_identity=app_instance.state.ephemeris_identity,
    )
    db_session.commit()
    return client


def _charts_for(db_session: Session, client_id) -> list[StoredNatalChart]:
    return list(
        db_session.exec(select(StoredNatalChart).where(StoredNatalChart.client_id == client_id))
    )


def _rendered_abs_pos(body: str, slug: str) -> float:
    """Mirrors tests/test_http_chart_wheel.py's own helper: Kerykeion's
    ``kr:absoluteposition`` attribute for the ``kr:slug`` element named
    ``slug``, matched in the SVG's single-quoted form (``ChartDrawer``
    rewrites all double quotes to single quotes before returning it)."""
    match = re.search(rf"kr:absoluteposition='([^']+)'[^>]*kr:slug='{re.escape(slug)}'", body)
    assert match is not None, slug
    return float(match.group(1))


# --- Authentication -------------------------------------------------------------


def test_anonymous_get_edit_is_rejected(
    client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)
    assert client.get(f"/clients/{seeded.id}/edit").status_code == 401


def test_anonymous_post_edit_is_rejected(
    client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)
    assert client.post(f"/clients/{seeded.id}/edit", data=_CORRECTION_FORM).status_code == 401


# --- Prefilled edit form ----------------------------------------------------------


def test_the_edit_form_is_prefilled_from_the_client_row_and_birthplace_is_blank(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)

    response = authenticated_client.get(f"/clients/{seeded.id}/edit")

    assert response.status_code == 200
    body = response.text
    assert 'value="Ada Lovelace"' in body
    assert 'value="2026-01-01"' in body
    assert 'value="00:00"' in body

    birthplace_value = re.search(r'name="birthplace"[^>]*value="([^"]*)"', body)
    assert birthplace_value is not None
    assert birthplace_value.group(1) == ""


# --- Unknown client id -------------------------------------------------------------


def test_get_edit_for_an_unknown_client_id_is_a_plain_404(
    authenticated_client: TestClient,
) -> None:
    assert authenticated_client.get(f"/clients/{uuid4()}/edit").status_code == 404


def test_post_edit_for_an_unknown_client_id_is_a_plain_404(
    authenticated_client: TestClient, app_instance: FastAPI
) -> None:
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_NEW_RESOLVED_PLACE))
    response = authenticated_client.post(f"/clients/{uuid4()}/edit", data=_CORRECTION_FORM)
    assert response.status_code == 404


# --- Unconfirmed correction ---------------------------------------------------------


def test_unconfirmed_correction_shows_a_warning_and_persists_nothing(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_NEW_RESOLVED_PLACE))

    response = authenticated_client.post(f"/clients/{seeded.id}/edit", data=_CORRECTION_FORM)

    assert response.status_code == 200
    assert "supersede" in response.text.lower()
    assert 'value="Ada Corrected"' in response.text
    assert 'name="confirmed"' in response.text

    db_session.refresh(seeded)
    assert seeded.name == "Ada Lovelace"
    charts = _charts_for(db_session, seeded.id)
    assert len(charts) == 1
    assert charts[0].superseded_at is None


# --- Confirmed correction ------------------------------------------------------------


def test_confirmed_correction_supersedes_the_old_chart_and_updates_the_client(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)
    old_chart_id = _charts_for(db_session, seeded.id)[0].id
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_NEW_RESOLVED_PLACE))

    form = {**_CORRECTION_FORM, "confirmed": "1"}
    response = authenticated_client.post(f"/clients/{seeded.id}/edit", data=form)

    assert response.status_code == 200, response.text
    assert "corrected" in response.text.lower()

    charts = _charts_for(db_session, seeded.id)
    assert len(charts) == 2
    old_chart = next(c for c in charts if c.id == old_chart_id)
    assert old_chart.superseded_at is not None
    current_charts = [c for c in charts if c.superseded_at is None]
    assert len(current_charts) == 1
    assert current_charts[0].id != old_chart_id

    db_session.refresh(seeded)
    assert seeded.name == "Ada Corrected"
    assert seeded.birth_time == dt_time(6, 0)
    assert seeded.latitude == _NEW_LATITUDE
    assert seeded.longitude == _NEW_LONGITUDE
    assert seeded.iana_zone == "America/New_York"


# --- Ambiguous birthplace ------------------------------------------------------------


def test_ambiguous_birthplace_shows_the_candidate_picker_and_persists_nothing(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)
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
    form = {**_CORRECTION_FORM, "birthplace": "Springfield"}

    response = authenticated_client.post(f"/clients/{seeded.id}/edit", data=form)

    assert response.status_code == 200
    assert "Springfield, Illinois, USA" in response.text
    assert "Springfield, Massachusetts, USA" in response.text
    assert "supersede" not in response.text.lower()
    assert len(_charts_for(db_session, seeded.id)) == 1


# --- Resolution failure ----------------------------------------------------------------


def test_a_resolution_failure_is_refused_naming_the_step_and_persists_nothing(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)
    _use_geocoder(
        app_instance,
        _FakeGeocoder(resolve_result=PlaceResolutionError("geocoding", "no match")),
    )

    response = authenticated_client.post(f"/clients/{seeded.id}/edit", data=_CORRECTION_FORM)

    assert response.status_code == 422
    assert "geocoding" in response.text

    db_session.refresh(seeded)
    assert seeded.name == "Ada Lovelace"
    charts = _charts_for(db_session, seeded.id)
    assert len(charts) == 1
    assert charts[0].superseded_at is None


# --- Chart computation failure -----------------------------------------------------------


def test_a_chart_computation_failure_is_refused_and_the_old_chart_stays_current(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)
    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_NEW_RESOLVED_PLACE))

    def _raise(*args: object, **kwargs: object) -> None:
        raise EphemerisIntegrityError("simulated ephemeris failure")

    monkeypatch.setattr(clients_module, "compute_natal_chart", _raise)

    response = authenticated_client.post(f"/clients/{seeded.id}/edit", data=_CORRECTION_FORM)

    assert response.status_code == 422
    assert "simulated ephemeris failure" in response.text
    charts = _charts_for(db_session, seeded.id)
    assert len(charts) == 1
    assert charts[0].superseded_at is None


# --- Unchanged birthplace text (cache-hit-equivalent) ---------------------------------------


def test_unchanged_birthplace_text_resolves_again_on_confirm_and_the_correction_applies(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)
    geocoder = _FakeGeocoder(resolve_result=_RESOLVED_PLACE)
    _use_geocoder(app_instance, geocoder)

    form = {**_CORRECTION_FORM, "birthplace": "Fort Worth, TX"}
    warning_response = authenticated_client.post(f"/clients/{seeded.id}/edit", data=form)
    assert warning_response.status_code == 200
    assert "supersede" in warning_response.text.lower()

    confirm_form = {**form, "confirmed": "1"}
    confirm_response = authenticated_client.post(f"/clients/{seeded.id}/edit", data=confirm_form)

    assert confirm_response.status_code == 200, confirm_response.text
    assert len(geocoder.resolve_calls) == 2
    assert all(call[0] == "Fort Worth, TX" for call in geocoder.resolve_calls)
    assert len(_charts_for(db_session, seeded.id)) == 2


# --- AC: no correction ever submitted => no second chart row --------------------------------


def test_viewing_the_edit_form_or_the_chart_never_creates_a_second_chart_row(
    authenticated_client: TestClient, app_instance: FastAPI, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)

    authenticated_client.get(f"/clients/{seeded.id}/edit")
    authenticated_client.get(f"/clients/{seeded.id}/chart")

    assert len(_charts_for(db_session, seeded.id)) == 1


# --- Cross-story regression: the chart route reflects a confirmed correction ----------------


def test_after_a_confirmed_correction_the_chart_route_reflects_the_new_chart(
    authenticated_client: TestClient,
    app_instance: FastAPI,
    db_session: Session,
    fake_chart_computation: NatalChart,
) -> None:
    seeded = _seed_client_with_chart(db_session, app_instance)

    before = authenticated_client.get(f"/clients/{seeded.id}/chart")
    assert before.status_code == 200
    assert _rendered_abs_pos(before.text, "Sun") == pytest.approx(
        float(_OLD_NATAL_CHART.planets[0].longitude)
    )

    _use_geocoder(app_instance, _FakeGeocoder(resolve_result=_NEW_RESOLVED_PLACE))
    form = {**_CORRECTION_FORM, "confirmed": "1"}
    correction_response = authenticated_client.post(f"/clients/{seeded.id}/edit", data=form)
    assert correction_response.status_code == 200, correction_response.text

    after = authenticated_client.get(f"/clients/{seeded.id}/chart")
    assert after.status_code == 200
    assert _rendered_abs_pos(after.text, "Sun") == pytest.approx(
        float(_NEW_NATAL_CHART.planets[0].longitude)
    )
    assert _rendered_abs_pos(after.text, "Sun") != pytest.approx(
        float(_OLD_NATAL_CHART.planets[0].longitude)
    )
