"""Story 9.2 -- ``GET /``, the home dashboard.

Walks the story's I/O & Edge-Case Matrix end-to-end through the real
app/session wiring, mirroring ``tests/test_http_backup.py``: the authenticated
dashboard with and without runs, the recent-runs ordering / cap / row content,
the fixed ``(failed_at, stage)`` -> Italian badge map, the global
backup-stale banner (shown when stale, absent when not, absent again after a
recorded backup), and the anonymous empty-body 401.

Rows are built directly against each model's own columns -- this route only
reads existing state, so a valid row per table is all it needs, not a
domain-accurate run.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from datetime import time as time_of_day
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from markupsafe import escape
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from shell.adapters.postgres.backup_record import BackupRecord
from shell.adapters.postgres.client import Client
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_run import ReportRun
from shell.config import Environment, Settings
from shell.http.app import create_app, get_session
from shell.http.auth import ALLOWLIST, SESSION_COOKIE_NAME, sign_session

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


# --- Row builders -----------------------------------------------------------


def _make_client(db_session: Session, *, name: str = "Abbate Chiara") -> Client:
    row = Client(
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=time_of_day(0, 0),
        latitude=Decimal("32.7358"),
        longitude=Decimal("-97.3453"),
        iana_zone="America/Chicago",
    )
    db_session.add(row)
    db_session.flush()
    return row


def _make_run(
    db_session: Session,
    *,
    client_id,
    month: str = "2026-03",
    stage: str | None = None,
    failed_at: datetime | None = None,
    failure_reason: str | None = None,
    updated_at: datetime | None = None,
) -> ReportRun:
    run = ReportRun(
        client_id=client_id,
        month=month,
        stage=stage,
        failed_at=failed_at,
        failure_reason=failure_reason,
        updated_at=updated_at or datetime(2026, 3, 9, 7, 4, tzinfo=UTC),
    )
    db_session.add(run)
    db_session.flush()
    return run


def _make_report(db_session: Session, *, run: ReportRun) -> Report:
    report = Report(
        client_id=run.client_id,
        report_run_id=run.id,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
    )
    db_session.add(report)
    db_session.flush()
    return report


# --- Anonymous -----------------------------------------------------------------


def test_anonymous_get_slash_is_empty_body_401_and_slash_is_not_allowlisted(
    client: TestClient,
) -> None:
    """I/O Matrix -- "Anonymous ``GET /``": the uniform empty-body 401 the
    middleware gives every non-allowlisted path, decided ahead of routing;
    ``/`` never enters ``ALLOWLIST``."""
    response = client.get("/")

    assert response.status_code == 401
    assert response.content == b""
    assert "/" not in ALLOWLIST
    assert {"/healthz", "/login"} == ALLOWLIST


# --- The shell -----------------------------------------------------------------


def test_the_dashboard_renders_through_base_html_with_the_home_h1(
    authenticated_client: TestClient,
) -> None:
    """I/O Matrix -- extends ``base.html``: exactly one ``<html``,
    ``lang="it"``, the sidebar present, the "Home" nav item active, exactly
    one ``<h1>Home</h1>``."""
    response = authenticated_client.get("/")

    assert response.status_code == 200
    body = response.text
    assert body.lower().count("<html") == 1
    assert '<html lang="it">' in body
    assert body.count("<h1>") == 1
    assert "<h1>Home</h1>" in body
    assert 'aria-label="Navigazione principale"' in body
    assert 'href="/"' in body and 'aria-current="page"' in body


def test_the_recent_runs_section_has_a_visible_labelled_heading(
    authenticated_client: TestClient,
) -> None:
    """Review item 5 -- the recent-runs region carries a visible ``<h2>``
    (heading order: ``<h1>Home</h1>`` then this), and the ``<section>`` is
    labelled by it via ``aria-labelledby`` rather than a screen-reader-only
    ``aria-label``."""
    body = authenticated_client.get("/").text

    assert '<h2 id="dash-runs-heading"' in body
    assert ">Report recenti</h2>" in body
    assert 'aria-labelledby="dash-runs-heading"' in body
    assert 'aria-label="Report recenti"' not in body


def test_the_dashboard_links_the_page_and_quick_actions(
    authenticated_client: TestClient,
) -> None:
    """AC -- quick actions to ``/clients`` and ``/style-guide``; the page
    primary action to ``/clients/new``."""
    body = authenticated_client.get("/").text

    assert 'href="/clients/new"' in body
    assert 'href="/clients"' in body
    assert 'href="/style-guide"' in body


# --- Empty state -------------------------------------------------------------


def test_no_runs_shows_the_one_line_empty_state_and_still_the_quick_actions(
    authenticated_client: TestClient,
) -> None:
    """I/O Matrix -- "Authenticated ``GET /``, no runs": 200, exactly
    ``Nessun report avviato.``, no run rows, quick actions still rendered."""
    body = authenticated_client.get("/").text

    assert "Nessun report avviato." in body
    assert 'class="dash-run"' not in body
    assert 'href="/style-guide"' in body
    # Review item 7 -- the empty state carries one onward action of its own,
    # in addition to the quick-action link to the same place.
    assert body.count('href="/clients"') >= 2
    empty_block = body.split("Nessun report avviato.", 1)[1].split("</div>", 1)[0]
    assert 'href="/clients"' in empty_block


# --- Recent-runs list -------------------------------------------------------


def test_a_run_row_carries_client_name_month_chip_badge_and_timestamp(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O Matrix -- "runs exist": one row with the Client name, the month as
    a mono chip, the mapped Italian badge, and the ``dd/MM/yyyy HH:mm``
    updated time."""
    chiara = _make_client(db_session, name="Abbate Chiara")
    _make_run(
        db_session,
        client_id=chiara.id,
        month="2026-03",
        stage="payload_ready",
        updated_at=datetime(2026, 3, 9, 7, 4, tzinfo=UTC),
    )
    db_session.commit()

    body = authenticated_client.get("/").text

    assert "Abbate Chiara" in body
    assert '<button type="button" class="badge-mono" data-copy-chip>2026-03</button>' in body
    assert "Generazione della bozza" in body
    assert "09/03/2026 07:04" in body


