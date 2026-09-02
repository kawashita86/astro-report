"""``StoredGateResult`` (Story 5.6): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_report_store.py``. Covers the row's own
shape, ``store_gate_result()``'s writes on both a pass and a fail, the
``before_update`` immutability guard, that ``gate_result`` joins the FR-29
Client-deletion cascade, and -- the story's own AC2 -- that first-generation
pass rate and regeneration count as a series are both directly computable
from stored rows with no new production query function.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import StatementError
from sqlmodel import Session, SQLModel, create_engine, func, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.gate.run import _index_entries
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.gate import GateViolation
from core.types.generation import GeneratedDraft, Sentence
from core.types.payload import Payload, SectionPayload
from core.types.place import ResolvedPlace
from core.types.transits import TransitAspectEvent
from shell.adapters.postgres import client as client_module
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.gate_result import StoredGateResult, store_gate_result
from shell.adapters.postgres.report import Report, store_report
from shell.adapters.postgres.report_draft import ReportDraft, store_report_draft
from shell.adapters.postgres.report_payload import ReportPayload, store_report_payload
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from shell.sections import load_sections_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_report_store.py uses.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)

# A stand-in for ``GateVocabulary.content_hash`` -- a 64-char sha256 hex
# digest (epic-5-retro item 45).
_VOCABULARY_CONTENT_HASH = hashlib.sha256(b"epic-5-retro-item-45").hexdigest()


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


def _a_violation(**overrides: object) -> GateViolation:
    fields = {
        "kind": "empty_citation",
        "section": "energia_generale",
        "sentence": "Marte in Ariete porta energia.",
        "entry_ids": (),
        "detail": "no cited entry supports this Claim",
    }
    fields.update(overrides)
    return GateViolation(**fields)


# --- StoredGateResult row shape ------------------------------------------------


def test_a_gate_result_id_is_uuidv7(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_store_gate_result_persists_a_passing_check(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=0,
        vocabulary_version=3,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    session.commit()

    reloaded = session.get(StoredGateResult, stored.id)
    assert reloaded is not None
    assert reloaded.client_id == client.id
    assert reloaded.report_run_id == run.id
    assert reloaded.passed is True
    assert reloaded.regeneration_count == 0
    assert reloaded.vocabulary_version == 3
    assert reloaded.vocabulary_content_hash == _VOCABULARY_CONTENT_HASH
    assert reloaded.violations == []
    assert reloaded.created_at is not None


def test_store_gate_result_persists_a_failing_check_with_its_violations(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    violation = _a_violation()

    stored = store_gate_result(
        session,
        run=run,
        passed=False,
        regeneration_count=1,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(violation,),
    )
    session.commit()

    reloaded = session.get(StoredGateResult, stored.id)
    assert reloaded is not None
    assert reloaded.passed is False
    assert reloaded.regeneration_count == 1
    assert reloaded.violations == [
        {
            "kind": "empty_citation",
            "section": "energia_generale",
            "sentence": "Marte in Ariete porta energia.",
            "entry_ids": [],
            "detail": "no cited entry supports this Claim",
        }
    ]


def test_store_gate_result_persists_the_vocabulary_content_hash_on_a_fail_row(
    session: Session,
) -> None:
    """The digest threaded from ``GateVocabulary.content_hash`` is written on
    a failing row too (the fail path sources it straight off ``vocabulary``
    in ``shell/runner/driver.py``) and survives a write/read round-trip
    (epic-5-retro item 45)."""
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_gate_result(
        session,
        run=run,
        passed=False,
        regeneration_count=1,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(_a_violation(),),
    )
    session.commit()

    reloaded = session.get(StoredGateResult, stored.id)
    assert reloaded is not None
    assert reloaded.vocabulary_content_hash == _VOCABULARY_CONTENT_HASH


def test_two_gate_result_rows_with_equal_version_but_different_hash_are_distinguishable(
    session: Session,
) -> None:
    """I/O & Edge-Case Matrix: a forgotten ``GateVocabulary.version`` bump on
    a content edit is now detectable after the fact -- two rows with equal
    ``vocabulary_version`` but different ``vocabulary_content_hash`` can be
    told apart by a direct query (epic-5-retro item 45)."""
    client = _create_client(session)
    run = _create_run(session, client)
    other_hash = hashlib.sha256(b"a-different-vocabulary").hexdigest()

    store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=0,
        vocabulary_version=7,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=1,
        vocabulary_version=7,
        vocabulary_content_hash=other_hash,
        violations=(),
    )
    session.commit()

    distinct_hashes = session.exec(
        select(StoredGateResult.vocabulary_content_hash)
        .where(StoredGateResult.vocabulary_version == 7)
        .distinct()
    ).all()
    assert set(distinct_hashes) == {_VOCABULARY_CONTENT_HASH, other_hash}


def test_a_gate_result_row_written_without_the_hash_reads_back_none(session: Session) -> None:
    """A row inserted before migration ``0021`` -- modelled here by building
    ``StoredGateResult`` directly without the new field -- reads the new
    column as ``None``, never crashing (epic-5-retro item 45)."""
    client = _create_client(session)
    run = _create_run(session, client)

    row = StoredGateResult(
        client_id=client.id,
        report_run_id=run.id,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        violations=[],
    )
    session.add(row)
    session.commit()

    reloaded = session.get(StoredGateResult, row.id)
    assert reloaded is not None
    assert reloaded.vocabulary_content_hash is None


def test_store_gate_result_only_flushes_never_commits(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    stored_id = stored.id
    session.rollback()

    assert session.get(StoredGateResult, stored_id) is None


# --- Many rows per ReportRun (unlike Report) -----------------------------------


def test_report_run_id_is_not_unique_across_gate_result_rows(session: Session) -> None:
    """Unlike ``Report.report_run_id`` (Story 5.3), ``report_run_id`` here is
    indexed but not unique -- a run may regenerate (Story 5.4), and each
    attempt's Gate check gets its own row."""
    client = _create_client(session)
    run = _create_run(session, client)

    store_gate_result(
        session,
        run=run,
        passed=False,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(_a_violation(),),
    )
    store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=1,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    session.commit()

    stored = session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all()
    assert len(stored) == 2
    assert {row.regeneration_count for row in stored} == {0, 1}


