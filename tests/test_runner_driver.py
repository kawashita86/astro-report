"""``shell/runner/driver.py::drive()`` -- Story 3.5's own I/O & Edge-Case
Matrix rows for advancing a ``ReportRun``, extended by Story 3.8's own row
for ``payload_ready``, Story 4.6's own row for ``draft_ready``, and
``_deserialize_transit_events``'s round trip.

An in-memory SQLite engine stands in for Postgres, mirroring
``tests/test_client_store.py``; the Natal Chart, ``ComputationConfig``,
``SectionsConfig``, ``EphemerisIdentity`` and ``GateVocabulary`` are all real
(the same known-good Fort Worth fixture ``tests/test_client_store.py`` uses,
and the same shipped vocabulary ``tests/test_gate_run.py`` uses), since four
of the five registered stages (``natal_ready``, ``transits_ready``,
``payload_ready``, ``gate_passed``) call real ``core/`` code -- only the
*failure* scenarios below inject a fake stage function, mirroring the
story's own Design Notes ("no live external call demonstrates the backoff").
``draft_ready`` is the one stage with a genuine external call (the Generator
port), so every test here drives it through ``_FakeGenerator`` rather than a
real Gemini call -- ``tests/test_report_draft_store.py`` covers the
persisted row's own shape, and the Gemini adapter has its own test module.

Five real stages are now registered (Story 5.3 added ``gate_passed``), so a
fresh, fully-successful ``drive()`` call -- with the clean, non-Claim-bearing
draft ``_FakeGenerator`` returns by default -- advances all the way to
``gate_passed``, persisting a ``Report`` row along the way; the first name in
``_STAGE_SEQUENCE`` with no registered function is now ``exported``.
``_create_client_and_chart`` seeds a Style Guide version alongside the
Client/Natal Chart so every full-drive test below reaches ``draft_ready``
without each test seeding one itself. ``tests/test_gate_run.py`` covers
``run_gate()``'s own checking logic; only the gate-pass/gate-fail stage
tests below need a fake, ungrounded draft to demonstrate a failure.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine, select

import shell.runner.driver as driver_module
from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.errors import GateFailedError
from core.types.generation import GeneratedDraft, Sentence
from core.types.memory import ReportTheme, ThemeAspect, ThemeLunation
from core.types.place import ResolvedPlace
from core.types.transits import Ingress, Lunation, StandingRetrograde, Station, TransitAspectEvent
from shell.adapters.postgres.client import create_client_with_chart, deserialize_natal_chart
from shell.adapters.postgres.gate_result import StoredGateResult
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_draft import _json_safe as _draft_json_safe
from shell.adapters.postgres.report_payload import ReportPayload
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.report_theme import StoredReportTheme
from shell.adapters.postgres.report_theme import _json_safe as _theme_json_safe
from shell.adapters.postgres.style_guide import create_style_guide_version
from shell.computation import load_computation_config
from shell.gate import DEFAULT_VOCABULARY_PATH, load_gate_vocabulary
from shell.ports.generator import Generator, StyleGuideVersion
from shell.runner.driver import _STAGE_FUNCTIONS, _deserialize_transit_events, advance
from shell.sections import load_sections_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()
_VOCABULARY = load_gate_vocabulary(DEFAULT_VOCABULARY_PATH)

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_client_store.py uses.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)

#: The Style Guide content ``_create_client_and_chart`` seeds (version 1) for
#: every test in this module -- so a full, fresh ``_drive()`` call reaches
#: ``draft_ready`` without each test seeding its own.
_STYLE_GUIDE_CONTENT = "Scrivi con calore, citando sempre il Payload."

#: A fixed test UUID standing in for a real ``StoredNatalChart.id`` (Story
#: 6.4) -- these tests exercise ``drive()``'s own bookkeeping of
#: ``natal_chart_id``, not chart-store lookup, so any stable UUID does.
_NATAL_CHART_ID: UUID = uuid4()


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as session:
        yield session


def _a_natal_chart():
    return compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG)


def _create_client_and_chart(session: Session):
    natal_chart = _a_natal_chart()
    client = create_client_with_chart(
        session,
        name="Ada Lovelace",
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=natal_chart,
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    # Seeded alongside the Client/Natal Chart (Story 4.6) so `draft_ready`
    # -- now a registered stage -- has a Style Guide to read, and every
    # full-drive test below reaches it without seeding one itself.
    create_style_guide_version(session, _STYLE_GUIDE_CONTENT)
    session.commit()
    return client, natal_chart


def _a_generated_draft() -> GeneratedDraft:
    """A minimal, valid ``GeneratedDraft`` (Story 4.5) -- ``_run_draft_ready``
    persists whatever the ``Generator`` returns verbatim, so its own content
    is arbitrary here; only ``_FakeGenerator``'s recorded call arguments and
    ``ReportDraft.draft``'s round trip matter to these tests."""
    return GeneratedDraft(
        energia_generale=(Sentence(text="Un mese di energia stabile.", entry_ids=("abc123",)),),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(),
    )


class _FakeGenerator:
    """A ``Generator`` (``shell/ports/generator.py``) test double: records
    every call it receives (``payload``, ``style_guide``, ``theme_previous``,
    ``theme_current``) and returns a fixed ``GeneratedDraft`` -- proves
    ``_run_draft_ready``'s own orchestration without a real Gemini call,
    mirroring this story's own Design Notes ("no live external call
    demonstrates the backoff")."""

    def __init__(self, draft: GeneratedDraft | None = None) -> None:
        self._draft = draft if draft is not None else _a_generated_draft()
        self.calls: list[tuple[dict, StyleGuideVersion, object, object]] = []

    def generate(self, payload, style_guide, theme_previous, theme_current):
        self.calls.append((payload, style_guide, theme_previous, theme_current))
        return self._draft


#: A generous ceiling on how many ``advance()`` calls ``_drive`` will chain
#: before giving up: the pipeline is 5 registered stages plus, in the worst
#: regeneration case, ``_MAX_REGENERATIONS + 1`` rewind/re-draft cycles of
#: two calls each -- well under 30. Hitting it means ``advance()`` is not
#: making progress the way the test expects, so it is a test failure, not a
#: silent early return.
_DRAIN_CAP = 60


def _advance(
    session: Session,
    run: ReportRun,
    natal_chart,
    generator: Generator | None = None,
    natal_chart_id: UUID = _NATAL_CHART_ID,
):
    """One ``advance()`` call -- at most one stage transition (AD-20, Story
    3.10). Tests asserting exactly-one-transition semantics use this
    directly; ``_drive`` below chains it to a fixed point."""
    return advance(
        session,
        run,
        natal_chart=natal_chart,
        natal_chart_id=natal_chart_id,
        config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
        sections_config=_SECTIONS_CONFIG,
        generator=generator if generator is not None else _FakeGenerator(),
        vocabulary=_VOCABULARY,
    )


def _drive(
    session: Session,
    run: ReportRun,
    natal_chart,
    generator: Generator | None = None,
    natal_chart_id: UUID = _NATAL_CHART_ID,
):
    """Drain ``advance()`` to a fixed point -- the end-to-end "run this to
    completion" harness the full-pipeline tests here (and
    ``tests/test_restore.py`` / ``tests/test_storage_growth_record.py`` /
    ``tests/test_latency_record.py``) still rely on. Under AD-20 (Story 3.10)
    ``advance()`` only moves one stage per call, so this loops it until
    ``run.stage`` stops changing or the run is marked terminally failed."""
    if generator is None:
        generator = _FakeGenerator()
    for _ in range(_DRAIN_CAP):
        stage_before = run.stage
        advance(
            session,
            run,
            natal_chart=natal_chart,
            natal_chart_id=natal_chart_id,
            config=_COMPUTATION_CONFIG,
            ephemeris_identity=_EPHEMERIS_IDENTITY,
            sections_config=_SECTIONS_CONFIG,
            generator=generator,
            vocabulary=_VOCABULARY,
        )
        if run.failed_at is not None:
            return run
        if run.stage == stage_before:
            return run
    raise AssertionError("_drive: advance() drain exceeded its iteration cap")


# --- Fresh run, all five registered stages succeed -----------------------------


