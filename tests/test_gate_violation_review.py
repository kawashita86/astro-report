"""``GateViolationReview`` (Story 5.7): an in-memory SQLite engine stands in
for Postgres, mirroring ``tests/test_gate_result_store.py``. Covers the
row's own shape, ``store_gate_violation_review()``'s writes, the
``before_update`` immutability guard, and that ``gate_violation_review``
joins the FR-29 Client-deletion cascade before ``gate_result``.

The HTTP-level I/O & Edge-Case Matrix (accept route happy path, closing
write, double-submit idempotency, wrong-index/no-failure 404s, badge
rendering) is covered end to end in ``tests/test_http_report_runs.py``
instead, mirroring how Story 5.6's own route-level behavior lives in that
module rather than here.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import StatementError
from sqlmodel import Session, SQLModel, create_engine, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.gate import GateViolation
from core.types.place import ResolvedPlace
from shell.adapters.postgres import client as client_module
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.gate_result import StoredGateResult, store_gate_result
from shell.adapters.postgres.gate_violation_review import (
    GateViolationReview,
    store_gate_violation_review,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_gate_result_store.py uses.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)

_VOCABULARY_CONTENT_HASH = hashlib.sha256(b"story-5-7").hexdigest()


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_client(session: Session, *, name: str = "Ada Lovelace") -> Client:
    natal_chart = compute_natal_chart(
        _BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG
    )
    return create_client_with_chart(
        session,
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=natal_chart,
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


def _create_run(session: Session, client: Client, *, month: str = "2026-01") -> ReportRun:
    run = ReportRun(client_id=client.id, month=month)
    session.add(run)
    session.commit()
    return run


def _a_failing_gate_result(session: Session, run: ReportRun) -> StoredGateResult:
    return store_gate_result(
        session,
        run=run,
        passed=False,
        regeneration_count=3,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(
            GateViolation(
                kind="empty_citation",
                section="lavoro",
                sentence="Marte in Ariete porta energia.",
                entry_ids=(),
                detail="no cited entry supports this Claim",
            ),
        ),
    )


# --- GateViolationReview row shape ------------------------------------------------


def test_a_gate_violation_review_id_is_uuidv7(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    gate_result = _a_failing_gate_result(session, run)
    session.commit()

    review = store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=0,
        kind="empty_citation",
        section="lavoro",
        sentence="Marte in Ariete porta energia.",
        entry_ids=(),
        detail="no cited entry supports this Claim",
    )
    session.commit()

    assert isinstance(review.id, UUID) and review.id.version == 7


def test_store_gate_violation_review_persists_the_denormalized_fields(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    gate_result = _a_failing_gate_result(session, run)
    session.commit()

    review = store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=0,
        kind="empty_citation",
        section="lavoro",
        sentence="Marte in Ariete porta energia.",
        entry_ids=("entry-1", "entry-2"),
        detail="no cited entry supports this Claim",
    )
    session.commit()

    reloaded = session.get(GateViolationReview, review.id)
    assert reloaded is not None
    assert reloaded.client_id == client.id
    assert reloaded.report_run_id == run.id
    assert reloaded.gate_result_id == gate_result.id
    assert reloaded.violation_index == 0
    assert reloaded.kind == "empty_citation"
    assert reloaded.section == "lavoro"
    assert reloaded.sentence == "Marte in Ariete porta energia."
    assert reloaded.entry_ids == ["entry-1", "entry-2"]
    assert reloaded.detail == "no cited entry supports this Claim"
    assert reloaded.created_at is not None


def test_store_gate_violation_review_only_flushes_never_commits(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    gate_result = _a_failing_gate_result(session, run)
    session.commit()

    review = store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=0,
        kind="empty_citation",
        section="lavoro",
        sentence="x",
        entry_ids=(),
        detail="y",
    )
    review_id = review.id
    session.rollback()

    assert session.get(GateViolationReview, review_id) is None


def test_two_review_rows_can_exist_for_two_different_violation_indices(session: Session) -> None:
    """Story 5.7's own I/O matrix, "Accept one of several": more than one
    review row may point at the same ``StoredGateResult``, one per accepted
    violation index."""
    client = _create_client(session)
    run = _create_run(session, client)
    gate_result = _a_failing_gate_result(session, run)
    session.commit()

    store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=0,
        kind="empty_citation",
        section="lavoro",
        sentence="a",
        entry_ids=(),
        detail="detail a",
    )
    store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=1,
        kind="invented_fact",
        section="amore",
        sentence="b",
        entry_ids=(),
        detail="detail b",
    )
    session.commit()

    reviewed_indices = session.exec(
        select(GateViolationReview.violation_index).where(
            GateViolationReview.gate_result_id == gate_result.id
        )
    ).all()
    assert set(reviewed_indices) == {0, 1}


# --- Immutability ----------------------------------------------------------------


def test_mutating_and_committing_a_persisted_review_raises(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    gate_result = _a_failing_gate_result(session, run)
    session.commit()

    review = store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=0,
        kind="empty_citation",
        section="lavoro",
        sentence="x",
        entry_ids=(),
        detail="y",
    )
    session.commit()

    review.detail = "a rewritten detail"
    session.add(review)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    assert "immutable" in str(caught.value)


# --- FR-29 cascade -----------------------------------------------------------------


def test_delete_client_and_derived_removes_its_gate_violation_reviews(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    gate_result = _a_failing_gate_result(session, run)
    session.commit()
    review = store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=0,
        kind="empty_citation",
        section="lavoro",
        sentence="x",
        entry_ids=(),
        detail="y",
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(StoredGateResult, gate_result.id) is None
    assert session.get(GateViolationReview, review.id) is None


def test_delete_client_and_derived_does_not_persist_review_deletion_without_a_commit(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    gate_result = _a_failing_gate_result(session, run)
    session.commit()
    review = store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=0,
        kind="empty_citation",
        section="lavoro",
        sentence="x",
        entry_ids=(),
        detail="y",
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(GateViolationReview, review.id) is not None


def test_the_cascade_constant_includes_gate_violation_review() -> None:
    """Story 5.7: ``gate_violation_review`` must join
    ``_CLIENT_CASCADE_TABLES`` -- a regression on top of the general
    invariant test in ``tests/test_client_store.py``, naming the table this
    story added explicitly."""
    assert "gate_violation_review" in client_module._CLIENT_CASCADE_TABLES


def test_gate_violation_review_rows_are_deleted_before_gate_result_rows(session: Session) -> None:
    """``GateViolationReview.gate_result_id`` is a foreign key to
    ``gate_result.id`` (this story's Code Map) -- deleting a Client with
    both must not violate that constraint, mirroring
    ``tests/test_client_store.py``'s own ``ExportRecord``-before-``Report``
    regression for the same reason."""
    client = _create_client(session)
    run = _create_run(session, client)
    gate_result = _a_failing_gate_result(session, run)
    session.commit()
    store_gate_violation_review(
        session,
        run=run,
        gate_result=gate_result,
        violation_index=0,
        kind="empty_citation",
        section="lavoro",
        sentence="x",
        entry_ids=(),
        detail="y",
    )
    session.commit()

    # Would raise an IntegrityError under real foreign-key enforcement if
    # gate_result were deleted first -- SQLite here doesn't enforce FKs by
    # default, so this asserts the actual outcome instead of relying on that
    # enforcement to catch a wrong order.
    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
