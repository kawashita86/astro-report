"""``/style-guide``, ``/style-guide/{version}``, ``/style-guide/edit`` -- one
test per row of the story's I/O & Edge-Case Matrix, plus authentication.
Mirrors ``tests/test_http_clients.py``'s fixture shape.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from shell.adapters.postgres.style_guide import StyleGuide, create_style_guide_version
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


def _seed_version_1(db_session: Session, content: str = "Version 1 content.") -> StyleGuide:
    stored = create_style_guide_version(db_session, content)
    db_session.commit()
    return stored


# --- Authentication -------------------------------------------------------------


def test_anonymous_get_history_is_rejected(client: TestClient) -> None:
    assert client.get("/style-guide").status_code == 401


def test_anonymous_get_a_version_is_rejected(client: TestClient, db_session: Session) -> None:
    _seed_version_1(db_session)

    assert client.get("/style-guide/1").status_code == 401


def test_anonymous_get_edit_form_is_rejected(client: TestClient) -> None:
    assert client.get("/style-guide/edit").status_code == 401


def test_anonymous_post_edit_is_rejected(client: TestClient) -> None:
    response = client.post("/style-guide/edit", data={"content": "new content"})

    assert response.status_code == 401
    assert response.content == b""


# --- GET /style-guide: current + history -----------------------------------------


def test_history_lists_current_and_prior_versions(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_version_1(db_session, "v1 content")
    create_style_guide_version(db_session, "v2 content")
    db_session.commit()

    response = authenticated_client.get("/style-guide")

    assert response.status_code == 200
    body = response.text
    assert "version 1" in body
    assert "version 2" in body


def test_current_version_is_not_duplicated_in_history(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """The current version has its own "Current" section; "History" must
    list only the prior versions, or the current version appears twice on
    the page."""
    _seed_version_1(db_session, "v1 content")
    create_style_guide_version(db_session, "v2 content")
    db_session.commit()

    response = authenticated_client.get("/style-guide")

    assert response.status_code == 200
    body = response.text
    assert body.count("version 2") == 1
    assert body.count("version 1") == 1


def test_history_against_an_empty_table_is_caught_and_rendered_not_a_bare_500(
    authenticated_client: TestClient,
) -> None:
    """I/O matrix: `current_style_guide()` against an empty table raises
    `StyleGuideMissingError`, which must be caught and rendered, never a bare
    500. This branch is only expected before migration 0007 has ever run --
    a startup/migration-ordering bug if hit in production -- so it must
    render as 503, distinguishable from a healthy 200 page by monitoring."""
    response = authenticated_client.get("/style-guide")

    assert response.status_code == 503


def test_edit_form_against_an_empty_table_is_caught_and_rendered_503(
    authenticated_client: TestClient,
) -> None:
    """Same I/O matrix case as the history route, for the edit form."""
    response = authenticated_client.get("/style-guide/edit")

    assert response.status_code == 503


# --- GET /style-guide/{version}: historical view -----------------------------------


def test_a_historical_version_is_viewable_read_only(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_version_1(db_session, "Version one prose.")

    response = authenticated_client.get("/style-guide/1")

    assert response.status_code == 200
    assert "Version one prose." in response.text
    # Read-only: no edit affordance on the historical view itself.
    assert "/style-guide/edit" not in response.text


def test_an_unknown_version_is_404(authenticated_client: TestClient, db_session: Session) -> None:
    _seed_version_1(db_session)

    response = authenticated_client.get("/style-guide/999")

    assert response.status_code == 404


# --- GET /style-guide/edit: the form ------------------------------------------------


def test_the_edit_form_is_prefilled_with_the_current_version(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_version_1(db_session, "Current prose to edit.")

    response = authenticated_client.get("/style-guide/edit")

    assert response.status_code == 200
    assert "Current prose to edit." in response.text


# --- POST /style-guide/edit: save a revision -----------------------------------------


def test_saving_a_revision_inserts_version_max_plus_1_and_redirects(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_version_1(db_session, "Version 1 content.")

    response = authenticated_client.post(
        "/style-guide/edit", data={"content": "Version 2 content."}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/style-guide/2"

    rows = list(db_session.exec(select(StyleGuide)))
    assert {row.version for row in rows} == {1, 2}


def test_a_concurrent_save_race_is_caught_and_rendered_409(
    authenticated_client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two concurrent "Save new version" submissions can both compute the
    same `next_version` and race to insert it; the loser's `session.commit()`
    then raises `IntegrityError` against the unique `version` index. That
    must surface as a 409 with the submitter's content preserved, not a bare,
    unhandled 500 -- and the session must be rolled back so a later request
    on the same session is not left in a broken transaction."""
    _seed_version_1(db_session, "Version 1 content.")

    def _raise_integrity_error() -> None:
        raise IntegrityError(
            "INSERT INTO style_guide ...",
            {},
            Exception("UNIQUE constraint failed: style_guide.version"),
        )

    monkeypatch.setattr(db_session, "commit", _raise_integrity_error)

    response = authenticated_client.post(
        "/style-guide/edit", data={"content": "Racing content."}, follow_redirects=False
    )

    assert response.status_code == 409
    assert "Racing content." in response.text
    assert "someone else saved a version first" in response.text


def test_saving_a_revision_leaves_prior_rows_untouched(
    authenticated_client: TestClient, db_session: Session
) -> None:
    seeded = _seed_version_1(db_session, "Version 1 content.")

    authenticated_client.post(
        "/style-guide/edit", data={"content": "Version 2 content."}, follow_redirects=False
    )

    reloaded = db_session.get(StyleGuide, seeded.id)
    assert reloaded is not None
    assert reloaded.version == 1
    assert reloaded.content == "Version 1 content."


def test_no_code_change_or_redeploy_is_needed_to_read_the_new_content(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Acceptance Criteria: after a save, `current_style_guide()` -- and thus
    every route reading through it -- serves the database's new content, not
    `data/style-guide.seed.md`."""
    _seed_version_1(db_session, "Version 1 content.")

    authenticated_client.post(
        "/style-guide/edit", data={"content": "Freshly edited prose."}, follow_redirects=False
    )

    history = authenticated_client.get("/style-guide")
    assert "version 2" in history.text

    view = authenticated_client.get("/style-guide/2")
    assert "Freshly edited prose." in view.text