def test_fresh_run_advances_through_all_five_registered_stages(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    assert result.stage == "gate_passed"
    assert result.month_start_utc == datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
    assert result.month_end_utc == datetime(2026, 2, 1, 6, 0, 0, tzinfo=UTC)
    assert isinstance(result.transit_events, list)
    assert result.transit_events, "fixture produced no transit events -- test is vacuous"
    assert {event["kind"] for event in result.transit_events} <= {
        "aspect",
        "station",
        "standing_retrograde",
        "ingress",
        "lunation",
    }


def test_lunation_events_keep_their_own_new_or_full_kind_distinct_from_the_wrapper_tag(
    session: Session,
) -> None:
    """Lunation (core/types/transits.py) carries its own `kind` field
    ("new_moon"/"full_moon") -- a real name collision with `_serialize_event`'s
    outer "kind" tag ("lunation"), not the same value twice. Both must survive
    the collision distinctly."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    lunations = [event for event in result.transit_events if event["kind"] == "lunation"]
    assert lunations, "fixture produced no lunations -- test is vacuous"
    for lunation in lunations:
        assert lunation["kind"] == "lunation"
        assert lunation["lunation_kind"] in {"new_moon", "full_moon"}


def test_a_completed_run_is_persisted_to_the_database(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    _drive(session, run, natal_chart)

    stored = session.get(ReportRun, run.id)
    assert stored is not None
    assert stored.stage == "gate_passed"
    assert stored.transit_events is not None


# --- Story 6.4's own row: natal_chart_id set once at natal_ready ---------------


def test_natal_chart_id_is_set_the_first_time_natal_ready_succeeds(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart, natal_chart_id=_NATAL_CHART_ID)

    assert result.stage == "gate_passed"
    assert result.natal_chart_id == _NATAL_CHART_ID


def test_natal_chart_id_is_unaffected_by_a_later_regeneration_rewind_to_payload_ready(
    session: Session,
) -> None:
    """natal_chart_id is recorded once, at natal_ready, and never touched
    again -- including by a Gate-failure regeneration rewind to
    payload_ready (Story 5.4), which never re-runs natal_ready."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _FakeGenerator(_a_violating_generated_draft())
    # One poll per stage up to draft_ready (natal, transits, payload, draft).
    for _ in range(4):
        _advance(session, run, natal_chart, generator=generator, natal_chart_id=_NATAL_CHART_ID)
    assert run.stage == "draft_ready"

    # The poll that runs gate_passed fails the Gate and rewinds to
    # payload_ready (Story 5.4) -- natal_ready is never re-run.
    result = _advance(
        session, run, natal_chart, generator=generator, natal_chart_id=_NATAL_CHART_ID
    )
    assert result.stage == "payload_ready", "fixture did not regenerate -- test is vacuous"
    assert result.natal_chart_id == _NATAL_CHART_ID

    # Regenerate (a poll re-runs draft_ready) then fail the Gate again on the
    # poll after -- passing a *different* natal_chart_id to each call.
    # natal_chart_id must stay exactly what natal_ready first set it to.
    other_chart_id = uuid4()
    _advance(session, run, natal_chart, generator=generator, natal_chart_id=other_chart_id)
    assert run.stage == "draft_ready"
    result = _advance(session, run, natal_chart, generator=generator, natal_chart_id=other_chart_id)

    assert result.natal_chart_id == _NATAL_CHART_ID, (
        "natal_chart_id must not be overwritten by a later poll"
    )


# --- Story 3.8's own row: payload_ready advances and persists a ReportPayload --


def test_payload_ready_advances_and_persists_a_report_payload_row(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    # Stop at transits_ready first -- the acceptance criterion's own
    # premise ("a ReportRun at transits_ready, when drive() is called
    # again").
    monkeypatch = pytest.MonkeyPatch()
    try:

        def _always_fail(*args, **kwargs):
            raise RuntimeError("simulated failure")

        monkeypatch.setitem(_STAGE_FUNCTIONS, "payload_ready", _always_fail)
        _drive(session, run, natal_chart)
        assert run.stage == "transits_ready", "fixture did not stop at transits_ready"
    finally:
        monkeypatch.undo()

    result = _drive(session, run, natal_chart)

    assert result.stage == "gate_passed"
    stored_payloads = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).all()
    assert len(stored_payloads) == 1
    stored_payload = stored_payloads[0]
    assert stored_payload.client_id == client.id
    assert stored_payload.payload["schema_version"] == stored_payload.schema_version
    assert set(stored_payload.payload["sections"]) == {
        "energia_generale",
        "amore",
        "lavoro",
        "denaro",
        "benessere",
        "consiglio_finale",
    }


# --- Story 4.3's own row: payload_ready also derives and persists a ReportTheme -


def test_payload_ready_also_derives_and_persists_a_report_theme_row(session: Session) -> None:
    """Acceptance Criteria: exactly one ``StoredReportTheme`` row exists for
    ``run.id`` once ``_run_payload_ready`` completes, derived purely from the
    just-assembled ``Payload`` -- no new AD-10 stage, reusing
    ``payload``/``config`` already in scope after ``store_report_payload()``."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    assert result.stage == "gate_passed"
    stored_themes = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.report_run_id == run.id)
    ).all()
    assert len(stored_themes) == 1
    stored_theme = stored_themes[0]
    assert stored_theme.client_id == client.id
    assert set(stored_theme.theme) == {"dominant_aspects", "lunations", "standing_retrogrades"}


# --- Re-drive after natal_ready alone -------------------------------------------


def test_re_drive_after_natal_ready_alone_runs_transits_ready_next_without_recomputing_it(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    # Stop right after natal_ready by making transits_ready fail every
    # attempt for this first drive() call only.
    def _always_fail(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _always_fail)
    _drive(session, run, natal_chart)
    assert run.stage == "natal_ready", "fixture did not stop at natal_ready -- test is vacuous"
    recorded_start, recorded_end = run.month_start_utc, run.month_end_utc

    monkeypatch.undo()

    # natal_ready must not be recomputed: prove it by making the function it
    # calls raise if it is ever invoked again.
    def _raise_if_called(*args, **kwargs):
        raise AssertionError("client_month_interval_utc must not be called again")

    monkeypatch.setattr(driver_module, "client_month_interval_utc", _raise_if_called)

    result = _drive(session, run, natal_chart)

    assert result.stage == "gate_passed"
    assert result.month_start_utc == recorded_start
    assert result.month_end_utc == recorded_end
    assert result.transit_events is not None


# --- Re-drive after full completion --------------------------------------------------


def test_re_drive_after_full_completion_is_a_noop(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    _drive(session, run, natal_chart)
    assert run.stage == "gate_passed", "fixture did not complete -- test is vacuous"
    events_before = run.transit_events
    updated_at_before = run.updated_at

    def _raise_if_called(*args, **kwargs):
        raise AssertionError("a completed stage must not be called again")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "natal_ready", _raise_if_called)
    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _raise_if_called)
    monkeypatch.setitem(_STAGE_FUNCTIONS, "payload_ready", _raise_if_called)
    monkeypatch.setitem(_STAGE_FUNCTIONS, "draft_ready", _raise_if_called)
    monkeypatch.setitem(_STAGE_FUNCTIONS, "gate_passed", _raise_if_called)

    result = _drive(session, run, natal_chart)

    assert result is run
    assert result.stage == "gate_passed"
    assert result.transit_events == events_before
    assert result.updated_at == updated_at_before

    # Re-driving must not have persisted a second ReportPayload row either.
    stored_payloads = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).all()
    assert len(stored_payloads) == 1

    # Nor a second ReportTheme row (Story 4.3).
    stored_themes = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.report_run_id == run.id)
    ).all()
    assert len(stored_themes) == 1

    # Nor a second ReportDraft row (Story 4.6).
    stored_drafts = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).all()
    assert len(stored_drafts) == 1

    # Nor a second Report row (Story 5.3).
    stored_reports = session.exec(select(Report).where(Report.report_run_id == run.id)).all()
    assert len(stored_reports) == 1


# --- A transiently failing stage still advances normally via with_backoff -----------


def test_a_stage_that_fails_once_then_succeeds_still_advances_run_stage_within_one_drive_call(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``tests/test_runner_backoff.py`` proves ``with_backoff`` itself
    retries a fail-once-then-succeed function in isolation. This proves the
    same thing through ``drive()``: a registered stage function that raises
    once and then succeeds must still be retried transparently and let
    ``run.stage`` advance normally within the same ``drive()`` call -- not
    leave the run stuck as if it had failed permanently."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    real_natal_ready = _STAGE_FUNCTIONS["natal_ready"]
    calls: list[int] = []

    def _fails_once_then_succeeds(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("simulated transient failure")
        return real_natal_ready(*args, **kwargs)

    monkeypatch.setitem(_STAGE_FUNCTIONS, "natal_ready", _fails_once_then_succeeds)

    result = _drive(session, run, natal_chart)

    assert len(calls) == 2, "the stage function must have been retried, not just called once"
    assert result.stage == "gate_passed"
    assert result.month_start_utc is not None
    assert result.transit_events is not None


# --- Stage raises past backoff's attempts --------------------------------------------


def test_a_persistently_failing_stage_leaves_the_run_unadvanced(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    calls: list[int] = []

    def _always_fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("simulated permanent failure")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "natal_ready", _always_fail)

    with caplog.at_level(logging.ERROR, logger=driver_module._logger.name):
        result = _advance(session, run, natal_chart)

    # No exception escaped advance() -- the call above completing at all is
    # part of what this test proves. One poll = one exhausted stage attempt-set.
    assert result.stage is None
    assert result.month_start_utc is None
    assert len(calls) == 3, "with_backoff's default max_attempts is 3"
    assert str(run.id) in caplog.text


def test_a_stage_failing_after_a_prior_success_leaves_stage_at_the_last_success(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    def _always_fail(*args, **kwargs):
        raise RuntimeError("simulated permanent failure")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _always_fail)

    _advance(session, run, natal_chart)  # natal_ready succeeds
    assert run.stage == "natal_ready"
    result = _advance(session, run, natal_chart)  # transits_ready exhausts every attempt

    assert result.stage == "natal_ready"
    assert result.month_start_utc is not None
    assert result.transit_events is None


# --- Process killed between stages -----------------------------------------------------


def test_process_killed_between_stages_resumes_reading_the_row_back(
    engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(engine) as first_session:
        client, natal_chart = _create_client_and_chart(first_session)
        run = ReportRun(client_id=client.id, month="2026-01")
        first_session.add(run)
        first_session.commit()

        def _always_fail(*args, **kwargs):
            raise RuntimeError("process killed here, simulated")

        monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _always_fail)
        _drive(first_session, run, natal_chart)
        assert run.stage == "natal_ready", "fixture did not stop at natal_ready -- test is vacuous"
        run_id = run.id
        recorded_start, recorded_end = run.month_start_utc, run.month_end_utc

    monkeypatch.undo()

    # A brand new session against the same engine -- simulates the process
    # restarting and reading the row back from Postgres, never from anything
    # held in memory.
    with Session(engine) as second_session:
        reloaded_run = second_session.get(ReportRun, run_id)
        assert reloaded_run is not None
        assert reloaded_run.stage == "natal_ready"
        assert reloaded_run.month_start_utc == recorded_start
        assert reloaded_run.month_end_utc == recorded_end

        result = _drive(second_session, reloaded_run, natal_chart)

        assert result.stage == "gate_passed"
        assert result.month_start_utc == recorded_start, "month bounds must not be recomputed"
        assert result.month_end_utc == recorded_end
        assert result.transit_events is not None


# --- Stops cleanly at the first unregistered stage ------------------------------------


def test_drive_stops_cleanly_once_it_reaches_an_unregistered_stage(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    # exported has no registered function -- drive() must stop there without
    # raising, having already completed gate_passed (Story 5.3).
    assert result.stage == "gate_passed"


# --- deserialize_natal_chart interop --------------------------------------------------


def test_drive_works_against_a_deserialized_natal_chart(session: Session) -> None:
    """The natal_chart drive() takes is the deserialized round trip
    (Boundaries & Constraints), not the freshly-computed value directly --
    proves the two interoperate."""
    from sqlmodel import select as _select

    from shell.adapters.postgres.client import StoredNatalChart

    client, _ = _create_client_and_chart(session)
    stored_chart = session.exec(
        _select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()
    natal_chart = deserialize_natal_chart(stored_chart)

    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    assert result.stage == "gate_passed"
    assert result.transit_events


# --- _deserialize_transit_events round trip --------------------------------------------


def test_deserialize_transit_events_round_trips_all_five_event_kinds() -> None:
    """The reverse of `_serialize_event`: every one of the five dataclasses
    it can tag must reconstruct equal to what was serialized."""
    t0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 10, 6, 30, 0, tzinfo=UTC)

    aspect = TransitAspectEvent(
        transiting_body="mars",
        natal_point="venus",
        aspect="trine",
        perfected_at=t0,
        never_perfected=False,
        orb_entry_at=t0,
        orb_exit_at=t1,
    )
    aspect_never_perfected = TransitAspectEvent(
        transiting_body="jupiter",
        natal_point="sun",
        aspect="square",
        perfected_at=None,
        never_perfected=True,
        orb_entry_at=t0,
        orb_exit_at=None,
    )
    station = Station(
        body="mercury", direction="retrograde", station_at=t0, longitude=Decimal("12.5")
    )
    standing_retrograde = StandingRetrograde(
        body="saturn", retrograde_start_utc=t0, retrograde_end_utc=t1
    )
    ingress = Ingress(body="venus", house_departed=4, house_entered=5, crossed_at=t0)
    lunation_new = Lunation(
        kind="new_moon", occurred_at=t0, longitude=Decimal("15.0"), natal_house=3
    )
    lunation_full = Lunation(
        kind="full_moon", occurred_at=t1, longitude=Decimal("195.0"), natal_house=9
    )

    originals = [
        ("aspect", aspect),
        ("aspect", aspect_never_perfected),
        ("station", station),
        ("standing_retrograde", standing_retrograde),
        ("ingress", ingress),
        ("lunation", lunation_new),
        ("lunation", lunation_full),
    ]
    serialized = [driver_module._serialize_event(kind, event) for kind, event in originals]

    deserialized_aspects, deserialized_stations, deserialized_ingresses, deserialized_lunations = (
        _deserialize_transit_events(serialized)
    )

    assert deserialized_aspects == (aspect, aspect_never_perfected)
    assert deserialized_stations == (station, standing_retrograde)
    assert deserialized_ingresses == (ingress,)
    assert deserialized_lunations == (lunation_new, lunation_full)


# --- _deserialize_theme round trip --------------------------------------------------


def test_deserialize_theme_round_trips_a_report_theme() -> None:
    """The reverse of ``StoredReportTheme.theme``'s own JSON encoding
    (``shell/adapters/postgres/report_theme.py``'s ``_json_safe``): every
    field of a ``ReportTheme`` -- including a ``None`` ``orb_exit_at`` -- must
    reconstruct equal to what was serialized, mirroring
    ``test_deserialize_transit_events_round_trips_all_five_event_kinds``'s
    own round-trip shape."""
    t0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 10, 6, 30, 0, tzinfo=UTC)

    theme = ReportTheme(
        dominant_aspects=(
            ThemeAspect(
                transiting_body="saturn",
                natal_point="sun",
                aspect="square",
                perfected_at=t0,
                never_perfected=False,
                orb_entry_at=t0,
                orb_exit_at=None,
            ),
        ),
        lunations=(ThemeLunation(kind="new_moon", natal_house=3),),
        standing_retrogrades=(
            StandingRetrograde(body="jupiter", retrograde_start_utc=t0, retrograde_end_utc=t1),
        ),
    )

    serialized = _theme_json_safe(theme)
    deserialized = driver_module._deserialize_theme(serialized)

    assert deserialized == theme


def test_deserialize_theme_round_trips_an_empty_theme() -> None:
    theme = ReportTheme(dominant_aspects=(), lunations=(), standing_retrogrades=())

    deserialized = driver_module._deserialize_theme(_theme_json_safe(theme))

    assert deserialized == theme


# --- Story 4.6's own row: draft_ready calls the Generator and persists a ReportDraft ---


def test_draft_ready_calls_the_generator_with_the_persisted_payload_style_guide_and_theme(
    session: Session,
) -> None:
    """Acceptance Criteria/Boundaries: ``_run_draft_ready`` reads
    ``payload``/``theme_current`` back from ``ReportPayload``/
    ``StoredReportTheme`` -- never recomputes them -- calls the Generator
    with the Style Guide currently in force, and passes
    ``theme_previous=None`` for a Client's first Report (Story 4.7: no prior
    ``ReportRun`` for this Client has reached ``payload_ready``)."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _FakeGenerator()
    result = _drive(session, run, natal_chart, generator=generator)

    assert result.stage == "gate_passed"
    assert len(generator.calls) == 1, "the Generator must be called exactly once"
    called_payload, called_style_guide, theme_previous, theme_current = generator.calls[0]

    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).one()
    assert called_payload == stored_payload.payload

    assert called_style_guide == StyleGuideVersion(version=1, content=_STYLE_GUIDE_CONTENT)
    assert theme_previous is None, "no prior ReportRun exists for this Client -- first Report"
    assert isinstance(theme_current, ReportTheme)


