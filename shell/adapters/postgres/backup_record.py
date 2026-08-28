"""``BackupRecord``: the timestamp of one completed ``GET /backup`` download
(Story 6.6) -- what the Report History warning compares the newest ``Report``
against to decide whether Francesco's last backup is out of date.

Global/versionless, mirroring ``StyleGuide``'s own shape
(``shell/adapters/postgres/style_guide.py``): no ``client_id``, so it is
correctly excluded from the FR-29 Client-deletion cascade
(``shell/adapters/postgres/client.py``) automatically, not by an explicit
exemption. Append-only -- one row per completed backup, never updated or
deleted -- but unlike ``StyleGuide`` there is no ordinal ``version`` column
to enforce uniqueness on; ``created_at`` alone, most-recent-first, is all
``latest_backup_record()`` ever needs.

Written by :func:`store_backup_record`, called from
``shell/http/routes/backup.py``'s ``download_backup`` only after the export
body is already built, right before the response is returned -- so a row is
recorded only for a backup that actually completed. Since retro-C item 49,
``download_backup`` calls it only for a deliberate ``?record=1`` request; a
bare ``GET /backup`` serves the export but records nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Column
from sqlmodel import Field, Session, SQLModel, select
from uuid6 import uuid7

from shell.adapters.postgres.report_run import _UTCDateTime

__all__ = ["BackupRecord", "latest_backup_record", "store_backup_record"]


class BackupRecord(SQLModel, table=True):
    """One completed ``GET /backup`` download, timestamped."""

    __tablename__ = "backup_record"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


def latest_backup_record(session: Session) -> BackupRecord | None:
    """The most recently recorded backup, or ``None`` if none has ever
    completed -- mirrors ``current_style_guide()``
    (``shell/adapters/postgres/style_guide.py``), except returning ``None``
    rather than raising: "never backed up" is an expected, ordinary state
    here, not a migration-ordering bug.
    """
    return session.exec(
        select(BackupRecord).order_by(BackupRecord.created_at.desc())
    ).first()


def store_backup_record(session: Session) -> BackupRecord:
    """Record one completed backup, in one flush.

    Only ``add()``s and ``flush()``es, never commits or rolls back --
    mirrors ``store_export_record()``
    (``shell/adapters/postgres/export_record.py``), so it never decides the
    caller's transaction boundary. ``download_backup`` commits immediately
    after calling this.
    """
    backup_record = BackupRecord()
    session.add(backup_record)
    session.flush()
    return backup_record
