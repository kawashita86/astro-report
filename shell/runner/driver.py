"""``advance()``: moves one ``ReportRun`` forward by **at most one** of
AD-10's six named stages per call, persisting that stage's output before it
returns (Story 3.5, reshaped for AD-20 by Story 3.10).

**Why one stage per call, from the poll GET only, with no background task or
queue.** AD-20 requires the start ``POST`` to return instantly and each
status poll to move the run forward exactly one stage. So
``POST /clients/{client_id}/report-runs`` only creates the row and
redirects, and ``advance()`` is called *only* from
``GET /report-runs/{run_id}``: the first stage runs on the first poll, and a
poll may take as long as its one stage (one external Generator call plus
bounded backoff, at ``draft_ready``) but never chains into a second -- so
closing the tab can never abandon work mid-pipeline. BUILD-ORDER.md's E5
still rules out an in-process background task ("run state lives only in
memory, lost silently on restart") and a queue ("no queue infrastructure
needed"): the browser's poll cadence remains the only drain. Concurrent
polls for one run are single-flighted by a Postgres transaction-scoped
advisory lock on the run id (``shell/runner/advisory_lock.py``) -- the poll
that takes the lock advances one stage; the other returns the current stage
untouched. See ``shell/http/routes/report_runs.py``.

**Why only five of the six stages get real stage functions (so far).**
BUILD-ORDER.md: "the runner introduced once two real stages exist."
`natal_ready`/`transits_ready` arrived in Story 3.5; `payload_ready` in
Story 3.8, once ``core/payload/`` (Stories 3.6-3.8) existed to call;
`draft_ready` in Story 4.6, once the Generator port and its Gemini adapter
(Story 4.5) existed to call; `gate_passed` in Story 5.3, once
``core/gate/run.py::run_gate()`` (Story 5.2) existed to call. Registering a
stage before its implementation exists would mean stubbing a lie.
`_STAGE_SEQUENCE` names all six stages for display/ordering;
`_STAGE_FUNCTIONS` only the ones actually implemented -- `advance()` stops
the moment the next stage name has no registered function (today,
`exported`).

**`draft_ready` is the first stage with a live external call.** The three
earlier stages read only local state (the already-persisted chart, the
local ephemeris); `draft_ready` calls the injected `Generator`
(``shell/ports/generator.py``) over the network. It runs through the same
uniform ``with_backoff`` wrapper every other stage already does -- no
special-casing here for "this one talks to a rate-limited API" -- so a
transient Generator failure retries exactly like a transient local one
would. A dedicated request-rate ceiling for the Generator adapter itself
(rather than `with_backoff`'s own retry-on-failure) is Story 4.8's own
deliverable, sized for its 10 RPM ceiling; nothing here anticipates it.

**`transit_events` as one JSON column, not four new tables.** Story 3.6 will
read these events to assemble the Payload and may reshape how they're
consumed; committing to per-kind tables now risks a schema this story can't
justify. Serialized the same way ``shell/adapters/postgres/client.py``'s
``_serialize``/``_json_safe`` already serialize a stored chart
(``Decimal`` -> ``str``), extended for ``datetime`` -- these dataclasses
carry both -- and each entry tagged ``"kind"`` since the four scan functions
return five different dataclasses.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from core.domains.profiles import assemble_domain_profiles
from core.domains.rulers import resolve_house_rulers
from core.ephemeris.identity import EphemerisIdentity
from core.errors import GateFailedError
from core.gate.run import run_gate
from core.memory.derive import derive_theme
from core.payload.assemble import assemble_payload
from core.payload.day_lists import project_day_lists
from core.payload.freeze import freeze_payload
from core.transits.aspects import find_transit_aspects
from core.transits.ingresses import find_ingresses
from core.transits.lunations import find_lunations
from core.transits.stations import find_stations
from core.types.chart import NatalChart
from core.types.computation import ComputationConfig
from core.types.gate import GateVocabulary
from core.types.generation import GeneratedDraft, Sentence
from core.types.memory import ReportTheme, ThemeAspect, ThemeLunation
from core.types.sections import SectionsConfig
from core.types.transits import Ingress, Lunation, StandingRetrograde, Station, TransitAspectEvent
from shell.adapters.postgres.client import Client
from shell.adapters.postgres.gate_result import store_gate_result
from shell.adapters.postgres.report import store_report
from shell.adapters.postgres.report_draft import (
    ReportDraft,
    next_report_draft_attempt,
    store_report_draft,
)
from shell.adapters.postgres.report_payload import ReportPayload, store_report_payload
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.report_theme import (
    StoredReportTheme,
    most_recent_prior_report_theme,
    store_report_theme,
)
from shell.adapters.postgres.style_guide import current_style_guide
from shell.ports.generator import Generator, StyleGuideVersion
from shell.runner.advisory_lock import try_acquire_advance_lock
from shell.runner.backoff import with_backoff
from shell.runner.month import client_month_interval_utc

__all__ = ["advance"]

_logger = logging.getLogger(__name__)

#: All six AD-10 stage names, in the order a ``ReportRun`` advances through --
#: named for display/ordering regardless of whether a function is registered
#: for them yet (see the module's Design Notes).
_STAGE_SEQUENCE: tuple[str, ...] = (
    "natal_ready",
    "transits_ready",
    "payload_ready",
    "draft_ready",
    "gate_passed",
    "exported",
)

#: Per-stage overrides for `with_backoff`'s keyword arguments, keyed by
#: stage name. `draft_ready` is the only stage with a real rate-limited
#: network call (the module's own Design Notes): 3 attempts, 6-second base
#: delay, doubling to a second retry at 12s -- three Gemini attempts inside
#: one `advance()` call span 0s/6s/18s, comfortably inside the provider's 10
#: requests-per-minute ceiling even if a poll lands right after a prior
#: `advance()` call's own attempts.
#:
#: `gate_passed` (`_run_gate_passed`) is capped at a single attempt. Its
#: dominant failure mode is a deterministic `GateFailedError`: the stage
#: re-checks the *same* already-persisted draft with the pure `run_gate()`
#: (`core/gate/run.py`), so an in-process `with_backoff` retry only re-runs
#: an identical failing check -- wasted work that delays the real recovery,
#: `advance()`'s `except GateFailedError` regeneration path, which produces a
#: genuinely new draft on the *next* `advance()` call. `max_attempts=1` lets
#: that `GateFailedError` propagate on the first attempt.
#:
#: Tradeoff: `_run_gate_passed` also reads `ReportDraft`/`ReportPayload`
#: back and, on a pass, writes `Report` + `StoredGateResult`. A *transient*
#: DB error in any of those is no longer retried within one `advance()` call;
#: it surfaces through `advance()`'s generic `except Exception` branch, which
#: increments `stage_failure_count` from its first occurrence, so a flaky
#: database now recovers across poll cycles (`_MAX_STAGE_FAILURES`) rather
#: than inside a single call. A stage absent from this mapping keeps
#: `with_backoff`'s plain defaults (`max_attempts=3`, `shell/runner/backoff.py`).
_STAGE_BACKOFF_OVERRIDES: dict[str, dict[str, object]] = {
    "draft_ready": {"max_attempts": 3, "base_delay_seconds": 6.0},
    "gate_passed": {"max_attempts": 1},
}

#: Consecutive `with_backoff` exhaustions on a run's current stage, across
#: separate `advance()` calls, before that run is marked terminally failed
#: (Story 4.8). Each `advance()` call already spends up to 3 Gemini attempts
#: (~18s) when stuck at `draft_ready`; 5 such exhausted `advance()` calls is
#: ~15 real attempts -- a genuinely exhausted run, not a blip (the module's
#: own Design Notes).
_MAX_STAGE_FAILURES = 5

#: Regeneration attempts a run's current cycle may spend on a `GateFailedError`
#: before it is marked terminally failed instead of regenerated forever
#: (Story 5.4). Separate from `_MAX_STAGE_FAILURES`: a `GateFailedError` never
#: touches `stage_failure_count` (the module's own Design Notes explain why a
#: shared counter can't work -- a regeneration's `draft_ready` re-run succeeds
#: by definition, resetting `stage_failure_count` before `gate_passed` even
#: runs again). No planning artifact states a number (FR-21/AD-10 only
#: require "bounded"); `3` mirrors `with_backoff`'s own default
#: `max_attempts=3`.
_MAX_REGENERATIONS = 3

#: A stage function's uniform signature: every registered stage receives the
#: same context, whether or not it needs all of it, so the registry stays a
#: plain ``{name: function}`` mapping rather than growing per-stage plumbing
#: in ``advance()`` itself as more stages register. ``generator`` joined the
#: signature in Story 4.6 for ``draft_ready``; ``vocabulary`` joined it in
#: Story 5.3 for ``gate_passed`` -- every other registered stage still
#: receives both, unused, rather than the registry growing a second,
#: narrower signature.
StageFn = Callable[
    [
        Session,
        ReportRun,
        NatalChart,
        ComputationConfig,
        EphemerisIdentity,
        SectionsConfig,
        Generator,
        GateVocabulary,
    ],
    None,
]


def _run_natal_ready(
    session: Session,
    run: ReportRun,
    natal_chart: NatalChart,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
    sections_config: SectionsConfig,
    generator: Generator,
    vocabulary: GateVocabulary,
) -> None:
    """``natal_ready``: resolve ``run.month`` against ``run.client_id``'s
    local calendar into ``[month_start_utc, month_end_utc)``.

    The Natal Chart itself needs no computation here -- it is already
    stored and already deserialized into ``natal_chart`` by the caller
    (``shell/http/routes/report_runs.py``); this stage's whole job is the
    month-boundary resolution Stories 3.1-3.4 deferred. ``generator``/
    ``vocabulary`` are part of :data:`StageFn`'s uniform signature (Stories
    4.6/5.3); this stage does not use either.
    """
    client = session.get(Client, run.client_id)
    if client is None:
        raise RuntimeError(f"ReportRun {run.id} references a missing Client.")
    month_start_utc, month_end_utc = client_month_interval_utc(client, run.month)
    run.month_start_utc = month_start_utc
    run.month_end_utc = month_end_utc


def _run_transits_ready(
    session: Session,
    run: ReportRun,
    natal_chart: NatalChart,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
    sections_config: SectionsConfig,
    generator: Generator,
    vocabulary: GateVocabulary,
) -> None:
    """``transits_ready``: call the four Story 3.1-3.4 scan functions across
    ``[run.month_start_utc, run.month_end_utc)`` -- read back from the row,
    never recomputed, so a process restart between stages loses nothing --
    and record every result, tagged by kind, into ``run.transit_events``.
    ``generator``/``vocabulary`` are part of :data:`StageFn`'s uniform
    signature (Stories 4.6/5.3); this stage does not use either.
    """
    assert run.month_start_utc is not None and run.month_end_utc is not None, (
        f"ReportRun {run.id} reached transits_ready without a resolved month interval."
    )
    month_start_utc, month_end_utc = run.month_start_utc, run.month_end_utc

    events: list[dict[str, Any]] = [
        _serialize_event("aspect", event)
        for event in find_transit_aspects(natal_chart, month_start_utc, month_end_utc, config)
    ]
    events.extend(
        _serialize_event(
            "standing_retrograde" if isinstance(record, StandingRetrograde) else "station",
            record,
        )
        for record in find_stations(month_start_utc, month_end_utc, config)
    )
    events.extend(
        _serialize_event("ingress", ingress)
        for ingress in find_ingresses(natal_chart, month_start_utc, month_end_utc, config)
    )
    events.extend(
        _serialize_event("lunation", lunation)
        for lunation in find_lunations(natal_chart, month_start_utc, month_end_utc)
    )
    run.transit_events = events


def _stage_index(stage: str | None) -> int:
    """``-1`` for ``None`` (nothing completed yet), otherwise ``stage``'s
    position in ``_STAGE_SEQUENCE``."""
    if stage is None:
        return -1
    return _STAGE_SEQUENCE.index(stage)


def _json_safe(value: Any) -> Any:
    """``Decimal`` -> ``str``, ``datetime`` -> ISO 8601 -- everything else
    passes through unchanged. Extends
    ``shell/adapters/postgres/client.py``'s ``_json_safe`` (``Decimal``
    only): the transit-event dataclasses carry both types, unlike
    ``StoredNatalChart``'s JSON payloads."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_event(kind: str, event: Any) -> dict[str, Any]:
    """One transit-event dataclass -> a JSON-safe dict tagged ``"kind"``
    (``aspect``/``station``/``standing_retrograde``/``ingress``/``lunation``).

    :class:`core.types.transits.Lunation` carries its own ``kind`` field
    (``"new_moon"``/``"full_moon"``) -- a genuine name collision with this
    wrapper's own outer ``"kind"`` tag, not the same value under two names.
    Renamed to ``"lunation_kind"`` before the outer tag is applied, so
    neither is silently lost: the outer ``"kind"`` always identifies which
    of the five event shapes this is, and a Lunation's own new/full
    distinction survives under its own key.
    """
    assert is_dataclass(event)
    fields = {key: _json_safe(value) for key, value in asdict(event).items()}
    if "kind" in fields:
        fields[f"{kind}_kind"] = fields.pop("kind")
    return {"kind": kind, **fields}