def test_draft_ready_passes_the_most_recent_prior_report_theme_for_a_returning_client(
    session: Session,
) -> None:
    """Story 4.7 Acceptance Criteria: given a Client with at least one prior
    month, ``theme_previous`` is that month's already-persisted
    ``ReportTheme``, deserialized via ``_deserialize_theme`` -- never
    ``None``, never recomputed."""
    client, natal_chart = _create_client_and_chart(session)
    first_run = ReportRun(client_id=client.id, month="2026-01")
    session.add(first_run)
    session.commit()
    _drive(session, first_run, natal_chart)
    assert first_run.stage == "gate_passed", "fixture did not complete -- test is vacuous"

    first_stored_theme = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.report_run_id == first_run.id)
    ).one()
    expected_theme_previous = driver_module._deserialize_theme(first_stored_theme.theme)

    second_run = ReportRun(client_id=client.id, month="2026-02")
    session.add(second_run)
    session.commit()
    generator = _FakeGenerator()
    result = _drive(session, second_run, natal_chart, generator=generator)

    assert result.stage == "gate_passed"
    assert len(generator.calls) == 1
    _, _, theme_previous, _ = generator.calls[0]
    assert theme_previous == expected_theme_previous


def test_draft_ready_still_finds_the_prior_theme_when_a_month_was_skipped(
    session: Session,
) -> None:
    """Story 4.7 I/O Matrix: the most recent prior ``ReportRun`` (``"2026-01"``)
    is still fetched as ``theme_previous`` for ``"2026-03"`` even though
    ``"2026-02"`` was skipped -- "most recent", not "calendar-adjacent"."""
    client, natal_chart = _create_client_and_chart(session)
    first_run = ReportRun(client_id=client.id, month="2026-01")
    session.add(first_run)
    session.commit()
    _drive(session, first_run, natal_chart)
    assert first_run.stage == "gate_passed", "fixture did not complete -- test is vacuous"

    first_stored_theme = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.report_run_id == first_run.id)
    ).one()
    expected_theme_previous = driver_module._deserialize_theme(first_stored_theme.theme)

    third_run = ReportRun(client_id=client.id, month="2026-03")
    session.add(third_run)
    session.commit()
    generator = _FakeGenerator()
    result = _drive(session, third_run, natal_chart, generator=generator)

    assert result.stage == "gate_passed"
    _, _, theme_previous, _ = generator.calls[0]
    assert theme_previous == expected_theme_previous


