"""``try_acquire_advance_lock``: the non-blocking single-flight guard that
lets exactly one concurrent caller advance a given ``ReportRun`` by one stage
(AD-20, Story 3.10; callers are the ``RunDriver``'s loops since Story 10.4).

``shell/runner/advance.py::advance()`` performs at most one stage transition
per call and is invoked only by the driver's per-run loop. Two loops for the
same run can still collide (two processes during a rolling deploy, a restart's
``resume()`` racing a ``start``); on Postgres each takes a transaction-scoped
advisory lock keyed on the run id, so the caller that wins advances one stage
and commits -- which releases the lock -- while the loser returns the run's
current stage untouched.

A row lock (``SELECT ... FOR UPDATE`` on the ``ReportRun`` row) would
serialize the callers too, but the loser would then block until the winner
commits -- for a slow stage that is its whole duration plus its backoff, a caller
stuck behind another's work for no reason.
``pg_try_advisory_xact_lock`` is non-blocking: the loser gets ``False`` at
once and looks again later. Transaction-scoped (``_xact_``) means
Postgres releases it on ``advance()``'s own ``commit()`` / ``rollback()``,
or if the connection drops -- there is no ``pg_advisory_unlock`` to leak on
an error path.

Every non-Postgres backend (SQLite, in the test suite) returns ``True``
without touching the database: those run a whole test on one connection, so
there is no cross-connection concurrency to guard, and ``advance.py``'s
concurrent-``advance()`` unique-constraint ``IntegrityError`` classification
still stands there as defense-in-depth.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

__all__ = ["try_acquire_advance_lock"]

#: Fixed ``int4`` namespace for every ``pg_try_advisory_xact_lock`` call this
#: module makes -- the two-argument ``(int4, int4)`` form, with the second
#: argument ``hashtext(str(run_id))``, so distinct runs take distinct locks
#: and this module's locks never collide with another advisory-lock user's.
#: An arbitrary constant (ASCII ``"ADV1"``); it only has to stay stable and
#: stay ours.
_ADVANCE_LOCK_NAMESPACE = 0x41445631


def try_acquire_advance_lock(session: Session, run_id: UUID) -> bool:
    """Try, without blocking, to take the advance lock for ``run_id``.

    On Postgres, runs ``SELECT pg_try_advisory_xact_lock(:ns,
    hashtext(:key))`` with the fixed :data:`_ADVANCE_LOCK_NAMESPACE` and
    ``:key = str(run_id)``, and returns whether the lock was granted. The
    lock is transaction-scoped -- Postgres releases it on the caller's own
    ``commit()`` / ``rollback()`` (or a dropped connection), so there is no
    explicit unlock. On every other dialect returns ``True`` immediately,
    with no query.
    """
    if session.get_bind().dialect.name != "postgresql":
        return True
    granted = session.execute(
        text("SELECT pg_try_advisory_xact_lock(:ns, hashtext(:key))"),
        {"ns": _ADVANCE_LOCK_NAMESPACE, "key": str(run_id)},
    ).scalar_one()
    return bool(granted)
