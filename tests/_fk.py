"""A SQLite test engine/session with real foreign-key enforcement
(epic-6-retro-item-52 / epic-7-retro-item-54).

SQLite does not enforce foreign keys unless ``PRAGMA foreign_keys=ON`` is
issued on every connection. Production runs on Postgres, which always
enforces them -- so a cascade-delete test run against a default SQLite engine
silently passes on a wrong delete order. ``fk_enforcing_engine()`` registers
the ``PRAGMA`` on a ``"connect"`` listener *before* the first connection,
mirroring the body Story 6.4's regression test in
``tests/test_client_store.py`` originally hand-rolled inline.

The calling test module must already have imported its model modules (so
every table is registered on ``SQLModel.metadata``) before
``fk_enforcing_engine`` runs ``create_all`` -- otherwise the tables it needs
simply will not be created.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine


def fk_enforcing_engine() -> Engine:
    """A fresh in-memory SQLite engine with ``PRAGMA foreign_keys=ON`` armed
    on every connection and ``SQLModel.metadata`` already created."""
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, connection_record: object) -> None:
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


@contextmanager
def fk_enforcing_session() -> Iterator[Session]:
    """A ``Session`` against :func:`fk_enforcing_engine` -- drop-in for a
    module's ``session`` pytest fixture."""
    engine = fk_enforcing_engine()
    with Session(engine) as session:
        yield session
