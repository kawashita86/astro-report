"""``StyleGuide``: append-only versioned rows behind Francesco's own register
for the Generator's Section prose (Story 4.1, Story 4.2).

Version 1 is seeded exactly once, by ``migrations/versions/0007_style_guide.py``,
from ``data/style-guide.seed.md``. Every revision after that is a new row --
``version = max + 1``, inserted by :func:`create_style_guide_version` -- read
back by :func:`current_style_guide`. No row is ever updated or deleted: this
mirrors ``ReportPayload``'s (``shell/adapters/postgres/report_payload.py``)
``before_update`` immutability listener exactly, for the same reason -- once
Story 4.5's Generator exists and a Report cites a Style Guide version, that
citation must mean the same thing years later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Column, Text, event
from sqlalchemy.orm import Mapper
from sqlmodel import Field, Session, SQLModel, select
from uuid6 import uuid7

from shell.adapters.postgres.columns import _UTCDateTime

__all__ = [
    "StyleGuide",
    "StyleGuideMissingError",
    "create_style_guide_version",
    "current_style_guide",
]


class StyleGuide(SQLModel, table=True):
    """One version of the Style Guide, append-only.

    ``version`` is unique and monotonic from 1, enforced at the schema level
    by ``migrations/versions/0007_style_guide.py``'s unique index -- not
    merely by :func:`create_style_guide_version` always inserting ``max + 1``.
    """

    __tablename__ = "style_guide"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    version: int = Field(unique=True, index=True)
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of column
    # type/`nullable` from the type annotation, so `Text`/`nullable=False`
    # must be given explicitly here -- matching the migration's own `Text`,
    # `NOT NULL` column (a plain `str` field would otherwise default to an
    # unbounded `VARCHAR`, a schema drift from what the migration created).
    content: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(_UTCDateTime, nullable=False),
    )


class StyleGuideMissingError(RuntimeError):
    """``style_guide`` has no rows -- there is no current Style Guide to read.

    Raised only by :func:`current_style_guide`. Expected only before
    migration 0007 has ever run against this database; every deploy from that
    point on seeds version 1, so hitting this in production is a startup- or
    migration-ordering bug, not a normal runtime state.
    """


@event.listens_for(StyleGuide, "before_update")
def _forbid_update(
    mapper: Mapper[StyleGuide], connection: object, target: StyleGuide
) -> None:
    """A persisted ``StyleGuide`` row is immutable, unconditionally -- a
    revision is always a new row, never a rewrite of an old one. No code path
    updates a row; this makes an accidental one fail loudly rather than
    silently rewriting a version some future Report may already cite."""
    del mapper, connection, target
    raise RuntimeError(
        "StyleGuide rows are immutable once persisted -- no code path may update one."
    )


def current_style_guide(session: Session) -> StyleGuide:
    """The highest-version ``StyleGuide`` row.

    Raises :class:`StyleGuideMissingError` naming the empty table if no row
    exists yet.
    """
    current = session.exec(select(StyleGuide).order_by(StyleGuide.version.desc())).first()
    if current is None:
        raise StyleGuideMissingError(
            "style_guide has no rows -- current_style_guide() has nothing to read; "
            "migration 0007_style_guide should already have seeded version 1."
        )
    return current


def create_style_guide_version(session: Session, content: str) -> StyleGuide:
    """Append a new Style Guide version: ``version = max + 1``.

    Never updates or deletes a prior row -- mirrors ``store_report_payload()``
    (``shell/adapters/postgres/report_payload.py``): this only ``add()``s and
    ``flush()``es, never commits or rolls back, so it never decides the
    caller's transaction boundary.
    """
    current = session.exec(select(StyleGuide).order_by(StyleGuide.version.desc())).first()
    next_version = 1 if current is None else current.version + 1
    style_guide = StyleGuide(version=next_version, content=content)
    session.add(style_guide)
    session.flush()
    return style_guide