def test_draft_ready_persists_the_generated_draft_verbatim_with_its_versions(
    session: Session,
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    draft = GeneratedDraft(
        energia_generale=(Sentence(text="Un mese intenso.", entry_ids=("id-1", "id-2")),),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(Sentence(text="Respira.", entry_ids=()),),
    )
    generator = _FakeGenerator(draft)

    result = _drive(session, run, natal_chart, generator=generator)

    assert result.stage == "gate_passed"
    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).one()
    stored_drafts = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).all()
    assert len(stored_drafts) == 1
    stored_draft = stored_drafts[0]
    assert stored_draft.client_id == client.id
    assert stored_draft.style_guide_version == 1
    assert stored_draft.sections_config_version == stored_payload.sections_config_version
    # entry_ids intact: rendering to prose happens only in shell/http/, never
    # baked into what draft_ready persists (this story's Boundaries).
    assert stored_draft.draft["energia_generale"] == [
        {"text": "Un mese intenso.", "entry_ids": ["id-1", "id-2"]}
    ]
    assert stored_draft.draft["consiglio_finale"] == [{"text": "Respira.", "entry_ids": []}]
    assert stored_draft.draft["amore"] == []


# --- Story 5.3's own row: gate_passed checks the draft against the Payload -----------
# --- and persists a Report, only on a pass (I/O & Edge-Case Matrix rows 1-2) ---------


def _a_violating_generated_draft() -> GeneratedDraft:
    """A draft containing exactly one Claim (Story 5.1: ``"Marte"`` is a
    closed-vocabulary planet token) that cites nothing -- ``run_gate()``
    (Story 5.2) flags this as an ``"empty_citation"`` violation, for
    gate-fail tests below."""
    return GeneratedDraft(
        energia_generale=(Sentence(text="Marte è forte questo mese.", entry_ids=()),),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(),
    )


def test_gate_passed_advances_on_a_clean_draft_and_persists_a_report_row(
    session: Session,
) -> None:
    """Acceptance Criteria: given a run at ``draft_ready``, when it advances
    with a clean (non-Claim-bearing) draft, the run reaches ``gate_passed``
    and exactly one ``Report`` row is persisted, recording the Style Guide,
    Payload schema and Gate vocabulary versions that produced it."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    assert result.stage == "gate_passed"
    stored_reports = session.exec(select(Report).where(Report.report_run_id == run.id)).all()
    assert len(stored_reports) == 1
    stored_report = stored_reports[0]
    assert stored_report.client_id == client.id

    stored_draft = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).one()
    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).one()
    assert stored_report.style_guide_version == stored_draft.style_guide_version
    assert stored_report.payload_schema_version == stored_payload.schema_version
    assert stored_report.gate_vocabulary_version == _VOCABULARY.version
    assert stored_report.gate_vocabulary_content_hash == _VOCABULARY.content_hash

    # Story 5.6: exactly one immutable gate_result row also records the pass.
    stored_gate_results = session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all()
    assert len(stored_gate_results) == 1
    stored_gate_result = stored_gate_results[0]
    assert stored_gate_result.client_id == client.id
    assert stored_gate_result.passed is True
    assert stored_gate_result.regeneration_count == 0
    assert stored_gate_result.vocabulary_version == _VOCABULARY.version
    assert stored_gate_result.vocabulary_content_hash == _VOCABULARY.content_hash
    assert stored_gate_result.violations == []


def test_gate_passed_rewinds_to_payload_ready_and_regenerates_on_the_next_poll(
    session: Session,
) -> None:
    """I/O & Edge-Case Matrix row 1, "First Gate failure": given a failing
    ``GateResult``, ``run.stage`` rewinds to ``payload_ready`` (not
    ``draft_ready`` -- Story 5.4 replaces the old generic stage-failure
    bookkeeping for this specific error), ``regeneration_count`` becomes 1,
    ``stage_failure_count`` is left untouched, and no ``Report`` row is
    written. Two more polls (re-run ``draft_ready``, then fail
    ``gate_passed`` again) regenerate: a new ``ReportDraft`` at ``attempt=1``
    is persisted from the same Payload, and ``regeneration_count`` reaches
    2 -- one transition per poll (AD-20, Story 3.10)."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _FakeGenerator(_a_violating_generated_draft())
    # natal, transits, payload, draft -- one poll each.
    for _ in range(4):
        _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"

    # This poll runs gate_passed, which fails and rewinds to payload_ready.
    result = _advance(session, run, natal_chart, generator=generator)

    assert result.stage == "payload_ready"
    assert result.regeneration_count == 1
    assert result.stage_failure_count == 0
    assert result.failed_at is None
    # The violating draft was still persisted verbatim by draft_ready --
    # only gate_passed's own advance (and its Report row) failed.
    stored_drafts = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).all()
    assert len(stored_drafts) == 1
    assert stored_drafts[0].attempt == 0
    stored_reports = session.exec(select(Report).where(Report.report_run_id == run.id)).all()
    assert stored_reports == []

    # Story 5.6: exactly one gate_result row records the failing check, at
    # its pre-increment regeneration_count (0, not 1 -- run.regeneration_count
    # is only incremented after this write).
    stored_gate_results = session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all()
    assert len(stored_gate_results) == 1
    assert stored_gate_results[0].passed is False
    assert stored_gate_results[0].regeneration_count == 0
    assert stored_gate_results[0].vocabulary_version == _VOCABULARY.version
    assert stored_gate_results[0].vocabulary_content_hash == _VOCABULARY.content_hash
    assert stored_gate_results[0].violations

    # Poll: re-run draft_ready (attempt 1). Poll again: gate_passed fails once
    # more, rewinding to payload_ready with regeneration_count now 2.
    _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"
    result = _advance(session, run, natal_chart, generator=generator)

    assert result.stage == "payload_ready"
    assert result.regeneration_count == 2
    stored_drafts = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).all()
    assert {stored.attempt for stored in stored_drafts} == {0, 1}
    stored_reports = session.exec(select(Report).where(Report.report_run_id == run.id)).all()
    assert stored_reports == []

    # A second failing check adds a second gate_result row, at
    # regeneration_count 1 -- both failed, none passed.
    stored_gate_results = session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all()
    assert len(stored_gate_results) == 2
    assert {row.regeneration_count for row in stored_gate_results} == {0, 1}
    assert all(row.passed is False for row in stored_gate_results)


