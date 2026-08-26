"""``GET /backup`` -- Story 6.5's own I/O & Edge-Case Matrix, exercised
end-to-end through the real app/session wiring, mirroring
``tests/test_http_clients.py``.

Every row here is constructed directly against each model's own columns,
never via a real ``compute_natal_chart()``/``Generator``/Gate run: this
route only serializes whatever rows already exist -- it does not care how
they got there, so these tests only need *some* valid row per table, not a
domain-accurate one. Real per-table write behavior already has its own test
module (``tests/test_client_store.py``, ``tests/test_report_run_store.py``,
``tests/test_export_record_store.py``, etc.).
"""

from __future__ import annotations

import time
from datetime import date
from datetime import time as time_of_day
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from shell.adapters.postgres import client as client_module
from shell.adapters.postgres.client import Client, StoredNatalChart
from shell.adapters.postgres.export_record import ExportRecord
from shell.adapters.postgres.gate_result import StoredGateResult
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_payload import ReportPayload
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.report_theme import StoredReportTheme
from shell.adapters.postgres.style_guide import StyleGuide
from shell.config import Environment, Settings
from shell.http.app import create_app, get_session
from shell.http.auth import SESSION_COOKIE_NAME, sign_session
from shell.http.routes.backup import _BACKUP_MODELS

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

#: The exact FK-safe order the spec's Code Map and Design Notes require --
#: the single source of truth this whole test module checks the route's
#: output against.
_TABLE_ORDER = [
    "client",
    "natal_chart",
    "report_run",
    "report",
    "report_payload",
    "report_draft",
    "report_theme",
    "gate_result",
    "export_record",
    "style_guide",
]


@pytest.fixture
def db_session() -> Session:
    # `check_same_thread=False` + `StaticPool`: `TestClient` dispatches the
    # ASGI app on its own worker thread, distinct from this fixture's thread
    # -- mirrors `tests/test_http_clients.py`'s own `db_session` fixture.
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


# --- Row builders: one valid row per table, nothing more -----------------


def _make_client(db_session: Session, *, name: str = "Ada Lovelace") -> Client:
    client_row = Client(
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=time_of_day(0, 0),
        latitude=Decimal("32.7358"),
        longitude=Decimal("-97.3453"),
        iana_zone="America/Chicago",
    )
    db_session.add(client_row)
    db_session.flush()
    return client_row


def _make_chart(db_session: Session, *, client_id) -> StoredNatalChart:
    chart = StoredNatalChart(
        client_id=client_id,
        ascendant=Decimal("183.0381"),
        midheaven=Decimal("93.0381"),
        planets=[{"name": "sun"}],
        houses=[{"number": 1}],
        aspects=[{"body1": "sun"}],
        computation_config_version=1,
        computation_config_content_hash="a" * 64,
        ephemeris_files=[{"name": "test.se1"}],
    )
    db_session.add(chart)
    db_session.flush()
    return chart


def _make_run(
    db_session: Session, *, client_id, natal_chart_id=None, month: str = "2026-01"
) -> ReportRun:
    run = ReportRun(client_id=client_id, natal_chart_id=natal_chart_id, month=month)
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


def _make_payload(db_session: Session, *, run: ReportRun) -> ReportPayload:
    payload = ReportPayload(
        client_id=run.client_id,
        report_run_id=run.id,
        schema_version=1,
        computation_config_version=1,
        computation_config_content_hash="a" * 64,
        sections_config_version=1,
        sections_config_content_hash="b" * 64,
        ephemeris_files=[{"name": "test.se1"}],
        payload={"schema_version": 1},
    )
    db_session.add(payload)
    db_session.flush()
    return payload


def _make_draft(db_session: Session, *, run: ReportRun, attempt: int = 0) -> ReportDraft:
    draft = ReportDraft(
        client_id=run.client_id,
        report_run_id=run.id,
        attempt=attempt,
        style_guide_version=1,
        sections_config_version=1,
        draft={"energia_generale": []},
    )
    db_session.add(draft)
    db_session.flush()
    return draft


def _make_theme(db_session: Session, *, run: ReportRun) -> StoredReportTheme:
    theme = StoredReportTheme(
        client_id=run.client_id,
        report_run_id=run.id,
        theme={"amore": "steady"},
    )
    db_session.add(theme)
    db_session.flush()
    return theme


def _make_gate_result(db_session: Session, *, run: ReportRun) -> StoredGateResult:
    gate_result = StoredGateResult(
        client_id=run.client_id,
        report_run_id=run.id,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        violations=[],
    )
    db_session.add(gate_result)
    db_session.flush()
    return gate_result


def _make_export_record(db_session: Session, *, report: Report) -> ExportRecord:
    export_record = ExportRecord(
        client_id=report.client_id,
        report_id=report.id,
        format="pdf",
        elapsed_seconds=42,
    )
    db_session.add(export_record)
    db_session.flush()
    return export_record


def _make_style_guide(db_session: Session, *, version: int, content: str) -> StyleGuide:
    style_guide = StyleGuide(version=version, content=content)
    db_session.add(style_guide)
    db_session.flush()
    return style_guide


