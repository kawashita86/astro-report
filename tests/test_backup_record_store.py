"""``BackupRecord`` (Story 6.6): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_export_record_store.py`` and
``tests/test_style_guide_store.py``. Covers ``store_backup_record()``'s
write (a fresh row, timestamped with ``created_at`` approximately now) and
``latest_backup_record()``'s two outcomes -- empty table, and picking the
most recent of several rows by ``created_at``, not insertion order.

Also covers ``backup_is_stale()`` (promoted here from
``shell/http/routes/clients.py`` by Story 9.2): no Report -> False; a Report
with no backup ever recorded -> True; and the two ordering outcomes against
the latest ``backup_record``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from datetime import time as time_of_day
from decimal import Decimal
from uuid import UUID

import pytest
from sqlmodel import Session, SQLModel, create_engine

from shell.adapters.postgres.backup_record import (
    BackupRecord,
    backup_is_stale,
    latest_backup_record,
    store_backup_record,
)

# Imported so ``SQLModel.metadata.create_all`` below registers the ``client``
# / ``report_run`` / ``report`` tables that ``backup_is_stale`` reads through
# -- ``backup_record.py`` now imports ``Report`` at module level, whose FK
# chain reaches ``client``.
from shell.adapters.postgres.client import Client
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_run import ReportRun


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# --- store_backup_record() -------------------------------------------------------


def test_a_backup_record_id_is_uuidv7(session: Session) -> None:
    stored = store_backup_record(session)
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_store_backup_record_persists_a_row_with_created_at_now(session: Session) -> None:
    before = datetime.now(UTC)

    stored = store_backup_record(session)
    session.commit()

    after = datetime.now(UTC)
    reloaded = session.get(BackupRecord, stored.id)
    assert reloaded is not None
    assert reloaded.created_at is not None
    assert before - timedelta(seconds=5) <= reloaded.created_at <= after + timedelta(seconds=5)


def test_store_backup_record_only_flushes_never_commits(session: Session) -> None:
    stored = store_backup_record(session)
    stored_id = stored.id
    session.rollback()

    assert session.get(BackupRecord, stored_id) is None


# --- latest_backup_record() ------------------------------------------------------


def test_latest_backup_record_returns_none_when_the_table_is_empty(session: Session) -> None:
    assert latest_backup_record(session) is None


def test_latest_backup_record_returns_the_most_recent_of_several_rows(session: Session) -> None:
    """Explicit, well-separated ``created_at`` values, inserted out of
    chronological order, so the assertion actually proves ordering by
    ``created_at`` descending rather than first/last insertion order."""
    middle = BackupRecord(created_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC))
    newest = BackupRecord(created_at=datetime(2026, 3, 1, 9, 0, 0, tzinfo=UTC))
    oldest = BackupRecord(created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    session.add(middle)
    session.add(newest)
    session.add(oldest)
    session.commit()

    latest = latest_backup_record(session)

    assert latest is not None
    assert latest.id == newest.id


# --- backup_is_stale() --------------------------------------------------------


def _add_report(session: Session, *, created_at: datetime) -> None:
    """One ``Report`` at a given ``created_at``, on a minimal real
    Client -> ReportRun graph -- ``backup_is_stale`` only reads
    ``Report.created_at``, but the FK columns still need real parent rows."""
    client = Client(
        name="Ada Lovelace",
        birth_date=date(2026, 1, 1),
        birth_time=time_of_day(0, 0),
        latitude=Decimal("0"),
        longitude=Decimal("0"),
        iana_zone="UTC",
    )
    session.add(client)
    session.flush()
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.flush()
    session.add(
        Report(
            client_id=client.id,
            report_run_id=run.id,
            style_guide_version=1,
            payload_schema_version=1,
            gate_vocabulary_version=1,
            created_at=created_at,
        )
    )
    session.flush()


def test_backup_is_stale_is_false_when_no_report_exists(session: Session) -> None:
    """Nothing has been generated -> there is nothing a backup could be
    missing, even with no ``backup_record`` row."""
    assert backup_is_stale(session) is False


def test_backup_is_stale_is_true_with_a_report_and_no_backup_record(session: Session) -> None:
    """A Report exists but no backup was ever recorded -> stale (the safe
    default for a freshly restored database)."""
    _add_report(session, created_at=datetime(2026, 1, 1, tzinfo=UTC))
    session.commit()

    assert backup_is_stale(session) is True


def test_backup_is_stale_is_false_when_the_latest_backup_postdates_every_report(
    session: Session,
) -> None:
    _add_report(session, created_at=datetime(2026, 1, 1, tzinfo=UTC))
    session.add(BackupRecord(created_at=datetime(2026, 2, 1, tzinfo=UTC)))
    session.commit()

    assert backup_is_stale(session) is False


def test_backup_is_stale_is_true_when_a_report_postdates_the_latest_backup(
    session: Session,
) -> None:
    session.add(BackupRecord(created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    _add_report(session, created_at=datetime(2026, 2, 1, tzinfo=UTC))
    session.commit()

    assert backup_is_stale(session) is True
