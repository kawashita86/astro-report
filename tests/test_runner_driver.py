"""``shell/runner/driver.py::drive()`` -- Story 3.5's own I/O & Edge-Case
Matrix rows for advancing a ``ReportRun``, extended by Story 3.8's own row
for ``payload_ready``, Story 4.6's own row for ``draft_ready``, and
``_deserialize_transit_events``'s round trip.

An in-memory SQLite engine stands in for Postgres, mirroring
``tests/test_client_store.py``; the Natal Chart, ``ComputationConfig``,
``SectionsConfig`` and ``EphemerisIdentity`` are all real (the same
known-good Fort Worth fixture ``tests/test_client_store.py`` uses), since
three of the four registered stages (``natal_ready``, ``transits_ready``,
``payload_ready``) call real ``core/`` code -- only the *failure* scenarios
below inject a fake stage function, mirroring the story's own Design Notes
("no live external call demonstrates the backoff"). ``draft_ready`` is the
one stage with a genuine external call (the Generator port), so every test
here drives it through ``_FakeGenerator`` rather than a real Gemini call --
``tests/test_report_draft_store.py`` covers the persisted row's own shape,
and the Gemini adapter has its own test module.

Four real stages are now registered (Story 4.6 added ``draft_ready``), so a
fresh, fully-successful ``drive()`` call advances to ``draft_ready`` -- the
first name in ``_STAGE_SEQUENCE`` with no registered function is now
``gate_passed``. ``_create_client_and_chart`` seeds a Style Guide version
alongside the Client/Natal Chart so every full-drive test below reaches
``draft_ready`` without each test seeding one itself.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import shell.runner.driver as driver_module
from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.generation import GeneratedDraft, Sentence
from core.types.memory import ReportTheme, ThemeAspect, ThemeLunation
from core.types.place import ResolvedPlace
from core.types.transits import Ingress, Lunation, StandingRetrograde, Station, TransitAspectEvent
from shell.adapters.postgres.client import create_client_with_chart, deserialize_natal_chart
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_payload import ReportPayload
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.report_theme import StoredReportTheme
from shell.adapters.postgres.report_theme import _json_safe as _theme_json_safe
from shell.adapters.postgres.style_guide import create_style_guide_version
from shell.computation import load_computation_config
from shell.ports.generator import Generator, StyleGuideVersion
from shell.runner.driver import _STAGE_FUNCTIONS, _deserialize_transit_events, drive
from shell.sections import load_sections_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()

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


def _drive(session: Session, run: ReportRun, natal_chart, generator: Generator | None = None):
    return drive(
        session,
        run,
        natal_chart=natal_chart,
        config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
        sections_config=_SECTIONS_CONFIG,
        generator=generator if generator is not None else _FakeGenerator(),
    )


# --- Fresh run, all four registered stages succeed -----------------------------


def test_fresh_run_advances_through_all_four_registered_stages(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    assert result.stage == "draft_ready"
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
    assert stored.stage == "draft_ready"
    assert stored.transit_events is not None


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

    assert result.stage == "draft_ready"
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

    assert result.stage == "draft_ready"
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

    assert result.stage == "draft_ready"
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
    assert run.stage == "draft_ready", "fixture did not complete -- test is vacuous"
    events_before = run.transit_events
    updated_at_before = run.updated_at

    def _raise_if_called(*args, **kwargs):
        raise AssertionError("a completed stage must not be called again")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "natal_ready", _raise_if_called)
    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _raise_if_called)
    monkeypatch.setitem(_STAGE_FUNCTIONS, "payload_ready", _raise_if_called)
    monkeypatch.setitem(_STAGE_FUNCTIONS, "draft_ready", _raise_if_called)

    result = _drive(session, run, natal_chart)

    assert result is run
    assert result.stage == "draft_ready"
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
    assert result.stage == "draft_ready"
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
        result = _drive(session, run, natal_chart)

    # No exception escaped drive() -- the call above completing at all is
    # part of what this test proves.
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

    result = _drive(session, run, natal_chart)

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

        assert result.stage == "draft_ready"
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

    # gate_passed has no registered function -- drive() must stop there
    # without raising, having already completed draft_ready (Story 4.6).
    assert result.stage == "draft_ready"


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

    assert result.stage == "draft_ready"
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

    assert result.stage == "draft_ready"
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
    assert first_run.stage == "draft_ready", "fixture did not complete -- test is vacuous"

    first_stored_theme = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.report_run_id == first_run.id)
    ).one()
    expected_theme_previous = driver_module._deserialize_theme(first_stored_theme.theme)

    second_run = ReportRun(client_id=client.id, month="2026-02")
    session.add(second_run)
    session.commit()
    generator = _FakeGenerator()
    result = _drive(session, second_run, natal_chart, generator=generator)

    assert result.stage == "draft_ready"
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
    assert first_run.stage == "draft_ready", "fixture did not complete -- test is vacuous"

    first_stored_theme = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.report_run_id == first_run.id)
    ).one()
    expected_theme_previous = driver_module._deserialize_theme(first_stored_theme.theme)

    third_run = ReportRun(client_id=client.id, month="2026-03")
    session.add(third_run)
    session.commit()
    generator = _FakeGenerator()
    result = _drive(session, third_run, natal_chart, generator=generator)

    assert result.stage == "draft_ready"
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

    assert result.stage == "draft_ready"
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