# --- Immutability ----------------------------------------------------------------


def test_mutating_and_committing_a_persisted_gate_result_raises(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    session.commit()

    stored.passed = False
    session.add(stored)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    assert "immutable" in str(caught.value)


# --- FR-29 cascade ---------------------------------------------------------------


def test_delete_client_and_derived_removes_its_gate_results(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(ReportRun, run.id) is None
    assert session.get(StoredGateResult, stored.id) is None


def test_delete_client_and_derived_does_not_persist_gate_result_deletion_without_a_commit(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(StoredGateResult, stored.id) is not None


def test_the_cascade_constant_includes_gate_result() -> None:
    """Story 5.6: ``gate_result`` must join ``_CLIENT_CASCADE_TABLES`` -- a
    regression on top of the general invariant test in
    ``tests/test_client_store.py``, naming the table this story added
    explicitly."""
    assert "gate_result" in client_module._CLIENT_CASCADE_TABLES


def test_a_client_with_a_pass_and_an_earlier_fail_loses_both_gate_result_rows(
    session: Session,
) -> None:
    """I/O & Edge-Case Matrix row 4: a Client with Gate history spanning a
    pass and an earlier fail loses every ``gate_result`` row when deleted,
    before the ``report_run`` row itself is deleted."""
    client = _create_client(session)
    run = _create_run(session, client)
    failing = store_gate_result(
        session,
        run=run,
        passed=False,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(_a_violation(),),
    )
    passing = store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=1,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(StoredGateResult, failing.id) is None
    assert session.get(StoredGateResult, passing.id) is None


# --- AC2: pass rate and regeneration series are directly queryable ------------


def test_first_generation_pass_rate_and_regeneration_series_are_directly_queryable(
    session: Session,
) -> None:
    """AC2: given stored ``gate_result`` rows, first-generation pass rate
    (``regeneration_count == 0``) and regeneration count as its own series
    are both computable by a direct query against the table -- no new
    production query function required (this story's Boundaries)."""
    client = _create_client(session)

    # Run A: first-generation pass (regeneration_count == 0, passed).
    run_a = _create_run(session, client, month="2026-01")
    store_gate_result(
        session,
        run=run_a,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )

    # Run B: first attempt fails, second (regenerated) attempt passes.
    run_b = _create_run(session, client, month="2026-02")
    store_gate_result(
        session,
        run=run_b,
        passed=False,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(_a_violation(),),
    )
    store_gate_result(
        session,
        run=run_b,
        passed=True,
        regeneration_count=1,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )

    # Run C: first-generation fail, never recovers (bound exhausted).
    run_c = _create_run(session, client, month="2026-03")
    store_gate_result(
        session,
        run=run_c,
        passed=False,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(_a_violation(),),
    )
    session.commit()

    # First-generation pass rate: among regeneration_count == 0 rows, the
    # fraction that passed. Two first-generation checks (run_a, run_c's
    # first attempt), one of which passed -- run_b's own first attempt at
    # regeneration_count == 0 failed, not passed.
    first_generation_rows = session.exec(
        select(StoredGateResult).where(StoredGateResult.regeneration_count == 0)
    ).all()
    assert len(first_generation_rows) == 3
    first_generation_passes = sum(1 for row in first_generation_rows if row.passed)
    assert first_generation_passes == 1
    first_generation_pass_rate = first_generation_passes / len(first_generation_rows)
    assert first_generation_pass_rate == pytest.approx(1 / 3)

    # Regeneration count as its own series: every regeneration_count value
    # recorded, in the order checks occurred, directly readable off the
    # stored rows without any new query helper.
    regeneration_series = session.exec(
        select(StoredGateResult.regeneration_count).order_by(StoredGateResult.created_at)
    ).all()
    assert regeneration_series == [0, 0, 1, 0]

    # A plain aggregate query over the same table also answers "average
    # regenerations per run" with no new production code.
    average_regenerations = session.exec(
        select(func.avg(StoredGateResult.regeneration_count))
    ).one()
    assert average_regenerations == pytest.approx(sum(regeneration_series) / 4)


# --- Story 5.7: a Report closed via accepted violations and SM-5/SM-7 ----------


def test_a_report_closed_via_accepted_violations_is_excluded_from_sm5_and_eligible_for_sm7(
    session: Session,
) -> None:
    """Epic-5 context: "A Report closed via accepted violations (Story 5.7)
    is excluded from SM-5's first-generation pass rate (same treatment as
    every other post-first-attempt outcome) but is eligible for SM-7's
    hand-sample like any other passed Report."

    Accept-closure (``shell/http/routes/report_runs.py``'s accept route)
    never writes a new ``StoredGateResult`` row -- the run's original
    ``regeneration_count == 0`` failing row stays ``passed=False`` exactly
    as it was when the Gate itself rejected the draft, so SM-5's own
    ``regeneration_count == 0`` pass-rate query (proven directly above)
    needs no special-casing to keep counting it as a non-pass, the same
    treatment a run resolved by a genuine regeneration already gets. The
    closing ``Report`` row it *does* write is a real, ordinary ``report``
    row -- indistinguishable, to a query that only selects from ``report``,
    from any other passed Report -- so SM-7's hand-sample query needs no
    special-casing either."""
    client = _create_client(session)
    run = _create_run(session, client)
    violation = _a_violation()

    first_generation_failure = store_gate_result(
        session,
        run=run,
        passed=False,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(violation,),
    )
    session.commit()

    # Mirrors the accept route's own closing write
    # (`shell/http/routes/report_runs.py`): a `Report` row recording the
    # accepted count and the closing (failing) `StoredGateResult` it was
    # reviewed against -- no new Gate check, no new `gate_result` row.
    store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        accepted_violation_count=1,
        closing_gate_result_id=first_generation_failure.id,
    )
    session.commit()

    # SM-5: the first-generation pass-rate query (proven directly by
    # `test_first_generation_pass_rate_and_regeneration_series_are_directly_
    # queryable` above) still finds this run's only `regeneration_count ==
    # 0` row `passed=False` -- it is correctly excluded from the numerator,
    # with no accept-closure-specific logic required.
    first_generation_rows = session.exec(
        select(StoredGateResult).where(StoredGateResult.regeneration_count == 0)
    ).all()
    assert len(first_generation_rows) == 1
    assert first_generation_rows[0].passed is False

    # SM-7: a plain "every Report" query -- exactly what a monthly hand
    # -sample would run -- finds this run's closing Report row, indistinguishable
    # in kind from a clean pass except for its own accepted_violation_count.
    sampled_reports = session.exec(
        select(Report).where(Report.report_run_id == run.id)
    ).all()
    assert len(sampled_reports) == 1
    assert sampled_reports[0].accepted_violation_count == 1
    assert sampled_reports[0].closing_gate_result_id == first_generation_failure.id


# --- Design Notes: AC3 from epics.md needs no new production code -------------


def test_a_passed_reports_stored_draft_citations_are_checkable_against_its_stored_payload(
    session: Session,
) -> None:
    """AC3 (``epics.md``, this story's own Design Notes): a monthly hand
    sample of passed Reports must be checkable against their Payloads --
    the only measure of the Gate's false-negative rate. This needs no new
    production code: ``ReportDraft``/``ReportPayload`` rows are already
    retained permanently (deleted only by the Client cascade, since Story
    4.6) with citation structure intact (Story 3.8/4.6). Proven here as one
    coherent invariant -- persist a real, ``freeze_payload``-shaped Payload
    and a Draft citing one of its real entry ids, reload both by
    ``report_run_id`` after commit, and confirm ``core/gate/run.py``'s own
    ``_index_entries()`` (already used by the live Gate, no new query
    function) finds that citation's entry inside the reloaded Payload --
    exactly what a hand sample would do.
    """
    client = _create_client(session)
    run = _create_run(session, client)

    aspect = TransitAspectEvent(
        transiting_body="mars",
        natal_point="venus",
        aspect="trine",
        perfected_at=datetime(2026, 1, 5, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    populated_section = SectionPayload(
        profile=None,
        aspects=(aspect,),
        stations=(),
        standing_retrogrades=(),
        ingresses=(),
        lunations=(),
    )
    empty_section = SectionPayload(
        profile=None, aspects=(), stations=(), standing_retrogrades=(), ingresses=(), lunations=()
    )
    payload = Payload(
        energia_generale=populated_section,
        amore=empty_section,
        lavoro=empty_section,
        denaro=empty_section,
        benessere=empty_section,
        consiglio_finale=empty_section,
    )
    frozen = freeze_payload(
        payload,
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
        config=_COMPUTATION_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    real_id = frozen["sections"]["energia_generale"]["aspects"][0]["id"]

    store_report_payload(session, run=run, frozen=frozen)
    draft = GeneratedDraft(
        energia_generale=(
            Sentence(text="Marte in trigono a Venere.", entry_ids=(real_id,)),
        ),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(),
    )
    store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=frozen["sections_config_version"],
        draft=draft,
    )
    store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=0,
        vocabulary_version=1,
        vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        violations=(),
    )
    session.commit()

    # Reload -- both rows survived the commit unchanged and are still
    # joinable by report_run_id, exactly as a monthly hand-sample query
    # would read them back.
    reloaded_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).one()
    reloaded_draft = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).one()

    cited_entry_ids = {
        entry_id
        for sentence in reloaded_draft.draft["energia_generale"]
        for entry_id in sentence["entry_ids"]
    }
    assert cited_entry_ids == {real_id}

    entry_index = _index_entries(reloaded_payload.payload)
    assert real_id in entry_index
    assert entry_index[real_id]["kind"] == "aspect"
