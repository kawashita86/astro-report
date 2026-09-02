"""``ReportDraft`` (Story 4.6): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_report_theme_store.py``. Covers the row's
own shape, ``store_report_draft()``'s writes, the ``before_update``
immutability guard, uniqueness on ``report_run_id``, and that
``report_draft`` joins the FR-29 Client-deletion cascade.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlmodel import Session, SQLModel, create_engine, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.generation import GeneratedDraft, Sentence
from core.types.place import ResolvedPlace
from shell.adapters.postgres import client as client_module
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.report_draft import (
    ReportDraft,
    next_report_draft_attempt,
    store_report_draft,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_client_store.py and tests/test_report_theme_store.py use.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _a_draft() -> GeneratedDraft:
    return GeneratedDraft(
        energia_generale=(Sentence(text="Un mese di energia stabile.", entry_ids=("abc123",)),),
        amore=(Sentence(text="Venere sostiene i legami.", entry_ids=("def456",)),),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(Sentence(text="Prenditi cura di te.", entry_ids=()),),
    )


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


def _create_run(session: Session, client: Client) -> ReportRun:
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()
    return run


# --- ReportDraft row shape ------------------------------------------------


def test_a_report_draft_id_is_uuidv7(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_draft(
        session, run=run, style_guide_version=1, sections_config_version=1, draft=_a_draft()
    )
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_store_report_draft_persists_identity_and_the_whole_draft_as_json(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    draft = _a_draft()

    stored = store_report_draft(
        session,
        run=run,
        style_guide_version=3,
        sections_config_version=2,
        draft=draft,
    )
    session.commit()

    reloaded = session.get(ReportDraft, stored.id)
    assert reloaded is not None
    assert reloaded.client_id == client.id
    assert reloaded.report_run_id == run.id
    assert reloaded.style_guide_version == 3
    assert reloaded.sections_config_version == 2
    assert reloaded.attempt == 0, "attempt defaults to 0 when not passed explicitly"
    assert reloaded.created_at is not None

    assert reloaded.draft["energia_generale"] == [
        {"text": "Un mese di energia stabile.", "entry_ids": ["abc123"]}
    ]
    assert reloaded.draft["lavoro"] == []
    assert reloaded.draft["consiglio_finale"] == [
        {"text": "Prenditi cura di te.", "entry_ids": []}
    ]


def test_store_report_draft_only_flushes_never_commits(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_draft(
        session, run=run, style_guide_version=1, sections_config_version=1, draft=_a_draft()
    )
    stored_id = stored.id
    session.rollback()

    assert session.get(ReportDraft, stored_id) is None


# --- Immutability ------------------------------------------------------------


def test_mutating_and_committing_a_persisted_report_draft_raises(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_draft(
        session, run=run, style_guide_version=1, sections_config_version=1, draft=_a_draft()
    )
    session.commit()

    stored.style_guide_version = 99
    session.add(stored)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    assert "immutable" in str(caught.value)


# --- Uniqueness ----------------------------------------------------------------


def test_a_second_report_draft_at_the_same_attempt_raises_integrity_error(
    session: Session,
) -> None:
    """Exactly one ``ReportDraft`` per ``(ReportRun, attempt)`` (Story 5.4
    loosened this from "per ``ReportRun``"), enforced by a unique constraint
    on ``(report_run_id, attempt)`` -- not merely by ``store_report_draft()``
    only ever being called once per attempt in
    ``shell/runner/driver.py``'s ``draft_ready`` stage."""
    client = _create_client(session)
    run = _create_run(session, client)

    store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_a_draft(),
        attempt=0,
    )
    session.commit()

    with pytest.raises(IntegrityError):
        store_report_draft(
            session,
            run=run,
            style_guide_version=1,
            sections_config_version=1,
            draft=_a_draft(),
            attempt=0,
        )

    session.rollback()


