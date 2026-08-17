"""``/clients/{id}/delete`` -- one test per row of Story 2.8's I/O & Edge-Case
Matrix, plus its Acceptance Criteria.

Mirrors ``tests/test_http_client_correction.py``'s own fixtures: an in-memory
SQLite engine (``StaticPool``, ``check_same_thread=False`` -- ``TestClient``
dispatches the ASGI app on its own worker thread), a Client seeded directly
through ``create_client_with_chart()``/``correct_client_and_chart()`` rather
than through the HTTP layer, and an authenticated ``TestClient``.
"""

from __future__ import annotations

import logging
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
from shell.adapters.postgres.client import (
    Client,
    StoredNatalChart,
    correct_client_and_chart,
    create_client_with_chart,
)
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

# Fort Worth, TX -- mirrors tests/test_http_client_correction.py's own fixture.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()
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


def _a_natal_chart():
    return compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG)


def _seed_client_with_chart(db_session: Session, *, name: str = "Ada Lovelace") -> Client:
    client_row = create_client_with_chart(
        db_session,
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=dt_time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=_a_natal_chart(),
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    db_session.commit()
    return client_row


def _supersede(db_session: Session, client_row: Client) -> None:
    """Give ``client_row`` a second, superseded chart (Story 2.7's shape)."""
    correct_client_and_chart(
        db_session,
        client=client_row,
        name=client_row.name,
        birth_date=client_row.birth_date,
        birth_time=client_row.birth_time,
        resolved_place=_RESOLVED_PLACE,
        natal_chart=_a_natal_chart(),
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    db_session.commit()


def _charts_for(db_session: Session, client_id) -> list[StoredNatalChart]:
    return list(
        db_session.exec(select(StoredNatalChart).where(StoredNatalChart.client_id == client_id))
    )


# --- Authentication -----------------------------------------------------------------


def test_anonymous_get_delete_is_rejected(client: TestClient, db_session: Session) -> None:
    seeded = _seed_client_with_chart(db_session)
    assert client.get(f"/clients/{seeded.id}/delete").status_code == 401


def test_anonymous_post_delete_is_rejected(client: TestClient, db_session: Session) -> None:
    seeded = _seed_client_with_chart(db_session)
    assert client.post(f"/clients/{seeded.id}/delete").status_code == 401


# --- Confirmation page ----------------------------------------------------------------


def test_the_confirmation_page_states_what_will_be_removed_and_deletes_nothing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)

    response = authenticated_client.get(f"/clients/{seeded.id}/delete")

    assert response.status_code == 200
    assert "Client" in response.text
    assert "chart" in response.text.lower()
    assert db_session.get(Client, seeded.id) is not None
    assert len(_charts_for(db_session, seeded.id)) == 1


def test_the_confirmation_page_mentions_a_superseded_chart_when_one_exists(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)
    _supersede(db_session, seeded)

    response = authenticated_client.get(f"/clients/{seeded.id}/delete")

    assert response.status_code == 200
    assert "superseded" in response.text.lower()
    assert len(_charts_for(db_session, seeded.id)) == 2


# --- Unconfirmed delete ---------------------------------------------------------------


def test_unconfirmed_delete_re_renders_the_confirmation_page_and_deletes_nothing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)

    response = authenticated_client.post(f"/clients/{seeded.id}/delete")

    assert response.status_code == 200
    assert db_session.get(Client, seeded.id) is not None
    assert len(_charts_for(db_session, seeded.id)) == 1


def test_unconfirmed_delete_still_mentions_a_superseded_chart_when_one_exists(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)
    _supersede(db_session, seeded)

    response = authenticated_client.post(f"/clients/{seeded.id}/delete")

    assert response.status_code == 200
    assert "superseded" in response.text.lower()
    assert len(_charts_for(db_session, seeded.id)) == 2


# --- Malformed body -------------------------------------------------------------------


def test_an_oversized_delete_body_is_refused(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)

    response = authenticated_client.post(
        f"/clients/{seeded.id}/delete", data={"confirmed": "1" + "X" * 100_000}
    )

    assert response.status_code == 422
    assert db_session.get(Client, seeded.id) is not None
    assert len(_charts_for(db_session, seeded.id)) == 1


