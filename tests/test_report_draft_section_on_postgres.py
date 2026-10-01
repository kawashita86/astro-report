"""``report_draft_section`` and the ``RunDriver`` against a real Postgres (Story 10.4).

The suite's store tests run on in-memory SQLite, which ignores ``VARCHAR(n)`` lengths and
foreign keys (``AGENTS.md``); schema bugs have shipped green three times that way. This
module applies migration ``0025`` for real (``alembic upgrade head`` from an empty
database), then checks what SQLite cannot: the table and its unique key exist with the
migrated shape, the cascade delete honours real foreign keys, the claim is atomic across
real concurrent connections, and a whole run is driven to ``gate_passed`` through the
real advisory lock.

Skips unless ``MIGRATION_TEST_DATABASE_URL`` points at a throwaway Postgres: like
``tests/test_migration_chain_on_postgres.py`` it **drops and recreates the ``public``
schema** of that database.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_draft_section import (
    ReportDraftSection,
    open_section_rows,
    section_rows,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.style_guide import create_style_guide_version
from shell.computation import load_computation_config
from shell.gate import DEFAULT_VOCABULARY_PATH, load_gate_vocabulary
from shell.runner.driver import RunDriver
from shell.runner.lease import section_claim
from shell.sections import load_sections_config
from tests.test_migration_chain_on_postgres import (
    _database_url,
    _reset_public_schema,
    run_online_upgrade,
)
from tests.test_run_driver import _Recorder

_IDENTITY = verify_ephemeris_identity()
_CONFIG = load_computation_config()
_PLACE = ResolvedPlace(
    latitude=Decimal("32.7358"),
    longitude=Decimal("-97.3453"),
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    url = _database_url()
    _reset_public_schema(url)
    completed = run_online_upgrade(url)
    assert completed.returncode == 0, completed.stderr
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


def _a_client_and_run(engine: Engine) -> tuple[UUID, UUID]:
    chart = compute_natal_chart(
        datetime(2026, 1, 1, 6, 0, tzinfo=UTC), _PLACE.latitude, _PLACE.longitude, _CONFIG
    )
    with Session(engine) as session:
        client = create_client_with_chart(
            session,
            name="Ada Lovelace",
            birth_date=date(2026, 1, 1),
            birth_time=time(0, 0),
            resolved_place=_PLACE,
            natal_chart=chart,
            computation_config=_CONFIG,
            ephemeris_identity=_IDENTITY,
        )
        if session.exec(text("SELECT count(*) FROM style_guide")).scalar_one() == 0:
            create_style_guide_version(session, "Scrivi con calore, citando sempre il Payload.")
        run = ReportRun(client_id=client.id, month="2026-01")
        session.add(run)
        session.commit()
        return client.id, run.id


def test_the_migration_creates_the_table_with_its_columns_and_unique_key(engine: Engine) -> None:
    inspector = inspect(engine)

    columns = {column["name"]: column for column in inspector.get_columns("report_draft_section")}
    assert set(columns) == {
        "id",
        "report_run_id",
        "attempt",
        "ordinal",
        "name",
        "status",
        "sentences",
        "attempts",
        "last_error",
        "claimed_at",
        "claim_expires_at",
    }
    assert columns["name"]["type"].length == 32
    assert columns["status"]["type"].length == 16
    assert columns["sentences"]["nullable"] is True
    indexes = {index["name"]: index for index in inspector.get_indexes("report_draft_section")}
    unique = indexes["ix_report_draft_section_run_attempt_ordinal"]
    assert unique["unique"] and unique["column_names"] == ["report_run_id", "attempt", "ordinal"]
    foreign_keys = inspector.get_foreign_keys("report_draft_section")
    assert [fk["referred_table"] for fk in foreign_keys] == ["report_run"]


def test_a_section_row_round_trips_and_the_unique_key_and_foreign_key_are_enforced(
    engine: Engine,
) -> None:
    _, run_id = _a_client_and_run(engine)
    expires = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            ReportDraftSection(
                report_run_id=run_id,
                attempt=0,
                ordinal=1,
                name="energia_generale",
                sentences=[{"text": "Ciao.", "entry_ids": ["a"]}],
                claim_expires_at=expires,
            )
        )
        session.commit()
        row = section_rows(session, run_id, 0)[0]
        assert row.claim_expires_at == expires
        assert row.sentences == [{"text": "Ciao.", "entry_ids": ["a"]}]

        session.add(ReportDraftSection(report_run_id=run_id, attempt=0, ordinal=1, name="amore"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(ReportDraftSection(report_run_id=UUID(int=7), attempt=0, ordinal=1, name="x"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_a_client_cascades_to_its_section_rows_under_real_foreign_keys(
    engine: Engine,
) -> None:
    client_id, run_id = _a_client_and_run(engine)
    with Session(engine) as session:
        open_section_rows(session, run_id, 0)
        session.commit()
        client = session.get(Client, client_id)
        assert client is not None
        delete_client_and_derived(session, client=client)
        session.commit()
        assert (
            session.exec(
                select(ReportDraftSection).where(ReportDraftSection.report_run_id == run_id)
            ).all()
            == []
        )


def test_exactly_one_of_many_concurrent_claims_wins(engine: Engine) -> None:
    _, run_id = _a_client_and_run(engine)
    with Session(engine) as session:
        open_section_rows(session, run_id, 0)
        session.commit()
        section_id = section_rows(session, run_id, 0)[0].id
    results: list[bool] = []
    barrier = threading.Barrier(8)
    holds = threading.Event()

    def _claim() -> None:
        barrier.wait()
        with section_claim(engine, section_id) as held:
            results.append(held is not None)
            if held:
                holds.wait(5)

    threads = [threading.Thread(target=_claim) for _ in range(8)]
    for thread in threads:
        thread.start()
    deadline = datetime.now(UTC) + timedelta(seconds=10)
    while len(results) < 8 and datetime.now(UTC) < deadline:
        threading.Event().wait(0.05)
    holds.set()
    for thread in threads:
        thread.join(10)

    assert sorted(results) == [False] * 7 + [True]


def test_a_run_is_driven_to_gate_passed_on_postgres_and_the_cascade_cleans_up(
    engine: Engine,
) -> None:
    client_id, run_id = _a_client_and_run(engine)
    generator = _Recorder()
    drivers = [
        RunDriver(
            engine=engine,
            config=_CONFIG,
            ephemeris_identity=_IDENTITY,
            sections_config=load_sections_config(),
            vocabulary=load_gate_vocabulary(DEFAULT_VOCABULARY_PATH),
            generator=lambda: generator,
            concurrency=11,
        )
        for _ in range(2)
    ]
    try:
        for driver in drivers:
            driver.start(run_id)
        for driver in drivers:
            assert driver.wait_idle(120)
    finally:
        for driver in drivers:
            driver.stop()

    with Session(engine) as session:
        run = session.get(ReportRun, run_id)
        assert run is not None and run.stage == "gate_passed" and run.failed_at is None
        assert len(session.exec(select(Report).where(Report.report_run_id == run_id)).all()) == 1
        assert (
            len(session.exec(select(ReportDraft).where(ReportDraft.report_run_id == run_id)).all())
            == 1
        )
        rows = section_rows(session, run_id, 0)
        assert [row.status for row in rows] == ["complete"] * 8
    # No Section was written twice, even by two drivers on one run.
    assert all(count == 1 for count in generator.counts.values())
    assert sum(generator.counts.values()) == 8

    with Session(engine) as session:
        client = session.get(Client, client_id)
        assert client is not None
        delete_client_and_derived(session, client=client)
        session.commit()
        assert (
            session.exec(
                select(ReportDraftSection).where(ReportDraftSection.report_run_id == run_id)
            ).all()
            == []
        )
