"""``/corpus``, ``/corpus/new``, ``POST /corpus`` -- one test per row of
Story 7.1's I/O & Edge-Case Matrix, plus authentication. Mirrors
``tests/test_http_style_guide.py``'s fixture shape.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from shell.adapters.postgres.client import Client, delete_client_and_derived
from shell.adapters.postgres.corpus_entry import CorpusEntry
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


def _seed_entry(db_session: Session, *, content: str, created_at: datetime) -> CorpusEntry:
    entry = CorpusEntry(content=content, created_at=created_at)
    db_session.add(entry)
    db_session.commit()
    return entry


# --- Authentication -----------------------------------------------------------


def test_anonymous_get_list_is_rejected(client: TestClient) -> None:
    response = client.get("/corpus")

    assert response.status_code == 401
    assert response.content == b""


def test_anonymous_get_new_form_is_rejected(client: TestClient) -> None:
    response = client.get("/corpus/new")

    assert response.status_code == 401
    assert response.content == b""


def test_anonymous_post_is_rejected(client: TestClient, db_session: Session) -> None:
    response = client.post("/corpus", data={"content": "a past report"})

    assert response.status_code == 401
    assert response.content == b""
    assert db_session.exec(select(CorpusEntry)).all() == []


# --- Add an entry -----------------------------------------------------------


def test_posting_prose_inserts_one_unpaired_row_and_redirects(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus", data={"content": "Cara cliente, questo mese..."}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/corpus"

    rows = db_session.exec(select(CorpusEntry)).all()
    assert len(rows) == 1
    assert rows[0].content == "Cara cliente, questo mese..."
    assert rows[0].client_id is None


def test_a_posted_entry_then_appears_in_the_list(
    authenticated_client: TestClient,
) -> None:
    authenticated_client.post(
        "/corpus", data={"content": "A distinctive pasted sentence."}, follow_redirects=False
    )

    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    assert "A distinctive pasted sentence." in response.text


# --- List with rows -------------------------------------------------------


def test_list_renders_entries_most_recent_first(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_entry(db_session, content="OLDEST-REPORT", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    _seed_entry(db_session, content="NEWEST-REPORT", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    _seed_entry(db_session, content="MIDDLE-REPORT", created_at=datetime(2026, 3, 1, tzinfo=UTC))

    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    body = response.text
    assert body.index("NEWEST-REPORT") < body.index("MIDDLE-REPORT") < body.index("OLDEST-REPORT")


# --- Empty corpus ---------------------------------------------------------


def test_empty_corpus_shows_empty_state_and_a_link_to_the_form(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    assert "/corpus/new" in response.text
    assert "No past reports" in response.text


# --- Blank content --------------------------------------------------------


def test_whitespace_only_content_is_rejected_and_inserts_nothing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus", data={"content": "   \n\t  "}, follow_redirects=False
    )

    assert response.status_code == 422
    assert 'role="alert"' in response.text
    assert db_session.exec(select(CorpusEntry)).all() == []


def test_missing_content_field_is_rejected_and_inserts_nothing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post("/corpus", data={}, follow_redirects=False)

    assert response.status_code == 422
    assert 'role="alert"' in response.text
    assert db_session.exec(select(CorpusEntry)).all() == []


# --- Oversized body -----------------------------------------------------


def test_an_oversized_body_is_rejected_before_it_is_read(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus", data={"content": "x" * (1_048_576 + 1)}, follow_redirects=False
    )

    assert response.status_code == 422
    assert db_session.exec(select(CorpusEntry)).all() == []


# --- Non-UTF-8 body ---------------------------------------------------


def test_a_non_utf8_body_is_rejected_and_inserts_nothing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus",
        content=b"content=\xff\xfe\xfa",
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert db_session.exec(select(CorpusEntry)).all() == []


# --- FR-29 cascade (matrix rows 8 & 9) --------------------------------------


def test_a_paired_entry_is_deleted_with_its_client(db_session: Session) -> None:
    ada = Client(
        name="Ada Lovelace",
        birth_date=datetime(2026, 1, 1).date(),
        birth_time=datetime(2026, 1, 1, 0, 0).time(),
        latitude=0,
        longitude=0,
        iana_zone="UTC",
    )
    db_session.add(ada)
    db_session.flush()
    paired = CorpusEntry(content="paired", client_id=ada.id)
    db_session.add(paired)
    db_session.commit()

    delete_client_and_derived(db_session, client=ada)
    db_session.commit()

    assert db_session.get(CorpusEntry, paired.id) is None


def test_an_unpaired_entry_survives_any_client_deletion(db_session: Session) -> None:
    ada = Client(
        name="Ada Lovelace",
        birth_date=datetime(2026, 1, 1).date(),
        birth_time=datetime(2026, 1, 1, 0, 0).time(),
        latitude=0,
        longitude=0,
        iana_zone="UTC",
    )
    db_session.add(ada)
    db_session.flush()
    unpaired = CorpusEntry(content="unpaired")
    db_session.add(unpaired)
    db_session.commit()

    delete_client_and_derived(db_session, client=ada)
    db_session.commit()

    survived = db_session.get(CorpusEntry, unpaired.id)
    assert survived is not None
    assert survived.client_id is None
