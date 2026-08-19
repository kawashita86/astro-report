"""``drive()``: advances one ``ReportRun`` through AD-10's six named stages,
one already-registered stage at a time, persisting each stage's output
before the next begins (Story 3.5).

**Why `drive()` is called from both the start POST and the poll GET, with no
background task or queue.** BUILD-ORDER.md's E5 explicitly rejects an
in-process background task ("run state lives only in memory, lost silently
on restart") and a blocking synchronous request ("a stall loses the whole
run"). Making `drive()` a cheap, idempotent, re-entrant function that any
request handler can call reduces the problem to "the next HTTP request in
either role continues the run" -- the browser's own poll cadence is the
drain, matching the architecture note "no queue infrastructure needed." See
``shell/http/routes/report_runs.py``.

**Why only `natal_ready`/`transits_ready` get real stage functions.**
BUILD-ORDER.md: "the runner introduced once two real stages exist." Payload
assembly is Story 3.6's job (``core/payload/`` does not exist yet);
registering a stage before its implementation exists would mean stubbing a
lie. `_STAGE_SEQUENCE` names all six stages for display/ordering;
`_STAGE_FUNCTIONS` only the two real ones -- `drive()` stops the moment it
reaches a name with no registered function.

**Why no live external call demonstrates the backoff.** Both registered
stages read local state (the already-persisted chart, the local ephemeris)
-- nothing rate-limited exists yet (that arrives with the Generator, Story
4.8, sized for its own 10 RPM ceiling). ``with_backoff``
(``shell/runner/backoff.py``) is proven here with an injected fake failing
stage function in tests; it becomes the same wrapper future stages reuse.

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

from sqlmodel import Session

from core.ephemeris.identity import EphemerisIdentity
from core.transits.aspects import find_transit_aspects
from core.transits.ingresses import find_ingresses
from core.transits.lunations import find_lunations
from core.transits.stations import find_stations
from core.types.chart import NatalChart
from core.types.computation import ComputationConfig
from core.types.transits import StandingRetrograde
from shell.adapters.postgres.client import Client
from shell.adapters.postgres.report_run import ReportRun
from shell.runner.backoff import with_backoff
from shell.runner.month import client_month_interval_utc

__all__ = ["drive"]

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

#: A stage function's uniform signature: every registered stage receives the
#: same context, whether or not it needs all of it, so the registry stays a
#: plain ``{name: function}`` mapping rather than growing per-stage plumbing
#: in ``drive()`` itself as more stages register.
StageFn = Callable[[Session, ReportRun, NatalChart, ComputationConfig, EphemerisIdentity], None]


def _run_natal_ready(
    session: Session,
    run: ReportRun,
    natal_chart: NatalChart,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
) -> None:
    """``natal_ready``: resolve ``run.month`` against ``run.client_id``'s
    local calendar into ``[month_start_utc, month_end_utc)``.

    The Natal Chart itself needs no computation here -- it is already
    stored and already deserialized into ``natal_chart`` by the caller
    (``shell/http/routes/report_runs.py``); this stage's whole job is the
    month-boundary resolution Stories 3.1-3.4 deferred.
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
) -> None:
    """``transits_ready``: call the four Story 3.1-3.4 scan functions across
    ``[run.month_start_utc, run.month_end_utc)`` -- read back from the row,
    never recomputed, so a process restart between stages loses nothing --
    and record every result, tagged by kind, into ``run.transit_events``.
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


#: Only the two stages this story implements -- Story 3.6+ registers the
#: rest, unchanged (see the module's Design Notes).
_STAGE_FUNCTIONS: dict[str, StageFn] = {
    "natal_ready": _run_natal_ready,
    "transits_ready": _run_transits_ready,
}


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


def drive(
    session: Session,
    run: ReportRun,
    *,
    natal_chart: NatalChart,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
) -> ReportRun:
    """Advance ``run`` through every stage in ``_STAGE_SEQUENCE`` that has a
    registered function in ``_STAGE_FUNCTIONS`` and that ``run.stage`` has
    not already passed, committing after each stage succeeds.

    Idempotent by construction, not by re-checking output equality: a stage
    at or before ``run.stage`` in ``_STAGE_SEQUENCE`` is never called again,
    so re-driving a completed run is a no-op regardless of what
    ``natal_chart``/``config`` are passed. Stops cleanly the moment it
    reaches a stage name with no registered function (Story 3.6+ registers
    the rest) -- and stops just as cleanly, without raising, if a stage's
    ``with_backoff`` call exhausts every attempt, leaving ``run.stage``
    unchanged for the next ``drive()`` call to retry. Either way ``run`` is
    returned exactly as far as it got.

    Called from both the start route and the poll route
    (``shell/http/routes/report_runs.py``): a stalled or interrupted run
    resumes on whichever request -- start or poll -- calls this next.
    """
    completed_index = _stage_index(run.stage)

    for index, stage_name in enumerate(_STAGE_SEQUENCE):
        if index <= completed_index:
            continue

        stage_fn = _STAGE_FUNCTIONS.get(stage_name)
        if stage_fn is None:
            break

        try:
            with_backoff(
                lambda stage_fn=stage_fn: stage_fn(
                    session, run, natal_chart, config, ephemeris_identity
                )
            )
        except Exception:
            _logger.exception("report run stage failed, left un-advanced: %s", run.id)
            break

        run.stage = stage_name
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        _logger.info("report run advanced to %s: %s", stage_name, run.id)
        completed_index = index

    return run
