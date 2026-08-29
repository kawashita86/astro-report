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

from shell.adapters.postgres.columns import _UTCDateTime
from shell.adapters.postgres.report import Report

__all__ = [
    "BackupRecord",
    "backup_is_stale",
    "latest_backup_record",
    "store_backup_record",
]


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


def backup_is_stale(session: Session) -> bool:
    """Whether the newest ``Report`` anywhere in the system postdates the
    last recorded backup (Story 6.6) -- computed globally, not scoped to any
    one Client, since one un-backed-up Report anywhere is the durability gap
    this warns about.

    No ``Report`` at all -> never stale, even with no ``backup_record`` row
    yet: there is nothing new a backup could be missing. Otherwise, no
    ``backup_record`` row at all -> stale (the safe default for a freshly
    restored database).

    Promoted here from ``shell/http/routes/clients.py::_backup_is_stale``
    (Story 9.2): it is now read by two screens -- the Client reports page and
    the Home dashboard -- and belongs beside ``latest_backup_record`` /
    ``store_backup_record`` rather than imported ``_``-private across route
    modules. ``clients.py`` keeps a one-line delegate under the old name so
    its existing importers need no churn.
    """
    newest_report_created_at = session.exec(
        select(Report.created_at).order_by(Report.created_at.desc())
    ).first()
    if newest_report_created_at is None:
        return False

    latest_backup = latest_backup_record(session)
    if latest_backup is None:
        return True

    return newest_report_created_at > latest_backup.created_at


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
