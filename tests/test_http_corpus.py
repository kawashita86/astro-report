"""``/corpus``, ``/corpus/new``, ``POST /corpus`` -- one test per row of
Story 7.1's I/O & Edge-Case Matrix, plus authentication. Mirrors
``tests/test_http_style_guide.py``'s fixture shape.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import uuid4

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


def _seed_entry(
    db_session: Session,
    *,
    content: str,
    created_at: datetime,
    paired: bool = False,
) -> CorpusEntry:
    entry = CorpusEntry(content=content, created_at=created_at, paired=paired)
    db_session.add(entry)
    db_session.commit()
    return entry


def _seed_client(db_session: Session, *, name: str = "Ada Lovelace") -> Client:
    client = Client(
        name=name,
        birth_date=datetime(2026, 1, 1).date(),
        birth_time=datetime(2026, 1, 1, 0, 0).time(),
        latitude=0,
        longitude=0,
        iana_zone="UTC",
    )
    db_session.add(client)
    db_session.commit()
    return client


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


# --- Pairing marking (Story 7.2 I/O & Edge-Case Matrix) --------------------


def test_unpaired_entry_stores_paired_false_and_no_link(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus",
        data={"content": "An unpaired report.", "paired": "unpaired"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    rows = db_session.exec(select(CorpusEntry)).all()
    assert len(rows) == 1
    assert rows[0].paired is False
    assert rows[0].client_id is None
    assert rows[0].month is None


def test_paired_and_linked_entry_persists_client_id_and_month(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _seed_client(db_session)

    response = authenticated_client.post(
        "/corpus",
        data={
            "content": "Paired and linked.",
            "paired": "paired",
            "client_id": str(ada.id),
            "month": "2026-05",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    rows = db_session.exec(select(CorpusEntry)).all()
    assert len(rows) == 1
    assert rows[0].paired is True
    assert rows[0].client_id == ada.id
    assert rows[0].month == "2026-05"


def test_paired_entry_with_no_client_and_no_month_persists_with_nulls(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus",
        data={
            "content": "Chart known, not in the app.",
            "paired": "paired",
            "client_id": "",
            "month": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    rows = db_session.exec(select(CorpusEntry)).all()
    assert len(rows) == 1
    assert rows[0].paired is True
    assert rows[0].client_id is None
    assert rows[0].month is None


def test_paired_entry_with_unknown_client_is_rejected_and_inserts_nothing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus",
        data={"content": "Paired.", "paired": "paired", "client_id": str(uuid4())},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert 'role="alert"' in response.text
    assert db_session.exec(select(CorpusEntry)).all() == []


def test_paired_entry_with_malformed_client_id_is_rejected_and_inserts_nothing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus",
        data={"content": "Paired.", "paired": "paired", "client_id": "not-a-uuid"},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert 'role="alert"' in response.text
    assert db_session.exec(select(CorpusEntry)).all() == []


@pytest.mark.parametrize("bad_month", ["2026-13", "may", "2026-5"])
def test_paired_entry_with_a_bad_month_is_rejected_and_inserts_nothing(
    authenticated_client: TestClient, db_session: Session, bad_month: str
) -> None:
    response = authenticated_client.post(
        "/corpus",
        data={"content": "Paired.", "paired": "paired", "month": bad_month},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert 'role="alert"' in response.text
    assert db_session.exec(select(CorpusEntry)).all() == []


def test_unpaired_entry_ignores_submitted_link_fields(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _seed_client(db_session)

    response = authenticated_client.post(
        "/corpus",
        data={
            "content": "Unpaired, but link fields sent.",
            "paired": "unpaired",
            "client_id": str(ada.id),
            "month": "2026-05",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    rows = db_session.exec(select(CorpusEntry)).all()
    assert len(rows) == 1
    assert rows[0].paired is False
    assert rows[0].client_id is None
    assert rows[0].month is None


def test_blank_content_with_paired_is_rejected_and_inserts_nothing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus",
        data={"content": "   \n\t  ", "paired": "paired"},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert 'role="alert"' in response.text
    assert db_session.exec(select(CorpusEntry)).all() == []


def test_a_422_re_render_echoes_the_submitted_input_back(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """``_render_new_form`` preserves ``content`` and the submitted marking
    fields on every rejection: a distinctive prose body and the bad month
    both survive the round trip into the re-rendered form."""
    response = authenticated_client.post(
        "/corpus",
        data={"content": "KEEP-THIS-PROSE", "paired": "paired", "month": "2026-13"},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert "KEEP-THIS-PROSE" in response.text
    assert "2026-13" in response.text
    assert db_session.exec(select(CorpusEntry)).all() == []


def test_paired_entry_with_only_a_valid_month_persists(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/corpus",
        data={
            "content": "Paired, month only.",
            "paired": "paired",
            "client_id": "",
            "month": "2026-05",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    rows = db_session.exec(select(CorpusEntry)).all()
    assert len(rows) == 1
    assert rows[0].paired is True
    assert rows[0].client_id is None
    assert rows[0].month == "2026-05"


def test_list_shows_paired_client_and_month_and_unpaired_state(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _seed_client(db_session, name="Ada Lovelace")
    db_session.add(
        CorpusEntry(
            content="PAIRED-BLOCK-MARKER",
            paired=True,
            client_id=ada.id,
            month="2026-05",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    db_session.add(
        CorpusEntry(
            content="UNPAIRED-BLOCK-MARKER",
            # A created_at month deliberately unlike the paired entry's linked
            # month ("2026-05") so "2026-05" appearing in the unpaired block
            # would only ever be a template bug, not this timestamp.
            created_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
    )
    db_session.commit()

    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    blocks = response.text.split("<li>")
    paired_block = next(block for block in blocks if "PAIRED-BLOCK-MARKER" in block)
    unpaired_block = next(block for block in blocks if "UNPAIRED-BLOCK-MARKER" in block)

    assert "Ada Lovelace" in paired_block
    assert "2026-05" in paired_block
    assert "Paired" in paired_block

    assert "Unpaired" in unpaired_block
    assert "Ada Lovelace" not in unpaired_block
    assert "2026-05" not in unpaired_block


def test_new_form_offers_the_existing_clients_in_the_picker(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_client(db_session, name="Grace Hopper")

    response = authenticated_client.get("/corpus/new")

    assert response.status_code == 200
    assert "Grace Hopper" in response.text
    assert 'name="paired"' in response.text


# --- Corpus composition line (Story 7.3 I/O & Edge-Case Matrix) -----------


def test_empty_corpus_composition_reads_all_zero_and_keeps_the_empty_state(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    assert "0 total · 0 paired · 0 unpaired" in response.text
    assert "No past reports" in response.text
    assert "/corpus/new" in response.text


def test_mixed_corpus_composition_counts_and_still_lists_every_entry(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_entry(
        db_session, content="P-1", created_at=datetime(2026, 1, 1, tzinfo=UTC), paired=True
    )
    _seed_entry(
        db_session, content="P-2", created_at=datetime(2026, 2, 1, tzinfo=UTC), paired=True
    )
    _seed_entry(db_session, content="U-1", created_at=datetime(2026, 3, 1, tzinfo=UTC))
    _seed_entry(db_session, content="U-2", created_at=datetime(2026, 4, 1, tzinfo=UTC))
    _seed_entry(db_session, content="U-3", created_at=datetime(2026, 5, 1, tzinfo=UTC))

    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    body = response.text
    assert "5 total · 2 paired · 3 unpaired" in body
    for marker in ("P-1", "P-2", "U-1", "U-2", "U-3"):
        assert marker in body
    assert body.index("U-3") < body.index("U-2") < body.index("U-1") < body.index(
        "P-2"
    ) < body.index("P-1")


def test_all_unpaired_corpus_composition_counts(
    authenticated_client: TestClient, db_session: Session
) -> None:
    for n in range(4):
        _seed_entry(
            db_session, content=f"U-{n}", created_at=datetime(2026, 1, n + 1, tzinfo=UTC)
        )

    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    assert "4 total · 0 paired · 4 unpaired" in response.text


def test_paired_entry_without_a_link_still_counts_as_paired(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_entry(
        db_session,
        content="Chart known, not in the app.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        paired=True,
    )

    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    assert "1 total · 1 paired · 0 unpaired" in response.text


def test_composition_line_precedes_the_first_entry_in_the_html(
    authenticated_client: TestClient, db_session: Session
) -> None:
    _seed_entry(
        db_session, content="ONLY-ENTRY-MARKER", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )

    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    body = response.text
    assert body.index("Corpus composition:") < body.index("ONLY-ENTRY-MARKER")


def test_composition_counts_change_when_entries_are_added_between_requests(
    authenticated_client: TestClient, db_session: Session
) -> None:
    first = authenticated_client.get("/corpus")
    assert "0 total · 0 paired · 0 unpaired" in first.text

    _seed_entry(
        db_session, content="NEW-ROW", created_at=datetime(2026, 1, 1, tzinfo=UTC), paired=True
    )

    second = authenticated_client.get("/corpus")
    assert "1 total · 1 paired · 0 unpaired" in second.text


def test_composition_line_after_the_real_post_then_get_user_path(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ada = _seed_client(db_session)

    authenticated_client.post(
        "/corpus",
        data={"content": "An unpaired past report.", "paired": "unpaired"},
        follow_redirects=False,
    )
    authenticated_client.post(
        "/corpus",
        data={
            "content": "A paired past report.",
            "paired": "paired",
            "client_id": str(ada.id),
            "month": "2026-05",
        },
        follow_redirects=False,
    )

    response = authenticated_client.get("/corpus")

    assert response.status_code == 200
    assert "Corpus composition: 2 total · 1 paired · 1 unpaired" in response.text


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