def _make_report(db_session: Session, *, run: ReportRun) -> Report:
    """A minimal, directly-built `Report` row for `run` -- mirrors this
    file's own convention (module docstring) of building each model's
    columns directly rather than driving the real Gate. Content-free by
    design: the dashboard link only checks this row's existence."""
    report = Report(
        client_id=run.client_id,
        report_run_id=run.id,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
    )
    db_session.add(report)
    db_session.flush()
    return report


def test_a_gate_passed_run_row_links_straight_to_its_report(
    authenticated_client: TestClient, db_session: Session
) -> None:
    chiara = _make_client(db_session, name="Abbate Chiara")
    run = _make_run(db_session, client_id=chiara.id, stage="gate_passed")
    _make_report(db_session, run=run)
    db_session.commit()

    body = authenticated_client.get("/").text

    assert f'href="/report-runs/{run.id}/report"' in body


def test_a_run_closed_via_accepted_violations_shows_the_warning_badge_beside_the_status(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Story 5.7: a Report with a non-zero ``accepted_violation_count``
    carries the "Superato con N eccezioni" warning badge stacked alongside
    the run's normal status badge, never replacing it."""
    chiara = _make_client(db_session, name="Abbate Chiara")
    run = _make_run(db_session, client_id=chiara.id, stage="gate_passed")
    report = Report(
        client_id=run.client_id,
        report_run_id=run.id,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        accepted_violation_count=2,
    )
    db_session.add(report)
    db_session.commit()

    body = authenticated_client.get("/").text

    assert "Superato con 2 eccezioni" in body
    assert "status-badge--warning" in body
    # The row's own normal status badge is still rendered alongside it, not
    # replaced by the warning badge.
    assert f'href="/report-runs/{run.id}/report"' in body


def test_a_clean_pass_run_row_shows_no_warning_badge(
    authenticated_client: TestClient, db_session: Session
) -> None:
    chiara = _make_client(db_session, name="Abbate Chiara")
    run = _make_run(db_session, client_id=chiara.id, stage="gate_passed")
    _make_report(db_session, run=run)
    db_session.commit()

    body = authenticated_client.get("/").text

    assert "eccezioni" not in body


def test_an_exported_run_row_links_straight_to_its_report(
    authenticated_client: TestClient, db_session: Session
) -> None:
    chiara = _make_client(db_session, name="Abbate Chiara")
    run = _make_run(db_session, client_id=chiara.id, stage="exported")
    _make_report(db_session, run=run)
    db_session.commit()

    body = authenticated_client.get("/").text

    assert f'href="/report-runs/{run.id}/report"' in body


def test_a_still_running_run_row_links_to_its_stage_view(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """No `Report` row yet -- `view_report` itself would 404 this run, so
    the dashboard must not send it there."""
    chiara = _make_client(db_session, name="Abbate Chiara")
    run = _make_run(db_session, client_id=chiara.id, stage="payload_ready")
    db_session.commit()

    body = authenticated_client.get("/").text

    assert f'href="/report-runs/{run.id}"' in body
    assert f'href="/report-runs/{run.id}/report"' not in body


def test_a_run_that_never_reached_gate_passed_and_is_now_failed_links_to_its_stage_view(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Terminally failed with no `Report` row at all -- the common failure
    shape (never passed the Gate)."""
    chiara = _make_client(db_session, name="Abbate Chiara")
    run = _make_run(
        db_session,
        client_id=chiara.id,
        stage="draft_ready",
        failed_at=datetime(2026, 3, 9, 8, 0, tzinfo=UTC),
        failure_reason="errore generico",
    )
    db_session.commit()

    body = authenticated_client.get("/").text

    assert f'href="/report-runs/{run.id}"' in body
    assert f'href="/report-runs/{run.id}/report"' not in body


def test_a_run_with_a_passed_report_links_to_it_even_if_later_marked_failed(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """The dashboard link mirrors `view_report`'s own gate: a persisted
    `Report` row's mere existence, never `run.stage`/`run.failed_at`
    (`shell/http/routes/report_runs.py::view_report`'s docstring). A run
    that passed once and only later picked up an unrelated terminal
    failure still has a real Report to show -- linking to the stage view
    instead would hide it behind a badge that no longer reflects it."""
    chiara = _make_client(db_session, name="Abbate Chiara")
    run = _make_run(
        db_session,
        client_id=chiara.id,
        stage="gate_passed",
        failed_at=datetime(2026, 3, 9, 8, 0, tzinfo=UTC),
        failure_reason="errore generico",
    )
    _make_report(db_session, run=run)
    db_session.commit()

    body = authenticated_client.get("/").text

    assert f'href="/report-runs/{run.id}/report"' in body


def test_recent_runs_are_ordered_newest_updated_first(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Boundaries -- ordered ``updated_at`` desc."""
    a = _make_client(db_session, name="Alfa Uno")
    b = _make_client(db_session, name="Bravo Due")
    c = _make_client(db_session, name="Charlie Tre")
    _make_run(db_session, client_id=a.id, updated_at=datetime(2026, 3, 1, 8, 0, tzinfo=UTC))
    _make_run(db_session, client_id=b.id, updated_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC))
    _make_run(db_session, client_id=c.id, updated_at=datetime(2026, 3, 3, 8, 0, tzinfo=UTC))
    db_session.commit()

    body = authenticated_client.get("/").text

    assert body.index("Charlie Tre") < body.index("Bravo Due") < body.index("Alfa Uno")


def test_the_recent_runs_list_is_capped_at_twenty(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Boundaries -- ``.limit(_RECENT_LIMIT)`` with ``_RECENT_LIMIT = 20``."""
    owner = _make_client(db_session)
    for minute in range(25):
        _make_run(
            db_session,
            client_id=owner.id,
            updated_at=datetime(2026, 3, 1, 8, minute, tzinfo=UTC),
        )
    db_session.commit()

    body = authenticated_client.get("/").text

    assert body.count('class="dash-run"') == 20


# --- The status badge: a total map over (failed_at, stage) -----------------


@pytest.mark.parametrize(
    ("stage", "text", "variant"),
    [
        (None, "In coda", "neutral"),
        ("natal_ready", "Ricerca dei transiti", "running"),
        ("transits_ready", "Assemblaggio del Payload", "running"),
        ("payload_ready", "Generazione della bozza", "running"),
        ("draft_ready", "Verifica di fondatezza", "running"),
        ("gate_passed", "Pronto per l'esportazione", "running"),
        ("exported", "Esportato", "success"),
    ],
)
def test_the_stage_badge_map_is_total_over_every_persisted_stage(
    authenticated_client: TestClient,
    db_session: Session,
    stage: str | None,
    text: str,
    variant: str,
) -> None:
    owner = _make_client(db_session)
    _make_run(db_session, client_id=owner.id, stage=stage)
    db_session.commit()

    body = authenticated_client.get("/").text

    assert f"status-badge--{variant}" in body
    # The badge text is a template variable, so Jinja HTML-escapes the
    # apostrophe in "Pronto per l'esportazione" to ``&#39;``.
    assert str(escape(text)) in body


def test_a_terminally_failed_run_reads_danger_with_the_reason_as_title(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O Matrix -- "Terminal-failed run": ``failed_at`` set wins over
    ``stage``; badge is ``Verifica non superata`` (``danger``) with
    ``failure_reason`` as the element ``title``."""
    owner = _make_client(db_session)
    _make_run(
        db_session,
        client_id=owner.id,
        stage="draft_ready",
        failed_at=datetime(2026, 3, 9, 9, 0, tzinfo=UTC),
        failure_reason="Generatore non raggiungibile dopo i tentativi previsti.",
    )
    db_session.commit()

    body = authenticated_client.get("/").text

    assert "Verifica non superata" in body
    assert "status-badge--danger" in body
    assert 'title="Generatore non raggiungibile dopo i tentativi previsti."' in body
    assert "Verifica di fondatezza" not in body  # the draft_ready label is not used


def test_a_not_yet_advanced_run_reads_in_coda_neutral(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O Matrix -- "Not-yet-advanced run": ``stage is None`` -> ``In coda``,
    neutral variant."""
    owner = _make_client(db_session)
    _make_run(db_session, client_id=owner.id, stage=None)
    db_session.commit()

    body = authenticated_client.get("/").text

    assert "In coda" in body
    assert "status-badge--neutral" in body


def test_an_unmapped_stage_value_degrades_to_the_neutral_badge_not_a_500(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Review item 6 -- a legacy/restored run carrying a ``stage`` outside
    the seven mapped keys renders the neutral ``In coda`` badge with a 200,
    rather than ``KeyError``-ing the landing page."""
    owner = _make_client(db_session)
    _make_run(db_session, client_id=owner.id, stage="some_future_stage")
    db_session.commit()

    response = authenticated_client.get("/")

    assert response.status_code == 200
    assert "In coda" in response.text
    assert "status-badge--neutral" in response.text


# --- The global backup-stale banner (AD-17) -------------------------------


_BANNER_TEXT = "Backup non aggiornato — esistono nuovi report dall'ultimo backup."


def test_the_banner_shows_when_a_report_postdates_the_last_backup(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O Matrix -- "Backup is stale": a ``warning`` ``role="alert"`` region
    with the exact copy and an ``Esegui backup ora`` link to
    ``/backup?record=1``."""
    owner = _make_client(db_session)
    run = _make_run(db_session, client_id=owner.id)
    _make_report(db_session, run=run)  # a Report, no backup_record at all -> stale
    db_session.commit()

    body = authenticated_client.get("/").text

    assert _BANNER_TEXT in body
    assert 'role="alert"' in body
    assert "banner--warning" in body
    assert 'href="/backup?record=1"' in body
    assert "Esegui backup ora" in body


def test_the_banner_is_absent_when_the_backup_is_current(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O Matrix -- "Backup not stale": no ``Report`` at all -> no banner."""
    owner = _make_client(db_session)
    _make_run(db_session, client_id=owner.id)
    db_session.commit()

    body = authenticated_client.get("/").text

    assert _BANNER_TEXT not in body
    assert 'role="alert"' not in body


def test_the_banner_clears_after_a_recorded_backup(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """I/O Matrix -- "Banner clears after a recorded backup": stale, then
    ``GET /backup?record=1``, then a reload of ``/`` renders without it."""
    owner = _make_client(db_session)
    run = _make_run(db_session, client_id=owner.id)
    _make_report(db_session, run=run)
    db_session.commit()

    assert _BANNER_TEXT in authenticated_client.get("/").text

    recorded = authenticated_client.get("/backup?record=1")
    assert recorded.status_code == 200
    assert db_session.exec(select(BackupRecord)).first() is not None

    assert _BANNER_TEXT not in authenticated_client.get("/").text
