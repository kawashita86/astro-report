"""``GET /clients/{client_id}/chart`` -- one test per row of the story's I/O &
Edge-Case Matrix (Story 2.6), plus a direct unit test on
``chart_wheel.build_subject()``'s retrograde mapping.

Real ``compute_natal_chart()`` + real ``create_client_with_chart()`` populate
the stored chart these tests read -- mirrors ``tests/test_client_store.py``'s
own fixture, rather than hand-inventing a ``StoredNatalChart``'s JSON shape.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import Client, StoredNatalChart, create_client_with_chart
from shell.computation import load_computation_config
from shell.config import Environment, Settings
from shell.http import chart_wheel
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

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same real,
# known-good input tests/test_natal_chart.py and tests/test_client_store.py
# already use. Jupiter and Uranus are both retrograde at this real instant,
# so this one fixture also covers the "Retrograde planet" I/O matrix row
# without a synthetic chart.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)

#: Every Kerykeion `AstrologicalPoint` this project's Natal Chart maps a
#: planet onto (the story's body-name mapping).
_PLANET_KERYKEION_NAMES: tuple[str, ...] = (
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
    "True_North_Lunar_Node",
    "True_South_Lunar_Node",
)

_HOUSE_SLUGS: tuple[str, ...] = (
    "First_House",
    "Second_House",
    "Third_House",
    "Fourth_House",
    "Fifth_House",
    "Sixth_House",
    "Seventh_House",
    "Eighth_House",
    "Ninth_House",
    "Tenth_House",
    "Eleventh_House",
    "Twelfth_House",
)


def _rendered_abs_pos(body: str, slug: str) -> float:
    """Kerykeion's own ``kr:absoluteposition`` attribute for the ``kr:slug``
    element named ``slug`` (a planet's or house cusp's ``ChartPoint``/``Cusp``
    ``<g>`` element -- see ``.venv/lib/python3.13/site-packages/kerykeion/
    charts/draw_modern.py``, which always writes ``kr:absoluteposition``
    before ``kr:slug`` on the same tag). ``ChartDrawer.generate_svg_string()``
    rewrites all double quotes to single quotes before returning the SVG
    string (``chart_drawer.py``'s ``template.replace('"', "'")``), so the
    attributes are matched in that same single-quoted form here.
    """
    match = re.search(rf"kr:absoluteposition='([^']+)'[^>]*kr:slug='{re.escape(slug)}'", body)
    assert match is not None, slug
    return float(match.group(1))


def _natal_chart():
    return compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG)


def _seed_client_with_chart(session: Session, *, name: str = "Ada Lovelace") -> Client:
    client = create_client_with_chart(
        session,
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=dt_time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=_natal_chart(),
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    session.commit()
    return client


@pytest.fixture
def db_session() -> Session:
    # `check_same_thread=False` + `StaticPool`: `TestClient` dispatches the
    # ASGI app on its own worker thread, mirroring
    # tests/test_http_clients.py's identical fixture.
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


# --- Client with a stored chart -----------------------------------------------------


def test_a_client_with_a_stored_chart_shows_the_wheel(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)

    response = authenticated_client.get(f"/clients/{seeded.id}/chart")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "<svg" in body

    # Every planet this project computes is placed on the wheel.
    for kerykeion_name in _PLANET_KERYKEION_NAMES:
        assert f"kr:slug='{kerykeion_name}'" in body, kerykeion_name

    # All twelve Placidus house cusps.
    for house_slug in _HOUSE_SLUGS:
        assert f"kr:slug='{house_slug}'" in body, house_slug
    assert body.count("kr:node='HouseNumber'") == 12

    # The Ascendant/Medium Coeli angles: `build_subject()`'s
    # `active_points += ["Ascendant", "Medium_Coeli"]` wiring is the only
    # thing that puts them on the wheel -- if it were ever dropped or
    # misnamed, the angles would silently vanish with no other assertion
    # here catching it.
    assert "kr:slug='Ascendant'" in body
    assert "kr:slug='Medium_Coeli'" in body

    # Rendered positions actually match the stored chart -- a slug-presence
    # assertion alone would still pass under a swapped-index bug (e.g. two
    # house cusps swapped, or the wrong planet's longitude used) while every
    # position on the wheel is wrong, defeating the story's entire purpose
    # (Francesco eyeballing positions against Astro.com).
    stored_chart = db_session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == seeded.id)
    ).one()

    for stored_name, kerykeion_name in [("sun", "Sun"), ("moon", "Moon"), ("mercury", "Mercury")]:
        stored_planet = next(p for p in stored_chart.planets if p["name"] == stored_name)
        assert _rendered_abs_pos(body, kerykeion_name) == pytest.approx(
            float(stored_planet["longitude"]), abs=1e-6
        ), kerykeion_name

    for house_number, house_slug in [(1, "First_House"), (7, "Seventh_House")]:
        stored_house = next(h for h in stored_chart.houses if int(h["number"]) == house_number)
        assert _rendered_abs_pos(body, house_slug) == pytest.approx(
            float(stored_house["longitude"]), abs=1e-6
        ), house_slug

    # Natal Aspects: Kerykeion's own recomputation over the mapped positions
    # (the story's Design Notes), not a re-serialization of `chart.aspects`.
    assert "kr:node='Aspects_Wheel'" in body
    assert "kr:aspectname=" in body


# --- Client name is escaped in the rendered SVG ---------------------------------------


def test_a_client_name_with_markup_is_escaped_in_the_svg(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Kerykeion embeds `AstrologicalSubjectModel.name` verbatim, unescaped,
    into the generated SVG's own `<title>` element, and the route renders
    that SVG via `{{ svg | safe }}`, bypassing Jinja's autoescaping -- so a
    Client named with HTML/XML markup must never reach the browser as raw
    markup (stored XSS)."""
    seeded = _seed_client_with_chart(db_session, name="<script>alert(1)</script>")

    response = authenticated_client.get(f"/clients/{seeded.id}/chart")

    assert response.status_code == 200
    body = response.text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


# --- Unknown client id ---------------------------------------------------------------


def test_an_unknown_client_id_is_a_plain_404(authenticated_client: TestClient) -> None:
    response = authenticated_client.get(f"/clients/{uuid4()}/chart")

    assert response.status_code == 404


def test_a_client_with_no_stored_chart_is_a_plain_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    client_only = Client(
        name="No Chart Yet",
        birth_date=date(2026, 1, 1),
        birth_time=dt_time(0, 0),
        latitude=_LATITUDE,
        longitude=_LONGITUDE,
        iana_zone="America/Chicago",
    )
    db_session.add(client_only)
    db_session.commit()

    response = authenticated_client.get(f"/clients/{client_only.id}/chart")

    assert response.status_code == 404


# --- Unauthenticated request -----------------------------------------------------------


def test_an_unauthenticated_request_is_rejected(client: TestClient, db_session: Session) -> None:
    seeded = _seed_client_with_chart(db_session)

    response = client.get(f"/clients/{seeded.id}/chart")

    assert response.status_code == 401


# --- Retrograde planet -----------------------------------------------------------------


def test_a_retrograde_planet_carries_a_negative_speed(db_session: Session) -> None:
    """`chart_wheel.build_subject()`'s own mapping, exercised directly:
    Kerykeion's retrograde convention is a negative `speed`, not a separate
    flag (the I/O matrix's "Retrograde planet" row)."""
    seeded = _seed_client_with_chart(db_session)
    stored_chart = db_session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == seeded.id)
    ).one()
    retrograde_planets = [p for p in stored_chart.planets if p["retrograde"]]
    assert retrograde_planets, "fixture has no retrograde planet -- test is vacuous"

    subject = chart_wheel.build_subject(seeded, stored_chart)

    for planet in retrograde_planets:
        point_name = chart_wheel._kerykeion_point_name(planet["name"])
        point = getattr(subject, point_name.lower())
        assert point.speed is not None and point.speed < 0, point_name

    prograde_planets = [p for p in stored_chart.planets if not p["retrograde"]]
    assert prograde_planets, "fixture has no prograde planet -- test is vacuous"
    for planet in prograde_planets:
        point_name = chart_wheel._kerykeion_point_name(planet["name"])
        point = getattr(subject, point_name.lower())
        assert point.speed is not None and point.speed > 0, point_name