def _parse_datetime(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _deserialize_transit_events(
    events: list[dict[str, Any]],
) -> tuple[
    tuple[TransitAspectEvent, ...],
    tuple[Station | StandingRetrograde, ...],
    tuple[Ingress, ...],
    tuple[Lunation, ...],
]:
    """The reverse of ``_serialize_event``: split ``run.transit_events`` back
    into the four tuples ``core/payload/assemble.py::assemble_payload()``
    takes -- ``stations`` mixed ``Station | StandingRetrograde``, matching
    ``find_stations()``'s own return shape (``_run_transits_ready``'s
    ``isinstance`` split, done here in reverse only at the dataclass-choice
    step, never re-splitting the two kinds apart into separate tuples).
    """
    aspects: list[TransitAspectEvent] = []
    stations: list[Station | StandingRetrograde] = []
    ingresses: list[Ingress] = []
    lunations: list[Lunation] = []

    for event in events:
        kind = event["kind"]
        fields = {key: value for key, value in event.items() if key != "kind"}
        if kind == "aspect":
            aspects.append(
                TransitAspectEvent(
                    transiting_body=fields["transiting_body"],
                    natal_point=fields["natal_point"],
                    aspect=fields["aspect"],
                    perfected_at=_parse_datetime(fields["perfected_at"]),
                    never_perfected=fields["never_perfected"],
                    orb_entry_at=_parse_datetime(fields["orb_entry_at"]),
                    orb_exit_at=_parse_datetime(fields["orb_exit_at"]),
                )
            )
        elif kind == "station":
            stations.append(
                Station(
                    body=fields["body"],
                    direction=fields["direction"],
                    station_at=_parse_datetime(fields["station_at"]),
                    longitude=Decimal(fields["longitude"]),
                )
            )
        elif kind == "standing_retrograde":
            stations.append(
                StandingRetrograde(
                    body=fields["body"],
                    retrograde_start_utc=_parse_datetime(fields["retrograde_start_utc"]),
                    retrograde_end_utc=_parse_datetime(fields["retrograde_end_utc"]),
                )
            )
        elif kind == "ingress":
            ingresses.append(
                Ingress(
                    body=fields["body"],
                    house_departed=fields["house_departed"],
                    house_entered=fields["house_entered"],
                    crossed_at=_parse_datetime(fields["crossed_at"]),
                )
            )
        elif kind == "lunation":
            lunations.append(
                Lunation(
                    kind=fields["lunation_kind"],
                    occurred_at=_parse_datetime(fields["occurred_at"]),
                    longitude=Decimal(fields["longitude"]),
                    natal_house=fields["natal_house"],
                )
            )
        else:
            raise ValueError(f"unrecognized transit event kind: {kind!r}")

    return tuple(aspects), tuple(stations), tuple(ingresses), tuple(lunations)


def _run_payload_ready(
    session: Session,
    run: ReportRun,
    natal_chart: NatalChart,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
    sections_config: SectionsConfig,
    generator: Generator,
    vocabulary: GateVocabulary,
) -> None:
    """``payload_ready``: assemble this month's ``Payload`` (Story 3.6),
    project its two day lists (Story 3.7), freeze both into canonical JSON
    (Story 3.8) and persist a ``ReportPayload`` row for ``run`` -- then
    derive and persist this month's ``ReportTheme`` from that same
    ``Payload`` (Story 4.3, AD-14), reusing ``payload``/``config`` already in
    scope rather than a new AD-10 stage.

    ``run.transit_events`` is read back and split by
    ``_deserialize_transit_events`` -- never recomputed, mirroring how
    ``_run_natal_ready``'s month interval is read back rather than
    recomputed once ``transits_ready`` has already run. ``DomainProfiles``
    are recomputed fresh from ``natal_chart``/``config`` instead: cheap and
    pure, with no stored column to read back from (see Story 3.8's Design
    Notes).
    """
    assert run.transit_events is not None, (
        f"ReportRun {run.id} reached payload_ready without transit events."
    )

    aspects, stations, ingresses, lunations = _deserialize_transit_events(run.transit_events)
    rulers = resolve_house_rulers(natal_chart, config)
    profiles = assemble_domain_profiles(natal_chart, rulers)
    payload = assemble_payload(
        natal_chart, profiles, aspects, stations, ingresses, lunations, config, sections_config
    )
    day_lists = project_day_lists(payload, natal_chart, config)
    frozen = freeze_payload(
        payload,
        day_lists,
        config=config,
        sections_config=sections_config,
        ephemeris_identity=ephemeris_identity,
    )
    store_report_payload(session, run=run, frozen=frozen)

    theme = derive_theme(payload, config)
    store_report_theme(session, run=run, theme=theme)


def _deserialize_theme(theme: dict[str, Any]) -> ReportTheme:
    """The reverse of ``StoredReportTheme.theme``'s JSON encoding
    (``shell/adapters/postgres/report_theme.py``'s own ``_json_safe``) back
    into a real ``ReportTheme`` -- read back, never recomputed, mirroring
    ``_deserialize_transit_events``'s own round trip for ``run.transit_events``.

    ``ThemeAspect.orb_entry_at`` and ``StandingRetrograde``'s two fields are
    always set (non-``Optional`` on those dataclasses), but are parsed via
    the same ``_parse_datetime`` used for every possibly-``None`` field here
    -- mirroring how ``_deserialize_transit_events`` already parses
    ``TransitAspectEvent.orb_entry_at`` (also non-``Optional``) the same way,
    rather than a second, narrower datetime parser.
    """
    return ReportTheme(
        dominant_aspects=tuple(
            ThemeAspect(
                transiting_body=aspect["transiting_body"],
                natal_point=aspect["natal_point"],
                aspect=aspect["aspect"],
                perfected_at=_parse_datetime(aspect["perfected_at"]),
                never_perfected=aspect["never_perfected"],
                orb_entry_at=_parse_datetime(aspect["orb_entry_at"]),
                orb_exit_at=_parse_datetime(aspect["orb_exit_at"]),
            )
            for aspect in theme["dominant_aspects"]
        ),
        lunations=tuple(
            ThemeLunation(kind=lunation["kind"], natal_house=lunation["natal_house"])
            for lunation in theme["lunations"]
        ),
        standing_retrogrades=tuple(
            StandingRetrograde(
                body=retrograde["body"],
                retrograde_start_utc=_parse_datetime(retrograde["retrograde_start_utc"]),
                retrograde_end_utc=_parse_datetime(retrograde["retrograde_end_utc"]),
            )
            for retrograde in theme["standing_retrogrades"]
        ),
    )


def _deserialize_generated_draft(draft: dict[str, Any]) -> GeneratedDraft:
    """The reverse of ``ReportDraft.draft``'s JSON encoding
    (``shell/adapters/postgres/report_draft.py``'s own ``_json_safe``) back
    into a real ``GeneratedDraft`` -- read back, never recomputed, mirroring
    ``_deserialize_theme``'s own round trip for ``StoredReportTheme.theme``.

    ``draft`` is a dict of eight keys (``GeneratedDraft``'s own field
    names), each a list of ``{"text": ..., "entry_ids": [...]}`` objects;
    each is rebuilt as a ``tuple[Sentence, ...]`` before
    ``GeneratedDraft(**fields)`` reassembles the whole value -- key order
    does not matter, since every one of ``GeneratedDraft``'s eight fields is
    passed by name.
    """
    fields = {
        section: tuple(
            Sentence(text=sentence["text"], entry_ids=tuple(sentence["entry_ids"]))
            for sentence in sentences
        )
        for section, sentences in draft.items()
    }
    return GeneratedDraft(**fields)


def _run_draft_ready(
    session: Session,
    run: ReportRun,
    natal_chart: NatalChart,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
    sections_config: SectionsConfig,
    generator: Generator,
    vocabulary: GateVocabulary,
) -> None:
    """``draft_ready``: call the ``Generator`` port (Story 4.5, AD-3) with
    this run's already-persisted ``Payload``, the Style Guide currently in
    force, this month's already-persisted ``ReportTheme`` as
    ``theme_current`` and this Client's most recent prior month's
    ``ReportTheme`` (if any) as ``theme_previous`` (Story 4.7) -- then
    persist the returned ``GeneratedDraft`` verbatim.

    ``payload``/``theme_current``/``theme_previous`` are all read back --
    from ``ReportPayload``/``StoredReportTheme``/
    ``most_recent_prior_report_theme()`` respectively -- never recomputed,
    mirroring every other stage function's own "read back, never recomputed"
    pattern (this story's Boundaries). ``vocabulary`` is part of
    :data:`StageFn`'s uniform signature (Story 5.3); this stage does not use
    it -- the Groundedness Gate it feeds runs one stage later, at
    ``gate_passed``.

    The persisted ``ReportDraft`` is tagged
    ``attempt=next_report_draft_attempt(session, run.id)`` (Story 5.4,
    amended by Story 5.8): a count of existing ``ReportDraft`` rows for
    ``run``, not ``run.regeneration_count`` directly -- the two still
    coincide on this automatic path (``0`` the first time this stage runs,
    incrementing by one each regeneration), but only the count stays correct
    once Story 5.8's hand-correction route can also mint a row for this run
    without ever touching ``regeneration_count``. So a second (or third)
    draft for the same run is a new, distinctly-tagged row, never a conflict
    with the first, regardless of which route minted the prior one.
    """
    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).one()
    stored_theme = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.report_run_id == run.id)
    ).one()
    style_guide = current_style_guide(session)

    theme_current = _deserialize_theme(stored_theme.theme)
    stored_prior_theme = most_recent_prior_report_theme(
        session, run.client_id, before_month=run.month
    )
    theme_previous = (
        None if stored_prior_theme is None else _deserialize_theme(stored_prior_theme.theme)
    )
    draft = generator.generate(
        stored_payload.payload,
        StyleGuideVersion(version=style_guide.version, content=style_guide.content),
        theme_previous,
        theme_current,
    )
    store_report_draft(
        session,
        run=run,
        style_guide_version=style_guide.version,
        sections_config_version=stored_payload.sections_config_version,
        draft=draft,
        attempt=next_report_draft_attempt(session, run.id),
    )