def test_run_gate_passed_raises_gate_failed_error_on_a_failing_gate_result(
    session: Session,
) -> None:
    """Unit-level: ``_run_gate_passed`` itself raises ``GateFailedError`` on
    a failing ``GateResult`` -- proven directly, not only through
    ``drive()``'s regeneration handling. The fixture calls every earlier
    stage function directly, in sequence, real ``core/`` code and all --
    ending with ``_run_draft_ready`` against a violating draft -- to reach
    exactly the state ``_run_gate_passed`` needs (a persisted ``ReportDraft``
    and ``ReportPayload`` for ``run``, at ``draft_ready``) without going
    through ``drive()`` or touching ``_STAGE_FUNCTIONS`` at all."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _FakeGenerator(_a_violating_generated_draft())

    for stage_fn in (
        driver_module._run_natal_ready,
        driver_module._run_transits_ready,
        driver_module._run_payload_ready,
        driver_module._run_draft_ready,
    ):
        stage_fn(
            session,
            run,
            natal_chart,
            _COMPUTATION_CONFIG,
            _EPHEMERIS_IDENTITY,
            _SECTIONS_CONFIG,
            generator,
            _VOCABULARY,
        )
        session.commit()
    run.stage = "draft_ready"
    session.add(run)
    session.commit()
    assert run.stage == "draft_ready", "fixture did not stop at draft_ready -- test is vacuous"

    with pytest.raises(GateFailedError) as caught:
        driver_module._run_gate_passed(
            session,
            run,
            natal_chart,
            _COMPUTATION_CONFIG,
            _EPHEMERIS_IDENTITY,
            _SECTIONS_CONFIG,
            generator,
            _VOCABULARY,
        )

    assert caught.value.violations
    assert caught.value.violations[0].kind == "empty_citation"


def test_a_failing_gate_passed_stage_runs_exactly_once_per_poll(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Epic-6-retro item 43: ``gate_passed`` is capped at ``max_attempts=1``,
    so a failing Gate does not retry the stage function inside one
    ``advance()`` call -- it runs once, then ``advance()``'s
    ``GateFailedError`` regeneration handling takes over on that same poll."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    real_gate_passed = _STAGE_FUNCTIONS["gate_passed"]
    calls = 0

    def _counting_gate_passed(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_gate_passed(*args, **kwargs)

    monkeypatch.setitem(_STAGE_FUNCTIONS, "gate_passed", _counting_gate_passed)

    generator = _FakeGenerator(_a_violating_generated_draft())
    # natal, transits, payload, draft -- one poll each.
    for _ in range(4):
        _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"
    assert calls == 0, "gate_passed must not run before the poll that lands on it"

    # The poll that runs gate_passed: it fails once, then regeneration
    # bookkeeping takes over -- no with_backoff retry of the stage function.
    result = _advance(session, run, natal_chart, generator=generator)

    assert calls == 1, "gate_passed must not be retried within a single poll"
    assert result.stage == "payload_ready"
    assert result.regeneration_count == 1


def test_gate_passed_regenerates_and_advances_once_a_later_attempt_passes(
    session: Session,
) -> None:
    """I/O & Edge-Case Matrix row 2, "Regeneration then pass": a Gate
    failure followed by a clean regenerated draft reaches ``gate_passed``
    with exactly one persisted ``Report``, ``regeneration_count`` reflects
    the one attempt used, and (matrix row 4, "Same Payload across
    attempts") both ``ReportDraft`` rows reference the same, unchanged
    ``ReportPayload`` row -- ``payload_ready`` is never re-run once
    ``run.stage`` rewinds to it (the module's own Design Notes)."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    class _ViolatesOnceThenCleanGenerator:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, payload, style_guide, theme_previous, theme_current):
            self.calls += 1
            return _a_violating_generated_draft() if self.calls == 1 else _a_generated_draft()

    generator = _ViolatesOnceThenCleanGenerator()

    # natal, transits, payload, draft (violating) -- one poll each.
    for _ in range(4):
        _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"

    # Poll: gate_passed fails on the violating draft, rewinds to payload_ready.
    first = _advance(session, run, natal_chart, generator=generator)
    assert first.stage == "payload_ready", "fixture did not fail once -- test is vacuous"
    assert first.regeneration_count == 1

    # Poll: re-run draft_ready (clean draft now). Poll again: gate_passed passes.
    _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"
    result = _advance(session, run, natal_chart, generator=generator)

    assert result.stage == "gate_passed"
    assert result.regeneration_count == 1

    stored_reports = session.exec(select(Report).where(Report.report_run_id == run.id)).all()
    assert len(stored_reports) == 1

    # Story 5.6: one failing gate_result row (attempt 0) and one passing
    # gate_result row (attempt 1) -- both recorded, not just the pass.
    stored_gate_results = session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all()
    assert len(stored_gate_results) == 2
    by_regeneration_count = {row.regeneration_count: row for row in stored_gate_results}
    assert by_regeneration_count[0].passed is False
    assert by_regeneration_count[1].passed is True

    stored_drafts = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).all()
    assert {stored.attempt for stored in stored_drafts} == {0, 1}

    stored_payloads = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).all()
    assert len(stored_payloads) == 1, "the same Payload row must be reused across attempts"