def _full_chain(db_session: Session, *, name: str = "Ada Lovelace") -> dict:
    """Client -> StoredNatalChart -> ReportRun -> Report/ReportPayload/
    ReportDraft/StoredReportTheme/StoredGateResult -> ExportRecord, the full
    depth the Populated pipeline matrix row describes."""
    client_row = _make_client(db_session, name=name)
    chart = _make_chart(db_session, client_id=client_row.id)
    run = _make_run(db_session, client_id=client_row.id, natal_chart_id=chart.id)
    report = _make_report(db_session, run=run)
    payload = _make_payload(db_session, run=run)
    draft = _make_draft(db_session, run=run)
    theme = _make_theme(db_session, run=run)
    gate_result = _make_gate_result(db_session, run=run)
    export_record = _make_export_record(db_session, report=report)
    return {
        "client": client_row,
        "chart": chart,
        "run": run,
        "report": report,
        "payload": payload,
        "draft": draft,
        "theme": theme,
        "gate_result": gate_result,
        "export_record": export_record,
    }


# --- I/O & Edge-Case Matrix ------------------------------------------------


def test_anonymous_request_is_rejected(client: TestClient) -> None:
    response = client.get("/backup")

    assert response.status_code == 401


def test_empty_database_downloads_all_ten_keys_as_empty_lists(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/backup")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    assert ".json" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"

    body = response.json()
    assert list(body.keys()) == _TABLE_ORDER
    for table_name in _TABLE_ORDER:
        assert body[table_name] == []


def test_populated_pipeline_includes_every_row_exactly_once_in_fk_safe_order(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: several Clients, each with a full ``ReportRun`` ->
    ``Report`` -> ``ReportPayload``/``ReportDraft``/``ReportTheme``/
    ``GateResult`` chain, some with ``ExportRecord``s -- every row across
    every included table appears exactly once, in the FK-safe table order.
    """
    ada = _full_chain(db_session, name="Ada Lovelace")
    grace = _full_chain(db_session, name="Grace Hopper")
    db_session.commit()

    response = authenticated_client.get("/backup")

    assert response.status_code == 200
    body = response.json()

    # The FK-safe order itself, exactly -- the whole trick that makes a
    # future restore able to insert file order without violating a
    # foreign key (this story's Design Notes).
    assert list(body.keys()) == _TABLE_ORDER

    assert {row["id"] for row in body["client"]} == {str(ada["client"].id), str(grace["client"].id)}
    assert {row["id"] for row in body["natal_chart"]} == {
        str(ada["chart"].id),
        str(grace["chart"].id),
    }
    assert {row["id"] for row in body["report_run"]} == {str(ada["run"].id), str(grace["run"].id)}
    assert {row["id"] for row in body["report"]} == {
        str(ada["report"].id),
        str(grace["report"].id),
    }
    assert {row["id"] for row in body["report_payload"]} == {
        str(ada["payload"].id),
        str(grace["payload"].id),
    }
    assert {row["id"] for row in body["report_draft"]} == {
        str(ada["draft"].id),
        str(grace["draft"].id),
    }
    assert {row["id"] for row in body["report_theme"]} == {
        str(ada["theme"].id),
        str(grace["theme"].id),
    }
    assert {row["id"] for row in body["gate_result"]} == {
        str(ada["gate_result"].id),
        str(grace["gate_result"].id),
    }
    assert {row["id"] for row in body["export_record"]} == {
        str(ada["export_record"].id),
        str(grace["export_record"].id),
    }

    # Every row appears exactly once: no duplication across the two chains.
    for table_name in _TABLE_ORDER:
        if table_name == "style_guide":
            continue
        assert len(body[table_name]) == 2


def test_a_pre_story_6_4_report_run_with_no_natal_chart_id_is_included(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: ``ReportRun.natal_chart_id`` is ``NULL`` -- a run created
    before Story 6.4 -- still included, with ``natal_chart_id: null``, not
    dropped or errored on."""
    ada = _make_client(db_session)
    run = _make_run(db_session, client_id=ada.id, natal_chart_id=None)
    db_session.commit()

    response = authenticated_client.get("/backup")

    assert response.status_code == 200
    body = response.json()

    rows = [row for row in body["report_run"] if row["id"] == str(run.id)]
    assert len(rows) == 1
    assert rows[0]["natal_chart_id"] is None


def test_multiple_style_guide_versions_are_all_included(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Matrix row: >1 ``StyleGuide`` row (Story 4.2 edits) -- all versions
    included, not only the current one."""
    v1 = _make_style_guide(db_session, version=1, content="Version one.")
    v2 = _make_style_guide(db_session, version=2, content="Version two.")
    db_session.commit()

    response = authenticated_client.get("/backup")

    assert response.status_code == 200
    body = response.json()

    versions = {row["version"] for row in body["style_guide"]}
    assert versions == {v1.version, v2.version}
    assert len(body["style_guide"]) == 2


# --- Structural invariants --------------------------------------------------


def test_backup_models_cover_exactly_the_client_cascade_tables_plus_client_and_style_guide() -> (
    None
):
    """``_BACKUP_MODELS`` (``shell/http/routes/backup.py``) must never
    silently drift from ``_CLIENT_CASCADE_TABLES``
    (``shell/adapters/postgres/client.py``) -- the guarded single source of
    truth for every table carrying a foreign key to ``client.id``, itself
    kept equal to every such table in ``SQLModel.metadata`` by
    ``tests/test_client_store.py``'s own cascade-invariant test. A
    client-scoped table added to the cascade set but forgotten here must
    fail loudly rather than silently go missing from every backup."""
    backup_tables = {model.__tablename__ for model in _BACKUP_MODELS}

    assert backup_tables == client_module._CLIENT_CASCADE_TABLES | {"client", "style_guide"}


def test_backup_model_order_is_fk_safe() -> None:
    """The FK-safe ordering claim this whole story is built on
    (``shell/http/routes/backup.py``'s own docstring, and the spec's Design
    Notes) verified structurally, not just asserted in prose: every foreign
    key declared on any of the ten ``_BACKUP_MODELS`` tables must target a
    table that appears *earlier* in ``_BACKUP_MODELS`` than the table
    declaring it, so a future restore (Story 8.5) can insert the file's
    arrays in file order without ever hitting a foreign key that doesn't
    exist yet."""
    table_order = [model.__tablename__ for model in _BACKUP_MODELS]
    position = {table_name: index for index, table_name in enumerate(table_order)}

    for model in _BACKUP_MODELS:
        for foreign_key in model.__table__.foreign_keys:
            target_table = foreign_key.column.table.name
            assert position[target_table] < position[model.__tablename__], (
                f"{model.__tablename__}.{foreign_key.parent.name} references "
                f"{target_table}, which appears at or after {model.__tablename__} "
                "in _BACKUP_MODELS -- a restore inserting file order would violate "
                "this foreign key."
            )


# --- Partial/uneven shapes --------------------------------------------------


def test_a_report_with_two_export_records_and_no_draft_theme_or_gate_result_associates_correctly(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """An uneven shape, not merely a fully-chained one: a ``ReportRun`` ->
    ``Report`` with two ``ExportRecord``s (a realistic case per Story 6.3's
    repeat-export flow -- every successful export writes a new row, first or
    repeat) and no ``ReportDraft``/``ReportTheme``/``GateResult`` at all.
    Asserts each ``ExportRecord`` row is correctly associated with its
    parent ``Report``/``Client`` by id, not merely that the counts match."""
    ada = _make_client(db_session)
    run = _make_run(db_session, client_id=ada.id)
    report = _make_report(db_session, run=run)
    first_export = _make_export_record(db_session, report=report)
    second_export = _make_export_record(db_session, report=report)
    db_session.commit()

    response = authenticated_client.get("/backup")

    assert response.status_code == 200
    body = response.json()

    assert body["report_draft"] == []
    assert body["report_theme"] == []
    assert body["gate_result"] == []

    export_rows_by_id = {row["id"]: row for row in body["export_record"]}
    assert set(export_rows_by_id) == {str(first_export.id), str(second_export.id)}
    for export_row in export_rows_by_id.values():
        assert export_row["report_id"] == str(report.id)
        assert export_row["client_id"] == str(ada.id)

    report_rows = body["report"]
    assert len(report_rows) == 1
    assert report_rows[0]["id"] == str(report.id)
    assert report_rows[0]["report_run_id"] == str(run.id)


# --- Value-level serialization -----------------------------------------------


def test_decimal_and_json_column_values_are_serialized_correctly(
    authenticated_client: TestClient, db_session: Session
) -> None:
    """Not just presence/count -- the actual serialized values of a
    ``Decimal`` column (``Client.latitude``/``longitude``) and a JSON column
    (``StoredNatalChart.planets``) round-trip through
    ``.model_dump(mode="json")`` correctly: ``Decimal`` -> ``str`` (numerically
    exact, regardless of the DB driver's own zero-padding on read-back), and
    the JSON column's list-of-dicts passes through unchanged."""
    ada = _make_client(db_session)
    chart = _make_chart(db_session, client_id=ada.id)
    db_session.commit()

    response = authenticated_client.get("/backup")

    assert response.status_code == 200
    body = response.json()

    client_row = next(row for row in body["client"] if row["id"] == str(ada.id))
    assert isinstance(client_row["latitude"], str)
    assert Decimal(client_row["latitude"]) == Decimal("32.7358")
    assert isinstance(client_row["longitude"], str)
    assert Decimal(client_row["longitude"]) == Decimal("-97.3453")

    chart_row = next(row for row in body["natal_chart"] if row["id"] == str(chart.id))
    assert chart_row["planets"] == [{"name": "sun"}]
    assert chart_row["houses"] == [{"number": 1}]
    assert chart_row["aspects"] == [{"body1": "sun"}]