def _run_gate_passed(
    session: Session,
    run: ReportRun,
    natal_chart: NatalChart,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
    sections_config: SectionsConfig,
    generator: Generator,
    vocabulary: GateVocabulary,
) -> None:
    """``gate_passed``: re-derive this run's already-persisted
    ``GeneratedDraft`` and ``Payload``, run the Groundedness Gate
    (Story 5.2, ``core/gate/run.py::run_gate()``) against them, and on a
    pass persist a new immutable ``Report`` row -- never on failure
    (Story 5.3) -- alongside a ``StoredGateResult`` row recording the pass
    (Story 5.6). The mirror write for a *failing* check lives in ``advance()``'s
    ``except GateFailedError`` block instead, not here: this stage's
    ``with_backoff`` wrapper is capped at ``max_attempts=1``
    (:data:`_STAGE_BACKOFF_OVERRIDES`), so a raised ``GateFailedError``
    propagates on the first attempt straight to that handler, which owns the
    failing ``StoredGateResult`` write and the regeneration bookkeeping (this
    story's Design Notes, as amended by epic-6-retro item 43).

    ``stored_draft``/``stored_payload`` are both read back -- from
    ``ReportDraft``/``ReportPayload`` respectively, via
    ``_deserialize_generated_draft`` for the former -- never recomputed,
    mirroring every other stage function's own "read back, never
    recomputed" pattern (this story's Boundaries). On
    ``GateResult.passed is False``, raises :class:`core.errors.GateFailedError`
    so ``advance()``'s ``GateFailedError``-specific handling (Story 5.4)
    rewinds ``run.stage`` to ``payload_ready`` for a bounded regeneration --
    no ``Report`` row is ever written on a failing pass. ``natal_chart``/
    ``ephemeris_identity`` are part of :data:`StageFn`'s uniform signature;
    this stage does not use either.

    ``stored_draft`` is the *latest* ``ReportDraft`` for ``run`` -- highest
    ``attempt`` -- never ``.one()`` (Story 5.4): more than one row is now
    expected once a run has regenerated at least once, and the Gate must
    always check the most recently generated draft, not an arbitrary or the
    very first one.
    """
    stored_draft = session.exec(
        select(ReportDraft)
        .where(ReportDraft.report_run_id == run.id)
        .order_by(ReportDraft.attempt.desc())
    ).first()
    assert stored_draft is not None, (
        f"ReportRun {run.id} reached gate_passed without a persisted ReportDraft."
    )
    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).one()

    draft = _deserialize_generated_draft(stored_draft.draft)
    result = run_gate(draft, stored_payload.payload, vocabulary)

    if not result.passed:
        raise GateFailedError(result.violations)

    store_report(
        session,
        run=run,
        style_guide_version=stored_draft.style_guide_version,
        payload_schema_version=stored_payload.schema_version,
        gate_vocabulary_version=result.vocabulary_version,
        gate_vocabulary_content_hash=result.vocabulary_content_hash,
    )
    store_gate_result(
        session,
        run=run,
        passed=True,
        regeneration_count=run.regeneration_count,
        vocabulary_version=result.vocabulary_version,
        vocabulary_content_hash=result.vocabulary_content_hash,
        violations=result.violations,
    )


