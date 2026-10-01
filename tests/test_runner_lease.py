"""``shell/runner/lease.py::section_claim`` (Story 10.4): the claim on a Section row is one
atomic conditional ``UPDATE`` -- taken only if the row is still ``pending`` with no live
lease -- released only by whoever took it, and reclaimable once it expires."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from shell.adapters.postgres import client as _client  # noqa: F401 -- registers the tables
from shell.adapters.postgres.report_draft_section import ReportDraftSection
from shell.adapters.postgres.report_run import ReportRun
from shell.runner.lease import LEASE_TTL, section_claim

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / 'lease.db'}", connect_args={"timeout": 30})
    SQLModel.metadata.create_all(engine)
    return engine


def _a_section(engine: Engine, **fields: object) -> UUID:
    with Session(engine) as session:
        run = ReportRun(client_id=UUID(int=1), month="2026-01")
        session.add(run)
        session.commit()
        row = ReportDraftSection(
            report_run_id=run.id, attempt=0, ordinal=1, name="energia_generale", **fields
        )
        session.add(row)
        session.commit()
        return row.id


def _row(engine: Engine, section_id: UUID) -> ReportDraftSection:
    with Session(engine) as session:
        row = session.get(ReportDraftSection, section_id)
        assert row is not None
        session.expunge(row)
        return row


def test_a_free_section_is_claimed_for_the_ttl_and_released_on_exit(engine: Engine) -> None:
    section_id = _a_section(engine)

    with section_claim(engine, section_id, now=lambda: NOW) as held:
        assert held is not None
        row = _row(engine, section_id)
        assert row.claimed_at == NOW
        assert row.claim_expires_at == NOW + LEASE_TTL

    row = _row(engine, section_id)
    assert row.claimed_at is None and row.claim_expires_at is None


def test_a_second_claim_while_the_first_is_live_returns_and_changes_nothing(
    engine: Engine,
) -> None:
    section_id = _a_section(engine)

    with section_claim(engine, section_id, now=lambda: NOW) as first:
        before = _row(engine, section_id)
        with section_claim(engine, section_id, now=lambda: NOW + timedelta(seconds=5)) as second:
            assert first == NOW
            assert second is None
        # The refused caller did not free the first caller's lease on exit.
        after = _row(engine, section_id)
        assert after.claim_expires_at == before.claim_expires_at
        assert after.claimed_at == before.claimed_at


def test_an_expired_lease_is_reclaimed(engine: Engine) -> None:
    section_id = _a_section(
        engine, claimed_at=NOW - timedelta(minutes=4), claim_expires_at=NOW - timedelta(minutes=1)
    )

    with section_claim(engine, section_id, now=lambda: NOW) as held:
        assert held == NOW
        assert _row(engine, section_id).claim_expires_at == NOW + LEASE_TTL


def test_a_lease_expiring_exactly_now_is_reclaimable(engine: Engine) -> None:
    section_id = _a_section(engine, claim_expires_at=NOW)

    with section_claim(engine, section_id, now=lambda: NOW) as held:
        assert held is not None


@pytest.mark.parametrize("status", ["complete", "failed"])
def test_a_section_that_is_no_longer_pending_cannot_be_claimed(engine: Engine, status: str) -> None:
    section_id = _a_section(engine, status=status)

    with section_claim(engine, section_id, now=lambda: NOW) as held:
        assert held is None

    assert _row(engine, section_id).claim_expires_at is None


def test_releasing_leaves_a_lease_another_writer_took_after_ours_expired(
    engine: Engine,
) -> None:
    section_id = _a_section(engine)
    late = NOW + LEASE_TTL + timedelta(seconds=1)

    with section_claim(engine, section_id, now=lambda: NOW) as ours:
        assert ours == NOW
        # Our lease expired; another writer reclaims and holds it past our exit.
        theirs = section_claim(engine, section_id, now=lambda: late)
        assert theirs.__enter__() == late
    row = _row(engine, section_id)

    assert row.claimed_at == late
    assert row.claim_expires_at == late + LEASE_TTL
    theirs.__exit__(None, None, None)


def test_an_unknown_section_is_never_held(engine: Engine) -> None:
    with section_claim(engine, UUID(int=42), now=lambda: NOW) as held:
        assert held is None
