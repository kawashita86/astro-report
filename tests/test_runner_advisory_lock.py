"""``shell/runner/advisory_lock.py::try_acquire_advance_lock`` -- Story
3.10's non-blocking single-flight guard for concurrent report-run polls
(AD-20).

The SQLite path (every non-Postgres backend) is a no-op that grants without
touching the database -- asserted here against a statement recorder. The
Postgres SQL shape (``pg_try_advisory_xact_lock`` with the fixed namespace
and ``hashtext(str(run_id))``) is asserted against a captured statement via
a minimal fake session. A real two-connection single-flight check runs only
when ``MIGRATION_TEST_DATABASE_URL`` names a throwaway Postgres, mirroring
``tests/test_migration_chain_on_postgres.py``'s own env gate.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlmodel import Session, SQLModel

from shell.runner.advisory_lock import _ADVANCE_LOCK_NAMESPACE, try_acquire_advance_lock


def test_sqlite_backend_grants_without_touching_the_database() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    with Session(engine) as session:
        granted = try_acquire_advance_lock(session, uuid4())

    assert granted is True
    assert not any("advisory" in statement.lower() for statement in statements), (
        "the non-Postgres path must issue no query at all"
    )


class _FakeDialect:
    name = "postgresql"


class _FakeBind:
    dialect = _FakeDialect()


class _FakeResult:
    def __init__(self, value: bool) -> None:
        self._value = value

    def scalar_one(self) -> bool:
        return self._value


class _FakeSession:
    """Just the two surfaces ``try_acquire_advance_lock`` touches on the
    Postgres path -- ``get_bind().dialect.name`` and ``execute(...)``."""

    def __init__(self, granted: bool = True) -> None:
        self.granted = granted
        self.executed: list[tuple[str, dict]] = []

    def get_bind(self):  # noqa: ANN201
        return _FakeBind()

    def execute(self, statement, params=None):  # noqa: ANN001, ANN201
        self.executed.append((str(statement), params or {}))
        return _FakeResult(self.granted)


def test_the_postgres_path_emits_pg_try_advisory_xact_lock() -> None:
    session = _FakeSession(granted=True)
    run_id = uuid4()

    granted = try_acquire_advance_lock(session, run_id)  # type: ignore[arg-type]

    assert granted is True
    assert len(session.executed) == 1
    sql, params = session.executed[0]
    assert "pg_try_advisory_xact_lock" in sql
    assert "hashtext" in sql
    assert params["key"] == str(run_id)
    assert params["ns"] == _ADVANCE_LOCK_NAMESPACE
    assert -(2**31) <= params["ns"] < 2**31, "namespace must fit in a Postgres int4"


def test_the_postgres_path_returns_false_when_the_lock_is_not_granted() -> None:
    session = _FakeSession(granted=False)

    assert try_acquire_advance_lock(session, uuid4()) is False  # type: ignore[arg-type]


@pytest.mark.skipif(
    os.environ.get("MIGRATION_TEST_DATABASE_URL") is None,
    reason="set MIGRATION_TEST_DATABASE_URL to a throwaway Postgres URL to run the "
    "real-Postgres single-flight test",
)
def test_two_connections_single_flight_on_a_real_postgres() -> None:
    """Two connections both call ``try_acquire_advance_lock`` for one run id:
    exactly one gets the lock, the other gets ``False`` without blocking, and
    the lock is gone once the winner's transaction commits."""
    url = os.environ["MIGRATION_TEST_DATABASE_URL"]
    engine = create_engine(url)
    run_id = uuid4()

    with Session(engine) as winner, Session(engine) as loser:
        assert try_acquire_advance_lock(winner, run_id) is True
        assert try_acquire_advance_lock(loser, run_id) is False, (
            "the second connection must not also get the transaction-scoped lock"
        )

        winner.commit()  # releases the xact lock

        assert try_acquire_advance_lock(loser, run_id) is True, (
            "the lock must be free again once the winner's transaction commits"
        )
        loser.commit()