#: Only the stages implemented so far -- Story 3.9+ registers the rest,
#: unchanged (see the module's Design Notes).
_STAGE_FUNCTIONS: dict[str, StageFn] = {
    "natal_ready": _run_natal_ready,
    "transits_ready": _run_transits_ready,
    "payload_ready": _run_payload_ready,
    "draft_ready": _run_draft_ready,
    "gate_passed": _run_gate_passed,
}


def advance(
    session: Session,
    run: ReportRun,
    *,
    natal_chart: NatalChart,
    natal_chart_id: UUID,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
    sections_config: SectionsConfig,
    generator: Generator,
    vocabulary: GateVocabulary,
) -> ReportRun:
    """Advance ``run`` by **at most one** stage: run the single next stage
    after ``run.stage`` in ``_STAGE_SEQUENCE`` that has a registered function
    in ``_STAGE_FUNCTIONS``, commit, and return (AD-20, Story 3.10).

    Called **only** from ``poll_report_run``
    (``shell/http/routes/report_runs.py``) -- never from the start ``POST``,
    a thread, an ``asyncio`` task, a queue consumer or a scheduled job. Each
    status poll moves the run forward exactly one stage; the start route just
    creates the row and redirects, so the first stage runs on the first
    poll. A poll landing on ``draft_ready`` runs ``gate_passed`` (one
    ``generator``-free Gate call) and returns -- it never also chains into a
    later stage in the same call. If ``run.stage`` is ``None``, this runs
    ``natal_ready`` only. If ``run.stage`` is ``gate_passed`` (or the next
    stage name has no registered function yet, e.g. ``exported``), this
    returns ``run`` unchanged with no commit.

    Concurrent polls for the same run are single-flighted by a Postgres
    transaction-scoped advisory lock on ``run.id``
    (``shell/runner/advisory_lock.py::try_acquire_advance_lock``), taken
    right after the ``failed_at`` short-circuit: the poll that gets the lock
    advances one stage and commits (Postgres releases the lock on that
    ``commit()`` / ``rollback()``, or if the connection drops -- no explicit
    unlock), while a poll that does not get the lock rolls back, refreshes
    ``run`` and returns its current stage without running any stage. On a
    non-Postgres backend (SQLite, in tests) the lock is a no-op that always
    grants -- there is no cross-connection concurrency there to guard, and
    the concurrent-``advance()`` ``IntegrityError`` classification below
    still stands as defense-in-depth.

    ``natal_chart_id`` (Story 6.4) is recorded onto ``run.natal_chart_id``
    exactly once, on the call that advances ``run`` through ``natal_ready``
    -- never touched again by any later stage or regeneration, mirroring
    ``month_start_utc``/``month_end_utc``'s own forward-only assignment
    inside that same stage. It is set here, in the generic per-stage success
    block, rather than added to :data:`StageFn`'s shared signature, so
    ``_run_natal_ready`` and the other four stage functions stay
    byte-for-byte unchanged.

    ``generator``/``vocabulary`` are threaded through to the stage function
    uniformly (Stories 4.6/5.3, :data:`StageFn`) -- only ``draft_ready``
    calls ``generator`` and only ``gate_passed`` calls ``vocabulary``, but
    the registry stays a plain ``{name: function}`` mapping rather than
    growing per-stage plumbing here.

    Idempotent by construction, not by re-checking output equality: a stage
    at or before ``run.stage`` in ``_STAGE_SEQUENCE`` is never called again,
    so polling a completed run is a no-op regardless of what
    ``natal_chart``/``config`` are passed. Resume-after-interruption still
    works because each stage persists before the next begins: the next poll
    picks up at the first incomplete stage and recomputes nothing already
    stored (AD-10). The stage's ``with_backoff`` call uses that stage's own
    override from :data:`_STAGE_BACKOFF_OVERRIDES` when one exists (Story
    4.8) -- ``draft_ready``'s Gemini attempts stay within the provider's
    10 requests-per-minute ceiling -- and the plain defaults otherwise.

    The ``with_backoff`` attempt runs the stage function inside its own
    ``session.begin_nested()`` SAVEPOINT (epic-4-retro item 23): a two-write
    stage (``_run_payload_ready``, ``_run_gate_passed``) that partially
    flushes and then fails has that partial flush rolled back to the
    savepoint, so the *next* ``with_backoff`` attempt -- and, after
    exhaustion, this function's own ``except`` handlers -- run on a clean
    session instead of dying on ``PendingRollbackError``. A transient
    second-write failure now gets a real retry within the same call.

    A unique-constraint ``IntegrityError`` from a concurrent ``advance()``
    for the same run (SQLite has no advisory lock; a future non-poll caller
    could reappear -- items 26/44) is handled separately from every other
    stage exception. It is intercepted *inside* the retried callable so
    ``with_backoff`` never retries it (a unique-constraint conflict never
    clears on retry, and on ``draft_ready`` a retry would spend another paid
    ``generator.generate()`` call plus ``with_backoff``'s 6 s / 12 s
    sleeps); this function then rolls back, ``session.refresh(run)``, and if
    ``run.stage`` has advanced past the current stage treats it as a
    completed stage (``return run``, no counter change, INFO log). Otherwise
    -- a genuine integrity bug, no concurrent advance -- it falls through to
    the same stage-failure path as any other exception (``stage_failure_count``
    increment, terminal at :data:`_MAX_STAGE_FAILURES`), still without a
    retry.

    A successful stage advance resets ``run.stage_failure_count`` to 0.
    When a stage's ``with_backoff`` call exhausts every attempt,
    ``run.stage`` is left unchanged (as before) but
    ``run.stage_failure_count`` is incremented; once it reaches
    :data:`_MAX_STAGE_FAILURES` *consecutive* exhaustions (across separate
    polls), ``run`` is marked terminally failed
    (``failed_at``/``failure_reason`` set) instead of being retried on every
    future poll forever -- a persistent rate limit or error now reaches a
    terminal state Francesco is shown, rather than an indefinite,
    ever-hammering silent stall. Either way ``run`` is returned exactly as
    far as it got.

    A run already marked ``failed_at`` short-circuits immediately: no lock is
    acquired, no stage function runs, no ``with_backoff`` call is made,
    ``run`` is returned unchanged.

    A :class:`core.errors.GateFailedError` from ``gate_passed`` is handled
    separately from every other stage exception (Story 5.4): it persists a
    failing ``StoredGateResult`` row (Story 5.6, ``regeneration_count`` at
    its pre-increment value, ``error.violations``, ``vocabulary.version``)
    before incrementing ``run.regeneration_count`` (never ``stage_failure_count``,
    left untouched) and, while that count is at or below
    :data:`_MAX_REGENERATIONS`, rewinds ``run.stage`` to ``payload_ready`` so
    the *next* poll re-runs ``draft_ready`` -- a genuinely new
    ``GeneratedDraft`` from the same stored Payload -- and then ``gate_passed``
    again on the poll after that. Once ``run.regeneration_count`` exceeds
    :data:`_MAX_REGENERATIONS`, ``run`` is marked terminally failed the same
    way a :data:`_MAX_STAGE_FAILURES` exhaustion is, except ``run.stage`` is
    left at ``draft_ready`` (never rewound) so the last, still-failing draft
    stays reachable rather than discarded. Either branch commits and returns
    immediately -- regeneration itself always happens on a subsequent poll,
    never within the same call that caught the failure.
    """
    if run.failed_at is not None:
        return run

    # Resolve the single next stage from the in-memory `run` *before* taking
    # the advisory lock: a poll on a completed run (`run.stage` is the last
    # named stage) or one whose next stage has no registered function yet
    # (`exported`, today) has nothing to do, so it must acquire no lock --
    # matching the `failed_at` fast-path above.
    next_index = _stage_index(run.stage) + 1
    if next_index >= len(_STAGE_SEQUENCE):
        # `run.stage` is already the last named stage (`gate_passed`) --
        # there is no next stage to run.
        return run

    stage_name = _STAGE_SEQUENCE[next_index]
    stage_fn = _STAGE_FUNCTIONS.get(stage_name)
    if stage_fn is None:
        # The next stage name has no registered function yet (`exported`,
        # today) -- stop cleanly, no commit.
        return run

    if not try_acquire_advance_lock(session, run.id):
        # A concurrent poll holds the transaction-scoped advisory lock and
        # is advancing this run one stage. Non-blocking by design (AD-20,
        # this module's Design Notes): roll our own empty transaction back,
        # re-read the row so the caller renders the freshest stage, and
        # return without running anything. Postgres releases the lock on the
        # winner's own commit/rollback.
        session.rollback()
        session.refresh(run)
        _logger.info(
            "advance lock held by a concurrent poll; returning current stage "
            "%s without advancing: %s",
            run.stage,
            run.id,
        )
        return run

    backoff_kwargs = _STAGE_BACKOFF_OVERRIDES.get(stage_name, {})

    #: Set by `_attempt` below when the stage's own flush raised a
    #: unique-constraint `IntegrityError` -- the fingerprint of a concurrent
    #: `advance()` (SQLite has no advisory lock; a future non-poll caller;
    #: items 26/44) having already written this stage's row. Holds the
    #: caught exception so the genuine-bug path can still log it.
    integrity_error: IntegrityError | None = None

    def _attempt(stage_fn: StageFn = stage_fn) -> None:
        # NOT a straight mirror of `place_cache.store_resolved_place`:
        # that helper wraps `begin_nested()` in `try/except
        # IntegrityError: pass` and swallows the conflict in place. Here
        # the SAVEPOINT shape is the same (item 23: a partial flush rolls
        # back to the savepoint, so the next `with_backoff` attempt runs
        # on a clean session), but a caught `IntegrityError` is surfaced
        # to `advance()`'s body via `integrity_error` for a benign-vs-
        # genuine classification -- it is deliberately NOT re-raised into
        # `with_backoff`'s retry: a unique-constraint conflict from a
        # concurrent `advance()` never clears on a retry, and letting it
        # ride `with_backoff` would burn up to `max_attempts` doomed
        # attempts -- for `draft_ready` that is three real
        # `generator.generate()` (Gemini) calls plus `time.sleep(6)` +
        # `time.sleep(12)` before the conflict is even classified. (The
        # "next attempt runs clean" reasoning for the SAVEPOINT itself
        # does not apply to `gate_passed`, which is `max_attempts=1`.)
        nonlocal integrity_error
        # Defensive reset: if a future change ever lets `with_backoff`
        # re-enter `_attempt` after a transient failure, a stale caught
        # conflict from an earlier attempt must not leak into the `else`
        # branch's benign-vs-genuine check.
        integrity_error = None
        try:
            with session.begin_nested():
                stage_fn(
                    session,
                    run,
                    natal_chart,
                    config,
                    ephemeris_identity,
                    sections_config,
                    generator,
                    vocabulary,
                )
        except IntegrityError as conflict:
            integrity_error = conflict

    try:
        with_backoff(_attempt, **backoff_kwargs)
    except GateFailedError as error:
        # `_run_gate_passed`'s pass-path attempt (`store_report` then
        # `store_gate_result`, each its own flush) may have partially
        # flushed and then failed before raising whatever exception
        # `with_backoff` ultimately exhausted on -- on a real database
        # that failed flush aborts the underlying transaction, so any
        # further statement on this session -- even reading `run.id`
        # back for the log line below -- would fail too, masking the
        # actual cause (epic-5-retro-item-39, re-prioritizing
        # epic-4-retro-item-23). Rolling back first, before touching
        # `run` at all, guarantees a clean transaction regardless of
        # what came before.
        session.rollback()
        # A pure Gate re-checking the same already-persisted draft fails
        # identically forever -- the generic stage-failure path below
        # would just retry that same draft until _MAX_STAGE_FAILURES,
        # never actually regenerating anything. Regeneration is a
        # distinct counter/path (Story 5.4): stage_failure_count is left
        # untouched here, exactly as the module's own Design Notes
        # require.
        _logger.exception(
            "gate_passed rejected the draft, regenerating: %s", run.id
        )
        try:
            store_gate_result(
                session,
                run=run,
                passed=False,
                regeneration_count=run.regeneration_count,
                vocabulary_version=vocabulary.version,
                vocabulary_content_hash=vocabulary.content_hash,
                violations=error.violations,
            )
        except Exception:
            # This write sits outside `with_backoff` by design (Story
            # 5.6, to avoid a duplicate row) -- so nothing else retries
            # it. Losing one gate_result row must never crash `advance()`
            # itself: the regeneration bookkeeping below still has to
            # run so the run keeps making progress. Roll back first --
            # mirroring both blocks above -- before touching `run` again
            # (even for this log line), so a real partial flush here
            # doesn't poison the commit that follows or the log call
            # itself.
            session.rollback()
            _logger.exception(
                "failed to persist a failing gate_result, continuing "
                "regeneration bookkeeping without it: %s",
                run.id,
            )
        run.regeneration_count += 1
        run.updated_at = datetime.now(UTC)
        if run.regeneration_count <= _MAX_REGENERATIONS:
            run.stage = "payload_ready"
            _logger.info(
                "report run rewound to payload_ready for regeneration "
                "attempt %s: %s",
                run.regeneration_count,
                run.id,
            )
        else:
            run.failed_at = run.updated_at
            run.failure_reason = (
                f"regeneration bound exhausted after {run.regeneration_count} "
                f"attempts: {error}"
            )
            _logger.error(
                "report run marked terminally failed: regeneration bound "
                "exhausted: %s",
                run.id,
            )
        session.add(run)
        session.commit()
        return run
    except Exception as error:
        # Mirrors the `GateFailedError` branch above: a stage function
        # that partially flushed before failing (e.g. `_run_gate_passed`'s
        # `store_report`+`store_gate_result` pair) can leave this
        # session's transaction aborted, which would make even reading
        # `run.id` back for the log line below fail too, taking the
        # whole `advance()` call down uncaught instead of leaving the run
        # simply un-advanced (epic-5-retro-item-39). Rolling back first,
        # before touching `run` at all, avoids that.
        session.rollback()
        _logger.exception("report run stage failed, left un-advanced: %s", run.id)
        run.stage_failure_count += 1
        run.updated_at = datetime.now(UTC)
        if run.stage_failure_count >= _MAX_STAGE_FAILURES:
            run.failed_at = run.updated_at
            run.failure_reason = (
                f"stage {stage_name!r} failed {run.stage_failure_count} consecutive "
                f"times: {error}"
            )
            _logger.error(
                "report run marked terminally failed at %s after %s consecutive "
                "failures: %s",
                stage_name,
                run.stage_failure_count,
                run.id,
            )
        session.add(run)
        session.commit()
        return run
    else:
        if integrity_error is not None:
            # `_attempt` caught a unique-constraint `IntegrityError` and
            # returned normally so `with_backoff` did not retry it. The
            # stage's `begin_nested()` already rolled its partial flush
            # back to the savepoint; roll the *outer* transaction back
            # too, before re-reading `run`, so the refresh below runs in
            # a fresh transaction and sees a concurrent commit under
            # READ COMMITTED or REPEATABLE READ alike.
            session.rollback()
            session.refresh(run)
            if _stage_index(run.stage) >= next_index:
                # A concurrent `advance()` already completed this stage and
                # advanced `run.stage`. Benign -- not a stage failure:
                # `stage_failure_count`/`regeneration_count`/`failed_at`
                # are all left exactly as the concurrent winner's
                # committed row (just refreshed) has them.
                _logger.info(
                    "stage %s already completed by a concurrent advance(); "
                    "run.stage is now %s: %s",
                    stage_name,
                    run.stage,
                    run.id,
                )
                return run
            # `run.stage` did not advance: this is a genuine integrity
            # bug, not a concurrent-stage race. Record it as a stage
            # failure exactly like the `except Exception` path above --
            # but still without a `with_backoff` retry (it never clears).
            # `_logger.error` (not `.exception`): this runs in the `else`
            # clause with no active exception handler; `exc_info` carries
            # the conflict caught back inside `_attempt`.
            _logger.error(
                "report run stage failed on a non-concurrent IntegrityError, "
                "left un-advanced: %s",
                run.id,
                exc_info=integrity_error,
            )
            run.stage_failure_count += 1
            run.updated_at = datetime.now(UTC)
            if run.stage_failure_count >= _MAX_STAGE_FAILURES:
                run.failed_at = run.updated_at
                run.failure_reason = (
                    f"stage {stage_name!r} failed {run.stage_failure_count} consecutive "
                    f"times: {integrity_error}"
                )
                _logger.error(
                    "report run marked terminally failed at %s after %s consecutive "
                    "failures: %s",
                    stage_name,
                    run.stage_failure_count,
                    run.id,
                )
            session.add(run)
            session.commit()
            return run

    if stage_name == "natal_ready":
        run.natal_chart_id = natal_chart_id
    run.stage = stage_name
    run.stage_failure_count = 0
    run.updated_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    _logger.info("report run advanced to %s: %s", stage_name, run.id)
    return run
