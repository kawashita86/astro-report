"""``ReportDraftSection`` (Story 10.4, AD-21): the row's shape, the unique
``(report_run_id, attempt, ordinal)`` key, ``open_section_rows``' idempotence and the
cascade-delete with the Client -- checked against an FK-enforcing SQLite, which ignores
foreign keys by default and would let a wrong delete order pass."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from core.draft_state import SECTION_NAMES
from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.generation import Sentence
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.report_draft_section import (
    ReportDraftSection,
    open_section_rows,
    section_rows,
    section_state,
    sentences_from_json,
    sentences_to_json,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from tests._fk import fk_enforcing_session

_CONFIG = load_computation_config()
_PLACE = ResolvedPlace(
    latitude=Decimal("32.7358"),
    longitude=Decimal("-97.3453"),
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)


@pytest.fixture
def session():
    with fk_enforcing_session() as session:
        yield session


def _a_client_with_a_run(session: Session) -> tuple[Client, ReportRun]:
    chart = compute_natal_chart(
        datetime(2026, 1, 1, 6, 0, tzinfo=UTC), _PLACE.latitude, _PLACE.longitude, _CONFIG
    )
    client = create_client_with_chart(
        session,
        name="Ada Lovelace",
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_PLACE,
        natal_chart=chart,
        computation_config=_CONFIG,
        ephemeris_identity=verify_ephemeris_identity(),
    )
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()
    return client, run


def test_opening_an_attempt_creates_eight_pending_rows_in_section_order(session: Session) -> None:
    _, run = _a_client_with_a_run(session)

    assert open_section_rows(session, run.id, 0) is True
    session.commit()

    rows = section_rows(session, run.id, 0)
    assert [row.ordinal for row in rows] == list(range(1, 9))
    assert tuple(row.name for row in rows) == SECTION_NAMES
    assert {row.status for row in rows} == {"pending"}
    assert {row.attempts for row in rows} == {0}
    assert all(row.sentences is None and row.last_error is None for row in rows)
    assert all(row.claimed_at is None and row.claim_expires_at is None for row in rows)


def test_opening_the_same_attempt_twice_creates_nothing_the_second_time(session: Session) -> None:
    _, run = _a_client_with_a_run(session)
    open_section_rows(session, run.id, 0)
    session.commit()

    assert open_section_rows(session, run.id, 0) is False
    session.commit()

    assert len(section_rows(session, run.id, 0)) == 8
    # The session survives the conflict: a different attempt opens fine.
    assert open_section_rows(session, run.id, 1) is True
    session.commit()
    assert len(section_rows(session, run.id, 1)) == 8


def test_the_unique_key_is_enforced_by_the_schema(session: Session) -> None:
    _, run = _a_client_with_a_run(session)
    session.add(ReportDraftSection(report_run_id=run.id, attempt=0, ordinal=1, name="amore"))
    session.commit()

    session.add(ReportDraftSection(report_run_id=run.id, attempt=0, ordinal=1, name="amore"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_sentences_round_trip_through_their_json_form() -> None:
    sentences = (
        Sentence(text="Un mese intenso.", entry_ids=("id-1", "id-2")),
        Sentence(text="Respira.", entry_ids=()),
    )

    assert sentences_from_json(sentences_to_json(sentences)) == sentences
    assert sentences_to_json(sentences)[0] == {
        "text": "Un mese intenso.",
        "entry_ids": ["id-1", "id-2"],
    }


def test_a_stored_row_reads_back_as_the_frozen_state_core_reasons_about(session: Session) -> None:
    _, run = _a_client_with_a_run(session)
    expires = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    session.add(
        ReportDraftSection(
            report_run_id=run.id,
            attempt=0,
            ordinal=3,
            name="lavoro",
            attempts=2,
            claim_expires_at=expires,
        )
    )
    session.commit()

    state = section_state(section_rows(session, run.id, 0)[0])

    assert (state.ordinal, state.status, state.attempts) == (3, "pending", 2)
    assert state.claim_expires_at == expires


def test_deleting_a_client_deletes_its_section_rows_without_a_foreign_key_error(
    session: Session,
) -> None:
    client, run = _a_client_with_a_run(session)
    open_section_rows(session, run.id, 0)
    open_section_rows(session, run.id, 1)
    session.commit()
    assert len(session.exec(select(ReportDraftSection)).all()) == 16

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.exec(select(ReportDraftSection)).all() == []
    assert session.exec(select(ReportRun)).all() == []


def test_deleting_one_client_leaves_another_clients_sections(session: Session) -> None:
    client, run = _a_client_with_a_run(session)
    other_run = ReportRun(client_id=client.id, month="2026-02")
    session.add(other_run)
    session.commit()
    open_section_rows(session, other_run.id, 0)
    session.commit()

    # a second Client with its own run and rows
    other_client = Client(
        name="Grace",
        birth_date=date(2026, 1, 2),
        birth_time=time(0, 0),
        latitude=Decimal("1"),
        longitude=Decimal("1"),
        iana_zone="UTC",
    )
    session.add(other_client)
    session.commit()
    keep_run = ReportRun(client_id=other_client.id, month="2026-01")
    session.add(keep_run)
    session.commit()
    open_section_rows(session, keep_run.id, 0)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    remaining = session.exec(select(ReportDraftSection)).all()
    assert {row.report_run_id for row in remaining} == {keep_run.id}