def test_a_non_utf8_delete_body_is_refused(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)

    response = authenticated_client.post(
        f"/clients/{seeded.id}/delete",
        content=b"confirmed=1&garbage=\xff\xfe",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 422
    assert db_session.get(Client, seeded.id) is not None
    assert len(_charts_for(db_session, seeded.id)) == 1


# --- Confirmed delete, current chart only ----------------------------------------------


def test_confirmed_delete_removes_the_client_and_its_current_chart(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)

    response = authenticated_client.post(
        f"/clients/{seeded.id}/delete", data={"confirmed": "1"}
    )

    assert response.status_code == 200
    assert db_session.get(Client, seeded.id) is None
    assert _charts_for(db_session, seeded.id) == []


# --- Confirmed delete, superseded chart present -----------------------------------------


def test_confirmed_delete_removes_both_the_current_and_superseded_chart(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)
    _supersede(db_session, seeded)
    assert len(_charts_for(db_session, seeded.id)) == 2, "fixture is vacuous"

    response = authenticated_client.post(
        f"/clients/{seeded.id}/delete", data={"confirmed": "1"}
    )

    assert response.status_code == 200
    assert db_session.get(Client, seeded.id) is None
    assert _charts_for(db_session, seeded.id) == []


# --- Cross-client isolation --------------------------------------------------------------


def test_deleting_one_client_leaves_another_client_and_its_charts_untouched(
    authenticated_client: TestClient, db_session: Session
) -> None:
    doomed = _seed_client_with_chart(db_session, name="Ada Lovelace")
    _supersede(db_session, doomed)
    survivor = _seed_client_with_chart(db_session, name="Grace Hopper")
    _supersede(db_session, survivor)

    response = authenticated_client.post(
        f"/clients/{doomed.id}/delete", data={"confirmed": "1"}
    )

    assert response.status_code == 200
    assert db_session.get(Client, doomed.id) is None
    assert _charts_for(db_session, doomed.id) == []
    assert db_session.get(Client, survivor.id) is not None
    assert len(_charts_for(db_session, survivor.id)) == 2


# --- Double delete -----------------------------------------------------------------------


def test_a_second_confirmed_delete_of_the_same_client_is_a_plain_404(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)

    first = authenticated_client.post(f"/clients/{seeded.id}/delete", data={"confirmed": "1"})
    assert first.status_code == 200

    second = authenticated_client.post(f"/clients/{seeded.id}/delete", data={"confirmed": "1"})
    assert second.status_code == 404


# --- Unknown client id ------------------------------------------------------------------


def test_get_delete_for_an_unknown_client_id_is_a_plain_404(
    authenticated_client: TestClient,
) -> None:
    assert authenticated_client.get(f"/clients/{uuid4()}/delete").status_code == 404


def test_post_delete_for_an_unknown_client_id_is_a_plain_404(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.post(
        f"/clients/{uuid4()}/delete", data={"confirmed": "1"}
    )
    assert response.status_code == 404


# --- Post-delete read --------------------------------------------------------------------


def test_the_chart_route_404s_after_deletion(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_client_with_chart(db_session)

    delete_response = authenticated_client.post(
        f"/clients/{seeded.id}/delete", data={"confirmed": "1"}
    )
    assert delete_response.status_code == 200

    assert authenticated_client.get(f"/clients/{seeded.id}/chart").status_code == 404


# --- Deletion log line (AC) ---------------------------------------------------------------


def test_the_deletion_log_line_carries_only_the_client_id(
    authenticated_client: TestClient,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seeded = _seed_client_with_chart(db_session, name="Ada Lovelace")

    with caplog.at_level(logging.INFO):
        response = authenticated_client.post(
            f"/clients/{seeded.id}/delete", data={"confirmed": "1"}
        )
    assert response.status_code == 200

    messages = [record.getMessage() for record in caplog.records]
    matching = [message for message in messages if str(seeded.id) in message]
    assert matching, "no log line carried the deleted Client's id"
    for message in matching:
        assert "Ada Lovelace" not in message
        assert "2026-01-01" not in message
