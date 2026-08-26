"""``BackupRecord`` (Story 6.6): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_export_record_store.py`` and
``tests/test_style_guide_store.py``. Covers ``store_backup_record()``'s
write (a fresh row, timestamped with ``created_at`` approximately now) and
``latest_backup_record()``'s two outcomes -- empty table, and picking the
most recent of several rows by ``created_at``, not insertion order.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlmodel import Session, SQLModel, create_engine

from shell.adapters.postgres.backup_record import (
    BackupRecord,
    latest_backup_record,
    store_backup_record,
)


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