def test_gate_passed_exhausting_the_regeneration_bound_marks_the_run_terminally_failed(
    session: Session,
) -> None:
    """I/O & Edge-Case Matrix row 3, "Bound exhausted": the Generator always
    returns the same violating draft, so every regenerated attempt's
    ``gate_passed`` fails identically (``run_gate()`` is pure). Once
    ``run.regeneration_count`` exceeds ``_MAX_REGENERATIONS``, the run is
    marked terminally failed with ``run.stage`` left at ``draft_ready`` (not
    rewound) so the final, still-failing draft stays reachable rather than
    discarded."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _FakeGenerator(_a_violating_generated_draft())

    # natal, transits, payload, draft -- one poll each.
    for _ in range(4):
        _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"

    for expected_regeneration_count in range(1, driver_module._MAX_REGENERATIONS + 1):
        # Poll that runs gate_passed: fails, rewinds to payload_ready.
        result = _advance(session, run, natal_chart, generator=generator)
        assert result.stage == "payload_ready"
        assert result.regeneration_count == expected_regeneration_count
        assert result.failed_at is None
        # Poll that re-runs draft_ready for the next regeneration attempt.
        result = _advance(session, run, natal_chart, generator=generator)
        assert result.stage == "draft_ready"

    # Poll that runs gate_passed once more -- this failure exceeds the bound.
    result = _advance(session, run, natal_chart, generator=generator)

    assert result.stage == "draft_ready"
    assert result.regeneration_count == driver_module._MAX_REGENERATIONS + 1
    assert result.failed_at is not None
    assert result.failure_reason is not None
    assert "regeneration bound exhausted" in result.failure_reason

    stored_drafts = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run.id)
    ).all()
    assert {stored.attempt for stored in stored_drafts} == set(
        range(driver_module._MAX_REGENERATIONS + 1)
    )
    stored_reports = session.exec(select(Report).where(Report.report_run_id == run.id)).all()
    assert stored_reports == []

    # Story 5.6: every failing check along the way -- including the final,
    # bound-exhausting one -- got its own gate_result row before
    # run.failed_at was set. None passed.
    stored_gate_results = session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all()
    assert {row.regeneration_count for row in stored_gate_results} == set(
        range(driver_module._MAX_REGENERATIONS + 1)
    )
    assert all(row.passed is False for row in stored_gate_results)


# --- epic-5-retro-item-39: a partial flush inside gate_passed's two-write ------------
# --- pattern must not poison the session drive()'s own bookkeeping needs ------------


def test_gate_passed_pass_path_flush_failure_leaves_run_recoverable(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``_run_gate_passed``'s pass branch calls ``store_report`` then
    ``store_gate_result``, each its own flush, with no commit between (Story
    5.6). If ``store_gate_result``'s flush always fails, ``with_backoff``
    retries the whole stage function, and a prior attempt's already-flushed,
    uncommitted ``Report`` row would otherwise poison the session for every
    later statement -- including ``drive()``'s own bookkeeping commit in its
    generic ``except Exception`` block, which must not crash uncaught
    (epic-5-retro-item-39, re-prioritizing epic-4-retro-item-23)."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    def _always_fail(*args, **kwargs):
        raise RuntimeError("simulated gate_result flush failure")

    monkeypatch.setattr(driver_module, "store_gate_result", _always_fail)

    with caplog.at_level(logging.ERROR, logger=driver_module._logger.name):
        result = _drive(session, run, natal_chart)

    # No exception escaped drive() -- the call above completing at all is
    # part of what this test proves.
    assert result.stage == "draft_ready"
    assert result.stage_failure_count == 1
    assert result.failed_at is None

    # The pass branch's own store_report() attempts were all rolled back
    # along with the failing store_gate_result() attempts -- nothing
    # half-written survives.
    assert session.exec(select(Report).where(Report.report_run_id == run.id)).all() == []
    assert (
        session.exec(select(StoredGateResult).where(StoredGateResult.report_run_id == run.id))
        .all()
        == []
    )

    monkeypatch.undo()

    result = _drive(session, run, natal_chart)

    assert result.stage == "gate_passed"
    assert result.stage_failure_count == 0
    stored_reports = session.exec(select(Report).where(Report.report_run_id == run.id)).all()
    assert len(stored_reports) == 1
    stored_gate_results = session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all()
    assert len(stored_gate_results) == 1
    assert stored_gate_results[0].passed is True


def test_gate_failed_error_path_survives_a_gate_result_flush_failure(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``advance()``'s own ``except GateFailedError`` block calls
    ``store_gate_result`` unguarded, outside ``with_backoff`` by design
    (Story 5.6, to avoid a duplicate row on retry). If that flush fails, the
    regeneration bookkeeping that follows (``regeneration_count`` increment,
    ``run.stage`` rewind) must still happen and commit cleanly -- losing one
    audit row must never crash ``advance()`` itself or block the run from
    progressing (epic-5-retro-item-39, re-prioritizing epic-4-retro-item-23)."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    def _fail_at_the_database(*args, **kwargs):
        # A genuine DB-level failure, not a plain Python raise -- this is
        # what actually poisons the session's transaction (unlike a raise
        # that never touches the DB), so it also proves `run.id` stays
        # readable for the log line that follows, right after this
        # exception is caught.
        session.execute(text("SELECT * FROM this_table_does_not_exist"))

    generator = _FakeGenerator(_a_violating_generated_draft())

    # natal, transits, payload, draft -- one poll each.
    for _ in range(4):
        _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"

    monkeypatch.setattr(driver_module, "store_gate_result", _fail_at_the_database)

    with caplog.at_level(logging.ERROR, logger=driver_module._logger.name):
        result = _advance(session, run, natal_chart, generator=generator)

    # No exception escaped advance() despite the audit write failing on the
    # single with_backoff attempt of the pure, failing gate_passed check.
    assert result.stage == "payload_ready"
    assert result.regeneration_count == 1
    assert result.stage_failure_count == 0
    assert result.failed_at is None
    assert "failed to persist a failing gate_result" in caplog.text
    assert session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all() == []

    monkeypatch.undo()

    # Poll: re-run draft_ready (attempt 1). Poll: gate_passed fails again, and
    # now store_gate_result works -- one row lands, at regeneration_count 1.
    _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"
    result = _advance(session, run, natal_chart, generator=generator)

    assert result.stage == "payload_ready"
    assert result.regeneration_count == 2
    stored_gate_results = session.exec(
        select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
    ).all()
    assert len(stored_gate_results) == 1
    assert stored_gate_results[0].regeneration_count == 1


# --- retro-C items 23 / 26 / 44: savepoint-per-attempt + concurrent-drive() races ---


def _stray_report_payload(session: Session, *, client_id, report_run_id) -> ReportPayload:
    """A minimally-valid ``ReportPayload`` for ``report_run_id``, built
    straight against the model's columns -- stands in for the row a
    concurrent ``drive()`` would have committed at ``payload_ready``."""
    row = ReportPayload(
        client_id=client_id,
        report_run_id=report_run_id,
        schema_version=1,
        computation_config_version=1,
        computation_config_content_hash="a" * 64,
        sections_config_version=1,
        sections_config_content_hash="b" * 64,
        ephemeris_files=[{"name": "test.se1"}],
        payload={"schema_version": 1},
    )
    session.add(row)
    return row


def test_a_two_write_stage_whose_second_write_fails_transiently_still_advances(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retro-C item 23: ``_run_payload_ready`` flushes ``ReportPayload`` and
    then ``store_report_theme`` raises a real (non-``IntegrityError``) DB
    error once. Each ``with_backoff`` attempt now runs inside its own
    ``session.begin_nested()`` SAVEPOINT, so attempt 1's partial flush rolls
    back to the savepoint and attempt 2 runs on a clean session and
    completes -- ``run.stage`` advances within the one ``drive()`` call and
    ``stage_failure_count`` stays 0. A ``base_delay_seconds: 0.0`` override
    keeps the suite free of a real ``time.sleep``."""
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "payload_ready",
        {"base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    real_store_report_theme = driver_module.store_report_theme
    calls: list[int] = []

    def _fails_once_then_delegates(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError(
                "UPDATE report_theme", {}, Exception("simulated transient DB error")
            )
        return real_store_report_theme(*args, **kwargs)

    monkeypatch.setattr(driver_module, "store_report_theme", _fails_once_then_delegates)

    result = _drive(session, run, natal_chart)

    assert len(calls) == 2, "with_backoff must have retried the whole two-write stage"
    assert result.stage == "gate_passed"
    assert result.stage_failure_count == 0
    assert result.failed_at is None
    assert (
        len(session.exec(select(ReportPayload).where(ReportPayload.report_run_id == run.id)).all())
        == 1
    ), "attempt 1's partial ReportPayload flush must have rolled back to its savepoint"
    assert (
        len(
            session.exec(
                select(StoredReportTheme).where(StoredReportTheme.report_run_id == run.id)
            ).all()
        )
        == 1
    )


def test_a_pre_existing_report_payload_row_makes_payload_ready_a_completed_stage(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """retro-C items 26/44: a concurrent ``advance()`` already wrote this
    run's ``ReportPayload`` (``report_run_id`` unique) and advanced
    ``run.stage``. Our poll, still holding the older ``run.stage`` in memory,
    re-runs ``payload_ready``, hits the unique-constraint ``IntegrityError``
    on the single attempt, and -- because ``run.stage`` refreshed past
    ``payload_ready`` -- treats it as a completed stage: no ``with_backoff``
    retry, ``stage_failure_count``/``failed_at`` untouched, INFO (not
    ``exception``) logged. One ``advance()`` call asserts exactly this."""
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "payload_ready",
        {"base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    # The concurrent winner: a full, clean drain that commits the
    # ReportPayload row and leaves stage_failure_count at 0.
    _drive(session, run, natal_chart)
    assert run.stage == "gate_passed"

    # Our own poll still sees the pre-race stage in memory.
    run.stage = "transits_ready"

    entries: list[int] = []
    real_payload_ready = _STAGE_FUNCTIONS["payload_ready"]

    def _counting(*args, **kwargs):
        entries.append(1)
        return real_payload_ready(*args, **kwargs)

    monkeypatch.setitem(_STAGE_FUNCTIONS, "payload_ready", _counting)

    with caplog.at_level(logging.INFO, logger=driver_module._logger.name):
        result = _advance(session, run, natal_chart)

    assert entries == [1], "the concurrent conflict must not be retried"
    assert result.stage == "gate_passed"
    assert result.stage_failure_count == 0
    assert result.regeneration_count == 0
    assert result.failed_at is None
    assert (
        len(session.exec(select(ReportPayload).where(ReportPayload.report_run_id == run.id)).all())
        == 1
    )
    info_records = [
        record
        for record in caplog.records
        if record.levelno == logging.INFO
        and "already completed by a concurrent advance" in record.getMessage()
    ]
    assert len(info_records) == 1
    assert "gate_passed" in info_records[0].getMessage(), "the observed run.stage must be logged"
    assert all(record.levelno < logging.ERROR for record in caplog.records)


def test_a_pre_existing_report_draft_row_makes_draft_ready_a_completed_stage(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """retro-C items 26/44, ``draft_ready`` variant: a concurrent
    ``advance()`` already wrote ``ReportDraft (run, attempt=0)``
    (``ix_report_draft_report_run_id_attempt``). Our poll re-runs
    ``draft_ready`` at the same attempt, hits the ``IntegrityError``, and
    recognises the completed stage without a ``with_backoff`` retry -- and,
    critically, without a second paid ``generator.generate()`` call. One
    ``advance()`` call asserts exactly this.

    Story 5.8 amendment: ``_run_draft_ready`` now tags the persisted
    ``ReportDraft`` with ``next_report_draft_attempt(session, run.id)`` -- a
    fresh count of existing rows read from the database at call time -- not
    ``run.regeneration_count`` read from a possibly-stale in-memory ``run``.
    That means the *count itself* self-heals across the race this test
    exercises (our poll's own query would see the concurrent winner's
    already-committed row and correctly compute attempt=1, never colliding).
    The genuine race this test is about is two callers computing that count
    from the database at the same instant, before either has committed --
    simulated here by monkeypatching ``next_report_draft_attempt`` to always
    return ``0``, exactly the value both concurrent callers would compute if
    neither had committed yet, so this poll's own insert still collides with
    the winner's already-committed ``attempt=0`` row."""
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "draft_ready",
        {"max_attempts": 3, "base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    # The concurrent winner: a full, clean drain that commits
    # ReportDraft(attempt=0).
    _drive(session, run, natal_chart)
    assert run.stage == "gate_passed"

    # Our own poll still sees the pre-race stage in memory, so it re-enters
    # draft_ready -- and, simulating the race, still computes attempt 0 too
    # (see the docstring above).
    run.stage = "payload_ready"
    monkeypatch.setattr(driver_module, "next_report_draft_attempt", lambda session, run_id: 0)
    generator = _FakeGenerator()

    with caplog.at_level(logging.INFO, logger=driver_module._logger.name):
        result = _advance(session, run, natal_chart, generator=generator)

    assert len(generator.calls) == 1, "the stage calls the generator exactly once, before the flush"
    assert result.stage == "gate_passed"
    assert result.stage_failure_count == 0
    assert result.regeneration_count == 0
    assert result.failed_at is None
    assert (
        len(session.exec(select(ReportDraft).where(ReportDraft.report_run_id == run.id)).all()) == 1
    )
    info_records = [
        record
        for record in caplog.records
        if record.levelno == logging.INFO
        and "already completed by a concurrent advance" in record.getMessage()
    ]
    assert len(info_records) == 1
    assert all(record.levelno < logging.ERROR for record in caplog.records)


def test_an_integrity_error_without_a_stage_advance_is_recorded_as_a_stage_failure(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """retro-C: an ``IntegrityError`` at ``payload_ready`` whose
    ``run.stage`` did **not** move past the current stage after refresh is a
    genuine integrity bug, not a concurrent-stage advance. It falls through
    to the ordinary stage-failure path -- ``stage_failure_count += 1``,
    ``logger.error``, terminal at ``_MAX_STAGE_FAILURES`` -- but is
    still never retried by ``with_backoff``."""
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "payload_ready",
        {"base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    # Stop at transits_ready, then neutralise the fixture's own failure bump
    # so the assertion below targets only the IntegrityError path.
    with monkeypatch.context() as m:

        def _always_fail(*args, **kwargs):
            raise RuntimeError("simulated failure -- stop at transits_ready")

        m.setitem(_STAGE_FUNCTIONS, "payload_ready", _always_fail)
        _drive(session, run, natal_chart)
        assert run.stage == "transits_ready"
    run.stage_failure_count = 0
    session.add(run)
    session.commit()

    # A stray ReportPayload row exists, but no concurrent drive() advanced
    # run.stage -- so the refresh will still show transits_ready.
    _stray_report_payload(session, client_id=client.id, report_run_id=run.id)
    session.commit()

    entries: list[int] = []
    real_payload_ready = _STAGE_FUNCTIONS["payload_ready"]

    def _counting(*args, **kwargs):
        entries.append(1)
        return real_payload_ready(*args, **kwargs)

    monkeypatch.setitem(_STAGE_FUNCTIONS, "payload_ready", _counting)

    with caplog.at_level(logging.ERROR, logger=driver_module._logger.name):
        result = _drive(session, run, natal_chart)

    assert entries == [1], "a non-concurrent IntegrityError must not be retried either"
    assert result.stage == "transits_ready"
    assert result.stage_failure_count == 1
    assert result.regeneration_count == 0
    assert result.failed_at is None
    assert str(run.id) in caplog.text


def test_a_two_write_stage_whose_second_write_fails_on_every_attempt_stays_recoverable(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """retro-C item 23, exhaustion path: ``_run_payload_ready`` flushes
    ``ReportPayload`` and then ``store_report_theme`` raises a real
    (non-``IntegrityError``) DB error on **every** ``with_backoff`` attempt.
    Each attempt's partial flush rolls back to its own savepoint, so
    ``with_backoff`` exhausts cleanly and ``drive()``'s ``except Exception``
    branch runs without any ``PendingRollbackError`` escaping: the run is
    left un-advanced with ``stage_failure_count == 1`` and no half-written
    rows survive (the protected item-39 test only used a plain
    ``RuntimeError``)."""
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "payload_ready",
        {"base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    def _always_fails_at_the_database(*args, **kwargs):
        raise OperationalError(
            "UPDATE report_theme", {}, Exception("simulated persistent DB error")
        )

    monkeypatch.setattr(driver_module, "store_report_theme", _always_fails_at_the_database)

    with caplog.at_level(logging.ERROR, logger=driver_module._logger.name):
        result = _drive(session, run, natal_chart)

    # No exception escaped drive() -- the call completing at all is part of
    # what this proves.
    assert result.stage == "transits_ready"
    assert result.stage_failure_count == 1
    assert result.failed_at is None
    assert str(run.id) in caplog.text
    assert (
        session.exec(select(ReportPayload).where(ReportPayload.report_run_id == run.id)).all() == []
    ), "every attempt's partial ReportPayload flush must have rolled back to its savepoint"
    assert (
        session.exec(
            select(StoredReportTheme).where(StoredReportTheme.report_run_id == run.id)
        ).all()
        == []
    )


def test_repeated_non_concurrent_integrity_errors_at_one_stage_reach_terminal_failure(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retro-C: ``_MAX_STAGE_FAILURES`` consecutive non-concurrent
    ``IntegrityError``s at ``payload_ready`` -- each classified as a genuine
    bug because ``run.stage`` never advances -- drive the run through the
    new ``else``-branch terminal path: ``failed_at`` is set and
    ``failure_reason`` names the stage, exactly as the generic
    ``except Exception`` exhaustion path does."""
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "payload_ready",
        {"base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    # Stop at transits_ready, then neutralise the fixture's own failure bump.
    with monkeypatch.context() as m:

        def _always_fail(*args, **kwargs):
            raise RuntimeError("simulated failure -- stop at transits_ready")

        m.setitem(_STAGE_FUNCTIONS, "payload_ready", _always_fail)
        _drive(session, run, natal_chart)
        assert run.stage == "transits_ready"
    run.stage_failure_count = 0
    session.add(run)
    session.commit()

    # A stray ReportPayload row makes every payload_ready run conflict,
    # while run.stage never advances -> a genuine integrity bug each time.
    _stray_report_payload(session, client_id=client.id, report_run_id=run.id)
    session.commit()

    for expected_count in range(1, driver_module._MAX_STAGE_FAILURES + 1):
        result = _drive(session, run, natal_chart)
        assert result.stage_failure_count == expected_count

    assert result.stage == "transits_ready"
    assert result.failed_at is not None
    assert result.failure_reason is not None
    assert "payload_ready" in result.failure_reason


# --- _deserialize_generated_draft round trip ------------------------------------------


def test_deserialize_generated_draft_round_trips_a_generated_draft() -> None:
    """The reverse of ``ReportDraft.draft``'s own JSON encoding
    (``shell/adapters/postgres/report_draft.py``'s ``_json_safe``): every
    field of a ``GeneratedDraft`` -- including an empty ``entry_ids`` tuple
    -- must reconstruct equal to what was serialized, mirroring
    ``test_deserialize_theme_round_trips_a_report_theme``'s own round-trip
    shape."""
    draft = GeneratedDraft(
        energia_generale=(Sentence(text="Un mese stabile.", entry_ids=("id-1", "id-2")),),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(Sentence(text="Respira.", entry_ids=()),),
    )

    serialized = _draft_json_safe(draft)
    deserialized = driver_module._deserialize_generated_draft(serialized)

    assert deserialized == draft


def test_deserialize_generated_draft_round_trips_an_empty_draft() -> None:
    draft = GeneratedDraft(
        energia_generale=(),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(),
    )

    deserialized = driver_module._deserialize_generated_draft(_draft_json_safe(draft))

    assert deserialized == draft


# --- Story 4.8: persistent draft_ready failure marks the run terminally failed --


class _AlwaysFailingGenerator:
    """A ``Generator`` (``shell/ports/generator.py``) test double whose
    ``generate()`` always raises -- proves Story 4.8's persistent-failure
    path (a rate limit that never clears) without a real Gemini call."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, payload, style_guide, theme_previous, theme_current):
        self.calls += 1
        raise RuntimeError("simulated persistent rate limit")


def test_draft_ready_failing_five_consecutive_drive_calls_marks_the_run_terminally_failed(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I/O & Edge-Case Matrix: "Persistent draft_ready failure across many
    polls" -- the Gemini call always raises; drive() is called 5 times; the
    5th call sets failed_at/failure_reason and the run never advances past
    payload_ready.

    ``draft_ready``'s real override (``base_delay_seconds=6.0``,
    ``tests/test_runner_backoff.py`` proves that schedule itself) is swapped
    for a zero-delay one here, so this behavioral test -- 5 consecutive
    ``drive()`` calls -- doesn't spend the real ~18s/call ``with_backoff``
    would otherwise sleep; ``max_attempts`` (the thing this test's failure
    count depends on) is left unchanged.
    """
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "draft_ready",
        {"max_attempts": 3, "base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _AlwaysFailingGenerator()
    for _ in range(4):
        _drive(session, run, natal_chart, generator=generator)
        assert run.stage == "payload_ready"
        assert run.failed_at is None

    result = _drive(session, run, natal_chart, generator=generator)

    assert result.stage == "payload_ready"
    assert result.stage_failure_count == 5
    assert result.failed_at is not None
    assert result.failure_reason is not None
    assert "draft_ready" in result.failure_reason


def test_a_failed_run_is_a_noop_on_drive(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I/O & Edge-Case Matrix: "Polling a failed run" -- once
    ``run.failed_at`` is set, ``drive()`` does nothing further: no stage
    function runs, nothing about the run changes. A zero-delay draft_ready
    override keeps the fixture's 5 failing drive() calls fast, mirroring
    the previous test's own reasoning."""
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "draft_ready",
        {"max_attempts": 3, "base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _AlwaysFailingGenerator()
    for _ in range(5):
        _drive(session, run, natal_chart, generator=generator)
    assert run.failed_at is not None, "fixture did not fail the run -- test is vacuous"
    failed_at_before = run.failed_at
    failure_reason_before = run.failure_reason
    calls_before = generator.calls

    result = _drive(session, run, natal_chart, generator=generator)

    assert result is run
    assert result.failed_at == failed_at_before
    assert result.failure_reason == failure_reason_before
    assert result.stage == "payload_ready"
    assert generator.calls == calls_before, "the Generator must not be called on a failed run"


def test_draft_ready_failing_then_succeeding_resets_the_failure_counter(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I/O & Edge-Case Matrix: "Transient draft_ready failure, then success"
    -- a fail-once-then-succeed Generator still advances the run to
    draft_ready within one drive() call (with_backoff's own retry), and
    ``stage_failure_count`` resets to 0. A zero-delay draft_ready override
    avoids the one real 6s sleep this fixture would otherwise wait through."""
    monkeypatch.setitem(
        driver_module._STAGE_BACKOFF_OVERRIDES,
        "draft_ready",
        {"max_attempts": 3, "base_delay_seconds": 0.0},
    )
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    calls: list[int] = []
    real_draft = _a_generated_draft()

    class _FailsOnceThenSucceeds:
        def generate(self, payload, style_guide, theme_previous, theme_current):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("simulated transient failure")
            return real_draft

    result = _drive(session, run, natal_chart, generator=_FailsOnceThenSucceeds())

    assert len(calls) == 2, "the Generator must have been retried by with_backoff"
    assert result.stage == "gate_passed"
    assert result.stage_failure_count == 0
    assert result.failed_at is None


def test_a_stage_other_than_draft_ready_failing_persistently_also_reaches_terminal_failure(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I/O & Edge-Case Matrix: "A stage other than draft_ready fails
    persistently" -- e.g. natal_ready always raises -- is still bounded by
    the existing default with_backoff schedule and _MAX_STAGE_FAILURES;
    eventually reaches failed_at too."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    def _always_fail(*args, **kwargs):
        raise RuntimeError("simulated permanent failure")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "natal_ready", _always_fail)

    for _ in range(4):
        _drive(session, run, natal_chart)
        assert run.failed_at is None

    result = _drive(session, run, natal_chart)

    assert result.stage is None
    assert result.stage_failure_count == 5
    assert result.failed_at is not None
    assert "natal_ready" in result.failure_reason


# --- Story 3.10 (AD-20): advance() performs at most one stage transition per call ---


def test_advance_moves_the_run_forward_exactly_one_stage_per_call(session: Session) -> None:
    """AD-20 / new test (a): each ``advance()`` call moves ``run.stage``
    forward by exactly one ``_STAGE_SEQUENCE`` position, and the Generator is
    never touched until the call that lands on ``draft_ready``."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _FakeGenerator()
    expected_stages = [
        "natal_ready",
        "transits_ready",
        "payload_ready",
        "draft_ready",
        "gate_passed",
    ]

    for stage_name in expected_stages:
        result = _advance(session, run, natal_chart, generator=generator)
        assert result.stage == stage_name
        if stage_name in ("natal_ready", "transits_ready", "payload_ready"):
            assert generator.calls == [], "the Generator must not be touched before draft_ready"

    assert len(generator.calls) == 1, "the Generator is called once, on the draft_ready poll"

    # A further call does not chain past gate_passed into exported (no
    # registered function) -- it returns the current stage unchanged.
    updated_at_before = run.updated_at
    result = _advance(session, run, natal_chart, generator=generator)
    assert result.stage == "gate_passed"
    assert result.updated_at == updated_at_before


def test_a_poll_that_runs_draft_ready_calls_the_generator_once_and_stops_there(
    session: Session,
) -> None:
    """AD-20 / new test (b): the poll that runs ``draft_ready`` calls the
    Generator exactly once and returns at ``draft_ready`` -- it never also
    runs ``gate_passed`` in that same call, so no ``Report`` row exists yet."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _FakeGenerator()
    for _ in range(3):  # natal, transits, payload
        _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "payload_ready"
    assert generator.calls == []

    result = _advance(session, run, natal_chart, generator=generator)

    assert result.stage == "draft_ready"
    assert len(generator.calls) == 1
    # gate_passed did not also run in this call.
    assert session.exec(select(Report).where(Report.report_run_id == run.id)).all() == []


def test_a_poll_landing_on_draft_ready_runs_gate_passed_and_never_chains_further(
    session: Session,
) -> None:
    """AD-20 I/O Matrix "Poll lands on draft_ready": a call entered with
    ``run.stage == "draft_ready"`` runs ``gate_passed`` (one generator-free
    Gate call) and returns at ``gate_passed`` -- it never chains into a
    later stage in the same call."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    generator = _FakeGenerator()
    for _ in range(4):  # natal, transits, payload, draft
        _advance(session, run, natal_chart, generator=generator)
    assert run.stage == "draft_ready"
    generator_calls_before = list(generator.calls)

    result = _advance(session, run, natal_chart, generator=generator)

    assert result.stage == "gate_passed"
    assert generator.calls == generator_calls_before, "gate_passed must not call the Generator"
    assert len(session.exec(select(Report).where(Report.report_run_id == run.id)).all()) == 1


def test_advance_resumes_at_the_next_stage_after_a_simulated_mid_run_kill(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-20 / new test (c): a run polled after a simulated mid-run kill
    (``run.stage`` at an intermediate value, its stored columns present)
    resumes at the next stage and recomputes nothing already persisted."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    _advance(session, run, natal_chart)  # natal_ready
    _advance(session, run, natal_chart)  # transits_ready
    assert run.stage == "transits_ready", "fixture did not reach transits_ready -- vacuous"
    recorded_start, recorded_end = run.month_start_utc, run.month_end_utc
    recorded_events = run.transit_events

    # Simulate the process restarting: nothing already persisted may be
    # recomputed on the next poll.
    def _raise_if_called(*args, **kwargs):
        raise AssertionError("client_month_interval_utc must not be called again")

    monkeypatch.setattr(driver_module, "client_month_interval_utc", _raise_if_called)

    def _transits_raise(*args, **kwargs):
        raise AssertionError("transits_ready must not run again")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _transits_raise)

    result = _advance(session, run, natal_chart)  # resumes at payload_ready

    assert result.stage == "payload_ready"
    assert result.month_start_utc == recorded_start
    assert result.month_end_utc == recorded_end
    assert result.transit_events == recorded_events


def test_advance_returns_the_current_stage_without_advancing_when_the_lock_is_unavailable(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-20 / new test (d): with ``try_acquire_advance_lock`` forced to
    ``False`` (a concurrent poll holds it), ``advance()`` returns the run's
    current stage, runs no stage function, and commits no stage change."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    _advance(session, run, natal_chart)  # natal_ready
    assert run.stage == "natal_ready"
    updated_at_before = run.updated_at

    monkeypatch.setattr(driver_module, "try_acquire_advance_lock", lambda session, run_id: False)

    called: list[int] = []
    real_transits = _STAGE_FUNCTIONS["transits_ready"]

    def _counting_transits(*args, **kwargs):
        called.append(1)
        return real_transits(*args, **kwargs)

    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _counting_transits)

    result = _advance(session, run, natal_chart)

    assert result.stage == "natal_ready"
    assert called == [], "no stage function runs when the advance lock is unavailable"
    assert result.updated_at == updated_at_before
    reloaded = session.get(ReportRun, run.id)
    assert reloaded is not None
    assert reloaded.stage == "natal_ready"


def test_advance_takes_the_advisory_lock_on_the_winning_path(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-20: a normal in-progress poll acquires the advance lock exactly
    once, keyed on the run's id, before running its one stage."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    lock_calls: list[tuple] = []
    real_lock = driver_module.try_acquire_advance_lock

    def _spy_lock(session_arg, run_id):
        lock_calls.append((session_arg, run_id))
        return real_lock(session_arg, run_id)

    monkeypatch.setattr(driver_module, "try_acquire_advance_lock", _spy_lock)

    result = _advance(session, run, natal_chart)  # runs natal_ready

    assert len(lock_calls) == 1, "advance() must take the lock exactly once on the winning path"
    assert lock_calls[0][0] is session
    assert lock_calls[0][1] == run.id
    assert result.stage == "natal_ready", "the run still advances exactly one stage"


def test_advance_takes_no_advisory_lock_when_the_run_is_already_terminally_failed(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-20 / this module's docstring: a run with ``failed_at`` set
    short-circuits before any lock is acquired."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(
        client_id=client.id,
        month="2026-01",
        stage="draft_ready",
        failed_at=datetime(2026, 1, 20, 12, 0, 0, tzinfo=UTC),
        failure_reason="regeneration bound exhausted after 4 attempts: simulated",
    )
    session.add(run)
    session.commit()

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("try_acquire_advance_lock must not be called on a failed run")

    monkeypatch.setattr(driver_module, "try_acquire_advance_lock", _fail_if_called)

    result = _advance(session, run, natal_chart)

    assert result is run
    assert result.stage == "draft_ready"
    assert result.failed_at is not None