def test_a_second_report_draft_at_a_different_attempt_for_the_same_run_succeeds(
    session: Session,
) -> None:
    """A second draft for the same ``ReportRun`` is no longer a bug once
    regeneration is real (Story 5.4) -- only a repeated ``attempt`` for the
    same run conflicts."""
    client = _create_client(session)
    run = _create_run(session, client)

    first = store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_a_draft(),
        attempt=0,
    )
    second = store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_a_draft(),
        attempt=1,
    )
    session.commit()

    stored_drafts = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).all()
    assert {stored.id for stored in stored_drafts} == {first.id, second.id}
    assert {stored.attempt for stored in stored_drafts} == {0, 1}


def test_two_report_runs_for_one_client_each_get_their_own_report_draft_row(
    session: Session,
) -> None:
    client = _create_client(session)
    first_run = _create_run(session, client)
    second_run = ReportRun(client_id=client.id, month="2026-02")
    session.add(second_run)
    session.commit()

    store_report_draft(
        session, run=first_run, style_guide_version=1, sections_config_version=1, draft=_a_draft()
    )
    store_report_draft(
        session, run=second_run, style_guide_version=1, sections_config_version=1, draft=_a_draft()
    )
    session.commit()

    stored_drafts = session.exec(
        select(ReportDraft).where(ReportDraft.client_id == client.id)
    ).all()
    assert {stored.report_run_id for stored in stored_drafts} == {first_run.id, second_run.id}


# --- Story 5.8: next_report_draft_attempt() -----------------------------------


def test_next_report_draft_attempt_is_zero_for_a_run_with_no_drafts(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    assert next_report_draft_attempt(session, run.id) == 0


def test_next_report_draft_attempt_is_n_after_n_drafts_stored(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_a_draft(),
        attempt=0,
    )
    assert next_report_draft_attempt(session, run.id) == 1

    store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_a_draft(),
        attempt=1,
    )
    assert next_report_draft_attempt(session, run.id) == 2


def test_next_report_draft_attempt_counts_rows_regardless_of_which_code_path_wrote_them(
    session: Session,
) -> None:
    """The count is a plain count of existing rows for the run -- it does not
    care whether ``attempt`` values are contiguous or in what order they were
    written, which is exactly what lets a hand-correction (Story 5.8) mint a
    row without ever touching ``ReportRun.regeneration_count``."""
    client = _create_client(session)
    run = _create_run(session, client)

    store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_a_draft(),
        attempt=0,
    )
    store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_a_draft(),
        attempt=1,
    )

    assert next_report_draft_attempt(session, run.id) == 2


def test_next_report_draft_attempt_is_scoped_to_its_own_run(session: Session) -> None:
    client = _create_client(session)
    first_run = _create_run(session, client)
    second_run = ReportRun(client_id=client.id, month="2026-02")
    session.add(second_run)
    session.commit()

    store_report_draft(
        session,
        run=first_run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_a_draft(),
        attempt=0,
    )

    assert next_report_draft_attempt(session, first_run.id) == 1
    assert next_report_draft_attempt(session, second_run.id) == 0


# --- FR-29 cascade ---------------------------------------------------------------


def test_delete_client_and_derived_removes_its_report_drafts(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_report_draft(
        session, run=run, style_guide_version=1, sections_config_version=1, draft=_a_draft()
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(ReportRun, run.id) is None
    assert session.get(ReportDraft, stored.id) is None


def test_delete_client_and_derived_does_not_persist_report_draft_deletion_without_a_commit(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_report_draft(
        session, run=run, style_guide_version=1, sections_config_version=1, draft=_a_draft()
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(ReportDraft, stored.id) is not None


def test_the_cascade_constant_includes_report_draft() -> None:
    """Story 4.6: ``report_draft`` must join ``_CLIENT_CASCADE_TABLES`` -- a
    regression on top of the general invariant test in
    ``tests/test_client_store.py``, naming the table this story added
    explicitly."""
    assert "report_draft" in client_module._CLIENT_CASCADE_TABLES


def test_every_table_with_a_client_id_foreign_key_includes_report_draft() -> None:
    tables_with_client_fk = {
        table.name
        for table in SQLModel.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if foreign_key.column.table.name == "client" and foreign_key.column.name == "id"
    }
    assert "report_draft" in tables_with_client_fk
