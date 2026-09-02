"""``POST /clients/{client_id}/report-runs`` (start) and
``GET /report-runs/{run_id}`` (HTMX poll) -- Francesco starts a month's
computation and watches it advance one stage at a time (Story 3.5, reshaped
for AD-20 by Story 3.10).

The start route only creates the ``ReportRun`` row, commits and redirects to
the poll view -- it runs no stage, so it returns immediately. Every stage is
driven from the poll route: each ``GET`` calls
``shell/runner/driver.py::advance()`` once, which moves the run forward by
at most one stage and returns, so the first stage runs on the first poll and
a poll never blocks on more than its own single stage (one external
Generator call plus bounded backoff, at ``draft_ready``). Concurrent polls
for one run are single-flighted by a Postgres advisory lock inside
``advance()``. No background task, no queue: see ``shell/runner/driver.py``'s
Design Notes.

Authenticated by default: nothing here is named in
``shell.http.auth.ALLOWLIST``, so ``AuthMiddleware`` guards both routes
before a request ever reaches this module, mirroring
``shell/http/routes/chart.py``/``shell/http/routes/clients.py``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace as dataclasses_replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from core.gate.run import run_gate
from core.types.generation import Sentence
from shell.adapters.gemini.generator import GeminiGenerator
from shell.adapters.local.generator import RecordedResponseGenerator
from shell.adapters.postgres.client import (
    Client,
    current_chart_for_client,
    deserialize_natal_chart,
)
from shell.adapters.postgres.export_record import (
    ExportRecord,
    record_send_disposition,
    store_export_record,
)
from shell.adapters.postgres.gate_result import StoredGateResult, store_gate_result
from shell.adapters.postgres.gate_violation_review import (
    GateViolationReview,
    store_gate_violation_review,
)
from shell.adapters.postgres.report import Report, store_report
from shell.adapters.postgres.report_draft import (
    ReportDraft,
    next_report_draft_attempt,
    store_report_draft,
)
from shell.adapters.postgres.report_payload import ReportPayload
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.weasyprint.render import html_to_pdf
from shell.config import Environment
from shell.http.app import get_session
from shell.http.draft_view import (
    LIST_SECTION_NAMES,
    SECTION_ORDER,
    SECTION_TITLES,
    deserialize_generated_draft,
    render_draft,
)
from shell.http.flash import _flash_context_processor, set_flash
from shell.http.payload_view import FIELD_TITLES, localize_payload
from shell.http.report_markdown import render_report_markdown
from shell.http.stage_view import build_stage_track, stage_caption, violation_kind_label
from shell.ports.generator import Generator
from shell.runner.driver import advance

__all__ = ["get_generator", "router"]

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(
    directory=_TEMPLATES_DIR, context_processors=[_flash_context_processor]
)

#: "YYYY-MM", zero-padded -- the one shape ``shell/runner/month.py``'s
#: ``client_month_interval_utc`` is contracted to accept. Checked here so a
#: malformed month is a plain 422 at submission time, never handed to
#: ``advance()`` where ``with_backoff`` would retry a permanent input error
#: as if it were a transient one and quietly leave the run un-advanced.
_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

#: The only two values ``record_send_disposition`` (and the route below)
#: ever accept -- Story 6.3's Boundaries forbid a third value or free text.
#: Paired with the button label ``report.html`` renders for each, in the
#: fixed order Francesco sees them.
DISPOSITION_CHOICES: tuple[tuple[str, str], ...] = (
    ("as_generated", "Inviato come generato"),
    ("edited", "Inviato, con modifiche"),
)
_DISPOSITION_VALUES = {value for value, _label in DISPOSITION_CHOICES}

#: How close a failing ``StoredGateResult.created_at`` must sit to
#: ``run.failed_at`` -- in *either* direction -- for
#: ``_current_cycle_gate_failure`` to treat it as the check that actually
#: produced *this* failure, rather than a stale row from an earlier,
#: ``/regenerate``-superseded cycle. A real Gate check and the terminal
#: ``failed_at`` it produces are written inside the same ``advance()`` call
#: (``shell/runner/driver.py``'s ``except GateFailedError`` block writes the
#: ``StoredGateResult`` row first, then sets ``failed_at`` once
#: ``regeneration_count`` exceeds the bound) -- a sub-second gap, well inside
#: this window; the absolute value admits that same sub-second gap when a
#: caller instead constructs ``failed_at`` before the row (as this module's
#: own tests do). A stale row is always separated from a *later* terminal
#: ``failed_at`` by well over this window: ``regenerate_report_run``'s ``303``
#: redirects to ``/report-runs/{run_id}`` (``poll_report_run``), so the first
#: ``advance()`` after a rewind fires immediately on that redirect's own page
#: load, not after a 2s poll wait -- but a fresh non-Gate terminal failure
#: still cannot land inside this window, because ``_MAX_STAGE_FAILURES``
#: (``shell/runner/driver.py``, 5) requires 5 *consecutive* stage-failure
#: exhaustions across separate ``advance()`` calls -- each one only reached on
#: a subsequent, ~2s-apart poll -- before a run is marked terminally failed
#: for a generic reason. The real minimum margin is therefore several poll
#: intervals (well over 2s), not "one poll interval" (this story's Design
#: Notes, review-loop 1; corrected by review-loop 2).
_GATE_RESULT_CORRELATION_WINDOW = timedelta(seconds=2)


#: Kept as a module-local alias (rather than calling
#: ``current_chart_for_client`` at each call site) purely so a reader
#: scanning this file doesn't need to jump to the adapter module to see
#: which chart "current" means here -- the two call sites below are the
#: whole of its usage.
_current_chart = current_chart_for_client


def _current_cycle_gate_failure(session: Session, run: ReportRun) -> StoredGateResult | None:
    """The failing ``StoredGateResult`` that actually caused ``run``'s
    *current* terminal failure, or ``None`` if this run's current failure was
    not a Gate failure at all (Story 9.5, review-loop 1).

    Replaces an existence-only "has a failing ``StoredGateResult`` ever been
    written for this ``run_id``" check, which review-loop 0's blind-hunter
    review caught as insufficient: once ``POST …/regenerate`` can rewind a
    Gate-failed run and let it fail again for an unrelated reason, "this run
    failed the Gate at some point in its history" and "the Gate produced
    *this* ``failed_at``" are different questions, and only the latter is
    safe to gate ``gate_failed``/the Rigenera route on.

    Returns ``None`` immediately if ``run.failed_at is None`` -- a running or
    passed run was never asked this question by any caller, but the guard is
    cheap and makes the function total. Otherwise runs the same query
    ``view_report_draft`` already ran pre-Story-9.5 (latest failing row by
    ``created_at`` descending -- Story 5.8 amendment, see below) and
    additionally requires ``result.created_at`` to fall within
    :data:`_GATE_RESULT_CORRELATION_WINDOW` of ``run.failed_at`` -- see that
    constant's own comment for why this window reliably separates "the check
    that just failed" from a stale row left behind by an earlier,
    since-superseded regeneration cycle.

    Ordered by ``created_at`` descending, not ``regeneration_count``
    descending (Story 5.8 amendment): once a hand-correction can mint a new
    failing ``StoredGateResult`` row without incrementing
    ``run.regeneration_count``, two failing rows for the same run can share
    one ``regeneration_count`` value, so that column no longer reliably picks
    out the newest row -- ``created_at`` always does.
    """
    if run.failed_at is None:
        return None
    result = session.exec(
        select(StoredGateResult)
        .where(StoredGateResult.report_run_id == run.id)
        .where(StoredGateResult.passed.is_(False))
        .order_by(StoredGateResult.created_at.desc())
    ).first()
    if result is None:
        return None
    delta = run.failed_at - result.created_at
    if abs(delta) > _GATE_RESULT_CORRELATION_WINDOW:
        return None
    return result


def _latest_export_record(session: Session, run_id: UUID) -> ExportRecord | None:
    """The most recent ``ExportRecord`` for ``run_id``'s ``Report`` (by
    ``created_at`` descending, ``id`` descending as a deterministic
    tiebreaker for two rows created within the same timestamp resolution),
    or ``None`` if no ``Report`` row exists for ``run_id`` or that ``Report``
    has never been exported -- shared by ``view_report`` (to show the
    disposition UI) and ``record_export_disposition`` (to 404 before ever
    calling ``record_send_disposition``)."""
    stored_report = session.exec(select(Report).where(Report.report_run_id == run_id)).first()
    if stored_report is None:
        return None
    return session.exec(
        select(ExportRecord)
        .where(ExportRecord.report_id == stored_report.id)
        .order_by(ExportRecord.created_at.desc(), ExportRecord.id.desc())
    ).first()


class _PassedReportBundle(NamedTuple):
    """Every row ``view_report`` (Story 6.1) and ``download_report_pdf``
    (Story 6.2) both load behind a Gate-passed ``Report`` row, plus the
    rendered draft -- see :func:`_load_passed_report_bundle`."""

    report: Report
    run: ReportRun
    stored_draft: ReportDraft
    stored_payload: ReportPayload
    client: Client
    rendered: dict[str, Any]


def _render_stored_draft(
    stored_draft: ReportDraft, stored_payload: ReportPayload, client: Client
) -> dict[str, Any]:
    """Deserialize ``stored_draft`` and render it against its frozen Payload
    -- the two-line tail ``view_report_draft`` / ``view_report`` /
    ``download_report_pdf`` all share verbatim (epic-6-retro-item-51)."""
    draft = deserialize_generated_draft(stored_draft.draft)
    return render_draft(draft, stored_payload.payload, iana_zone=client.iana_zone)


def _load_passed_report_bundle(session: Session, run_id: UUID) -> _PassedReportBundle:
    """The ``Report`` -> ``ReportRun`` -> ``ReportDraft`` -> ``ReportPayload``
    -> ``Client`` + ``render_draft`` block ``view_report`` and
    ``download_report_pdf`` load identically (epic-6-retro-item-51).

    404s only on the ``Report`` row's absence -- "no such run" or "its Gate
    hasn't passed yet", mirroring ``shell/export.py::export_report()``'s
    boundary. Once a ``Report`` exists, any row it implies being missing is a
    ``RuntimeError`` (a data-integrity bug, not a not-ready state), with the
    same message shapes both routes used before.
    """
    stored_report = session.exec(select(Report).where(Report.report_run_id == run_id)).first()
    if stored_report is None:
        raise HTTPException(status_code=404)

    run = session.get(ReportRun, run_id)
    if run is None:
        raise RuntimeError(f"Report {stored_report.id} references a missing ReportRun.")

    stored_draft = session.exec(
        select(ReportDraft)
        .where(ReportDraft.report_run_id == run_id)
        .order_by(ReportDraft.attempt.desc())
    ).first()
    if stored_draft is None:
        raise RuntimeError(f"Report {stored_report.id} has no matching ReportDraft.")

    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run_id)
    ).first()
    if stored_payload is None:
        raise RuntimeError(f"Report {stored_report.id} has no matching ReportPayload.")

    client = session.get(Client, stored_draft.client_id)
    if client is None:
        raise RuntimeError(f"Report {stored_report.id} references a missing Client.")

    return _PassedReportBundle(
        report=stored_report,
        run=run,
        stored_draft=stored_draft,
        stored_payload=stored_payload,
        client=client,
        rendered=_render_stored_draft(stored_draft, stored_payload, client),
    )


def get_generator(request: Request) -> Generator:
    """The ``Generator`` this route calls at the ``draft_ready`` stage.

    A dependency of its own, not a bare call inline in the handler, so tests
    can substitute a fake without a real network call or a real Gemini API
    key -- mirrors ``get_geocoder()`` (``shell/http/routes/clients.py``).
    Constructed per-request, never cached on ``app.state``: this avoids
    constructing a real ``genai.Client`` for every one of the many HTTP
    tests that build the app but never touch report runs (this story's
    Design Notes).

    Under ``Environment.LOCAL`` this returns ``RecordedResponseGenerator``
    instead of a real ``GeminiGenerator`` (Story 4.9) -- mirrors the
    ``settings.environment is Environment.LOCAL`` idiom ``shell/http/app.py``
    already uses twice, so ``docker compose up`` against a local Postgres
    never spends real Gemini quota. Production behavior is unchanged.
    """
    if request.app.state.settings.environment is Environment.LOCAL:
        return RecordedResponseGenerator()
    return GeminiGenerator(request.app.state.settings.gemini_api_key)


def _advance_run(
    request: Request, session: Session, run: ReportRun, client: Client, generator: Generator
) -> ReportRun:
    """Deserialize ``client``'s current stored chart and call ``advance()``
    once -- used only by ``poll_report_run`` (AD-20), so each poll moves the
    run forward by at most one stage."""
    stored_chart = _current_chart(session, client.id)
    if stored_chart is None:
        raise HTTPException(status_code=404)
    natal_chart = deserialize_natal_chart(stored_chart)
    return advance(
        session,
        run,
        natal_chart=natal_chart,
        natal_chart_id=stored_chart.id,
        config=request.app.state.computation_config,
        ephemeris_identity=request.app.state.ephemeris_identity,
        sections_config=request.app.state.sections_config,
        generator=generator,
        vocabulary=request.app.state.gate_vocabulary,
    )


@router.post("/clients/{client_id}/report-runs", include_in_schema=False)
def start_report_run(
    client_id: UUID,
    request: Request,
    month: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404)

    if not _MONTH_PATTERN.match(month):
        raise HTTPException(status_code=422, detail="month must be 'YYYY-MM'.")

    # AD-20 (Story 3.10): the start route runs no stage -- it only creates
    # the row, commits and redirects, so it returns immediately; the first
    # stage runs on the first poll. The stored chart is still checked here so
    # starting a run for a Client with no chart is a plain 404 at submission
    # time, not a failure the operator only discovers on the first poll.
    if _current_chart(session, client_id) is None:
        raise HTTPException(status_code=404)

    now = datetime.now(UTC)
    run = ReportRun(client_id=client_id, month=month, created_at=now, updated_at=now)
    session.add(run)
    session.commit()

    response = RedirectResponse(f"/report-runs/{run.id}", status_code=303)
    set_flash(
        response,
        "success",
        "Report avviato.",
        environment=request.app.state.settings.environment,
    )
    return response


@router.get("/report-runs/{run_id}", include_in_schema=False)
def poll_report_run(
    run_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    generator: Generator = Depends(get_generator),
) -> Response:
    run = session.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404)

    client = session.get(Client, run.client_id)
    if client is None:
        raise RuntimeError(f"ReportRun {run.id} references a missing Client.")

    _advance_run(request, session, run, client, generator)

    failed = run.failed_at is not None
    gate_failed = _current_cycle_gate_failure(session, run) is not None
    context = {
        "run": run,
        "client": client,
        "stage_track": build_stage_track(run.stage, failed=failed, gate_failed=gate_failed),
        "stage_caption": stage_caption(
            run.stage,
            failed=failed,
            gate_failed=gate_failed,
            failure_reason=run.failure_reason,
        ),
        "gate_failed": gate_failed,
        "poll_active": run.failed_at is None and run.stage not in ("gate_passed", "exported"),
    }
    return _templates.TemplateResponse(request, "report_run_poll.html", context)


@router.post("/report-runs/{run_id}/regenerate", include_in_schema=False)
def regenerate_report_run(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Rewind a Gate-failed run to ``payload_ready`` for one more real
    regeneration attempt (Story 9.5) -- a shell-only recovery route, not a
    stage advance: it never calls ``advance()`` itself, mirroring
    ``start_report_run``'s own "returns immediately without advancing" shape.
    Unlike ``start_report_run`` (whose redirect target, the Client's Reports
    tab, does not poll), this route's ``303`` redirects straight to
    ``/report-runs/{run_id}`` -- ``poll_report_run`` -- so the first
    ``advance()`` for the rewound run actually fires immediately, on that
    redirect's own page load, not on some later timed poll.
    ``run.regeneration_count`` is left untouched -- the driver's own
    ``except GateFailedError`` branch (``shell/runner/driver.py::advance()``)
    is still the only place that counter ever moves, on the *next* Gate check
    this rewind lets run.

    404s unless ``run.failed_at is not None`` **and**
    ``_current_cycle_gate_failure(session, run) is not None`` -- not the old
    "a failing ``StoredGateResult`` has ever existed for this run" check
    (review-loop 1): that weaker guard would let a direct ``POST`` regenerate
    a run whose *current* failure is not a Gate failure at all, even though
    the UI never shows the Rigenera button for one (``report_draft.html``
    only renders the form inside the ``{% if violations %}`` branch, which
    the same current-cycle check gates). Mirrors every other "wrong state /
    no such run" branch in this module by collapsing to a plain 404 (this
    story's Design Notes: "why a wrong-state 404, not 409").
    """
    run = session.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404)
    if run.failed_at is None or _current_cycle_gate_failure(session, run) is None:
        raise HTTPException(status_code=404)

    run.failed_at = None
    run.failure_reason = None
    run.stage = "payload_ready"
    run.updated_at = datetime.now(UTC)
    session.add(run)
    session.commit()

    response = RedirectResponse(f"/report-runs/{run_id}", status_code=303)
    set_flash(
        response,
        "success",
        "Rigenerazione avviata.",
        environment=request.app.state.settings.environment,
    )
    return response


def _close_run_via_accepted_violations(
    session: Session,
    run: ReportRun,
    stored_gate_result: StoredGateResult,
    violations: list[dict[str, Any]],
    *,
    stored_draft: ReportDraft | None = None,
    stored_payload: ReportPayload | None = None,
) -> bool:
    """Close ``run`` via accepted exceptions once every violation on
    ``stored_gate_result`` has a ``GateViolationReview`` row -- Story 5.7's
    own closing block, extracted (this story) so Story 5.8's hand-correct
    -and-recheck route (below) can trigger the exact same completion write
    when carrying forward acceptances leaves nothing open, without
    duplicating the read/write shape.

    Returns ``False`` immediately, writing nothing, when fewer
    ``GateViolationReview`` rows exist for ``stored_gate_result.id`` than
    ``len(violations)`` -- the caller's own accept/carry-forward action left
    at least one violation unresolved, so this is not (yet) a completion.
    Queried fresh from the database rather than trusting a caller-supplied
    count, so both call sites below share one source of truth for "is this
    result now fully reviewed."

    Also returns ``False``, writing nothing, when ``stored_gate_result`` is
    no longer ``run``'s *current* failing result (code-review fix,
    2026-09-02): a concurrent hand-correction (``correct_gate_violation``
    below) can mint a newer failing ``StoredGateResult`` for the same run
    between a caller reading ``stored_gate_result`` and this function
    actually closing against it, which would otherwise let a stale result
    get closed instead of the true current one. Re-checking
    ``_current_cycle_gate_failure`` here, right before the write, closes that
    window; the review row(s) already written against the stale result stay
    valid regardless (they are never deleted), and whichever request is
    actually working against the true current result closes it correctly on
    its own, later.

    Once every violation has a review row against the true current result,
    reads ``ReportDraft``/``ReportPayload`` back -- unless the caller already
    has them (``stored_draft``/``stored_payload``, an optimization
    ``correct_gate_violation`` uses to avoid re-querying rows it just fetched
    itself) -- and writes the closing ``Report`` row exactly like
    ``driver.py::_run_gate_passed`` does on a clean pass -- ``style_guide_version``/
    ``payload_schema_version`` read off the latest ``ReportDraft``/
    ``ReportPayload``, no new Gate check ever run (``run_gate()``/
    ``GateResult``/``StoredGateResult`` stay untouched). ``run.failed_at``/
    ``failure_reason`` are cleared and ``run.stage`` advances to
    ``gate_passed`` on that same write, mirroring
    ``regenerate_report_run``'s own state-transition shape.

    ``Report.report_run_id`` is unique at the DB level, so two
    near-simultaneous closes can't create two ``Report`` rows -- but without
    handling it here, the loser's commit would raise an unhandled
    ``IntegrityError`` and surface as a raw 500. Caught below, rolled back,
    and treated as "someone else just closed this run": ``True`` is returned
    either way, since ``run`` ends up closed regardless of which caller's
    write actually landed.
    """
    reviewed_count = session.exec(
        select(func.count())
        .select_from(GateViolationReview)
        .where(GateViolationReview.gate_result_id == stored_gate_result.id)
    ).one()
    if reviewed_count < len(violations):
        return False

    current = _current_cycle_gate_failure(session, run)
    if current is None or current.id != stored_gate_result.id:
        # A concurrent hand-correction has already superseded
        # `stored_gate_result` with a newer failing result (or the run is no
        # longer in a Gate-failed state at all) -- never close against a
        # stale result.
        return False

    if stored_draft is None:
        stored_draft = session.exec(
            select(ReportDraft)
            .where(ReportDraft.report_run_id == run.id)
            .order_by(ReportDraft.attempt.desc())
        ).first()
        if stored_draft is None:
            raise RuntimeError(f"ReportRun {run.id} has a Gate failure but no ReportDraft.")
    if stored_payload is None:
        stored_payload = session.exec(
            select(ReportPayload).where(ReportPayload.report_run_id == run.id)
        ).first()
        if stored_payload is None:
            raise RuntimeError(f"ReportRun {run.id} has a Gate failure but no ReportPayload.")

    try:
        store_report(
            session,
            run=run,
            style_guide_version=stored_draft.style_guide_version,
            payload_schema_version=stored_payload.schema_version,
            gate_vocabulary_version=stored_gate_result.vocabulary_version,
            gate_vocabulary_content_hash=stored_gate_result.vocabulary_content_hash,
            accepted_violation_count=len(violations),
            closing_gate_result_id=stored_gate_result.id,
        )
    except IntegrityError:
        # A concurrent closer already wrote this run's Report row first
        # (`Report.report_run_id` is unique) -- roll back and give this
        # caller the same outcome the winner got, rather than a raw 500.
        session.rollback()
    else:
        run.failed_at = None
        run.failure_reason = None
        run.stage = "gate_passed"
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()
    return True


@router.post(
    "/report-runs/{run_id}/violations/{violation_index}/accept", include_in_schema=False
)
def accept_gate_violation(
    run_id: UUID,
    violation_index: int,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    """Accept one violation on ``run_id``'s current failing
    ``StoredGateResult`` after Francesco has reviewed it (Story 5.7) -- a
    shell-only review decision, append-only, never a fabricated Gate
    re-check: ``core/gate/run.py::run_gate()`` is never called here.

    404s unless ``_current_cycle_gate_failure(session, run)`` is not
    ``None`` -- the exact same "current failing result" guard
    ``regenerate_report_run`` uses, mirroring how ``report_draft.html``
    only ever renders the Accetta form inside that same branch -- **and**
    ``violation_index`` is in range of that result's ``violations``. Covers
    both "no such run" and "already closed" (``run.failed_at is None``,
    whether via a clean pass, an earlier accept-closure, or any future
    route): ``_current_cycle_gate_failure`` returns ``None`` immediately
    once ``failed_at`` is ``None`` (this story's I/O & Edge-Case Matrix).

    Accepting an already-accepted index is a no-op -- idempotent
    double-submit, not an error and not a second row (this story's
    Boundaries): the existing reviewed indices are read back first, and
    ``store_gate_violation_review`` is only called when ``violation_index``
    is not already among them. This read-then-write check is also backed by
    a DB-level unique index on ``(gate_result_id, violation_index)``
    (``migrations/versions/0023_gate_violation_review.py``, review-loop
    fix): two near-simultaneous submits of the same index could otherwise
    both pass the in-memory check and each attempt to insert before either
    commits. The loser's insert raises ``IntegrityError`` once the winner
    commits -- caught below, rolled back, and treated exactly like a plain
    double-submit (re-read the now-current reviewed indices and carry on)
    rather than surfacing a raw 500.

    Once every violation on the current failing result has a review row
    (this accept made the count equal ``len(violations)``),
    ``_close_run_via_accepted_violations`` (Story 5.8 extraction, defined
    above) writes the closing ``Report`` row immediately, in this same
    request, clears ``run.failed_at``/``failure_reason`` and advances
    ``run.stage`` to ``gate_passed`` -- see that function's own docstring for
    exactly what it reads/writes and how it handles a concurrent closer.

    The redirect target differs by outcome (this story's Design Notes): the
    closing accept redirects to the poll page (``/report-runs/{run_id}``),
    exactly like ``regenerate_report_run``, since only the closing accept
    actually changes ``failed_at``/``stage``. An accept that leaves
    violations still open redirects back to the draft page
    (``/report-runs/{run_id}/draft``) instead -- the poll page would just
    show the still-failed state, forcing an extra click back to the panel to
    accept the next one.
    """
    run = session.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404)

    stored_gate_result = _current_cycle_gate_failure(session, run)
    if stored_gate_result is None:
        raise HTTPException(status_code=404)

    violations = stored_gate_result.violations
    if violation_index < 0 or violation_index >= len(violations):
        raise HTTPException(status_code=404)

    def _reviewed_indices() -> set[int]:
        return set(
            session.exec(
                select(GateViolationReview.violation_index).where(
                    GateViolationReview.gate_result_id == stored_gate_result.id
                )
            ).all()
        )

    reviewed_indices = _reviewed_indices()

    if violation_index not in reviewed_indices:
        violation = violations[violation_index]
        try:
            store_gate_violation_review(
                session,
                run=run,
                gate_result=stored_gate_result,
                violation_index=violation_index,
                kind=violation["kind"],
                section=violation["section"],
                sentence=violation["sentence"],
                entry_ids=violation["entry_ids"],
                detail=violation["detail"],
            )
        except IntegrityError:
            # A concurrent request for this exact index committed first --
            # the unique index on (gate_result_id, violation_index) caught
            # what the in-memory check above raced past. Roll back (a
            # failed flush poisons the transaction) so the session is clean
            # again -- `_close_run_via_accepted_violations` below re-reads
            # the reviewed count fresh from the database, so this is a
            # genuine double-submit from here on without needing this
            # function to re-read anything itself.
            session.rollback()

    if not _close_run_via_accepted_violations(session, run, stored_gate_result, violations):
        session.commit()
        response = RedirectResponse(f"/report-runs/{run_id}/draft", status_code=303)
        set_flash(
            response,
            "success",
            "Violazione accettata.",
            environment=request.app.state.settings.environment,
        )
        return response

    response = RedirectResponse(f"/report-runs/{run_id}", status_code=303)
    set_flash(
        response,
        "success",
        "Violazione accettata: verifica completata con eccezioni.",
        environment=request.app.state.settings.environment,
    )
    return response


@router.post(
    "/report-runs/{run_id}/violations/{violation_index}/correct", include_in_schema=False
)
def correct_gate_violation(
    run_id: UUID,
    violation_index: int,
    request: Request,
    sentence_text: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    """Hand-correct one flagged sentence on ``run_id``'s current failing
    ``StoredGateResult`` and re-check only the Gate (Story 5.8) -- a
    shell-only edit: only ``sentence_text`` changes, every other sentence
    (including the corrected sentence's own citations) carries over
    unchanged, and the recheck calls the exact same pure
    ``core/gate/run.py::run_gate()`` Story 5.2/5.4/Story 5.7's accept route
    already use -- never a model call, never new Gate logic.

    404s on the exact same guards ``accept_gate_violation`` uses: no such
    run, no current-cycle Gate failure (``_current_cycle_gate_failure``,
    which also covers "already closed"), or ``violation_index`` out of range
    of that result's ``violations``. Further, Story 5.8-specific 404s cover:
    a violation whose own ``sentence_index`` is missing entirely (a
    ``StoredGateResult`` row written before this story shipped, code-review
    fix -- ``violation.get("sentence_index")`` returning ``None`` is never
    silently defaulted to ``0``, which could otherwise rewrite an unrelated
    sentence); a ``section`` that does not resolve on the deserialized draft
    (also code-review fix, an impossible state from a real ``run_gate()``
    violation but not from a corrupted/hand-built row); and a *stale* index
    that is in range of the violations list but whose ``sentence_index`` no
    longer resolves against the latest ``ReportDraft`` -- caught as
    ``IndexError`` when indexing into the corrected Section's sentence tuple.

    A blank or whitespace-only ``sentence_text`` is rejected before anything
    is read or written (code-review fix): persisting it would produce a
    ``Sentence`` with no closed-vocabulary token, which ``is_claim()`` would
    then never flag, silently deleting that sentence's content from Gate
    scrutiny -- and, if it was the run's last open violation, closing the
    run as a genuine clean pass with content actually missing. Redirects to
    the draft page with a "danger" flash instead, mirroring the
    concurrent-mint "try again" redirect below.

    Never touches or is bounded by ``run.regeneration_count`` (this story's
    Boundaries, mirroring Story 5.7's accept route): the new ``ReportDraft``
    is tagged via ``next_report_draft_attempt(session, run.id)`` -- a plain
    count of existing rows, the same source ``shell/runner/driver.py``'s
    ``_run_draft_ready`` now uses -- not ``run.regeneration_count``, and
    ``store_gate_result`` below still records ``run.regeneration_count`` at
    its current, un-incremented value purely for traceability (mirroring
    every other ``store_gate_result`` call site), never advancing it.

    A concurrent request minting the same next ``attempt`` (e.g. a
    simultaneous Rigenera) loses at ``store_report_draft``'s own unique
    ``(report_run_id, attempt)`` index: caught as ``IntegrityError``, rolled
    back, and redirected back to the draft page with a "try again" flash --
    never a raw 500 (this story's I/O & Edge-Case Matrix).

    Once the corrected draft is persisted, ``run_gate()`` re-checks it
    against the same stored Payload and a new ``StoredGateResult`` is
    persisted (append-only, exactly like an automatic regeneration's pair --
    never updating or replacing the prior attempt). Every
    ``GateViolationReview`` already recorded against the *old* failing result
    is then matched to the *new* result's violations by
    ``(kind, section, sentence, entry_ids, detail)`` -- byte-for-byte content,
    not list position (this story's Design Notes) -- and carried forward
    automatically as a new review row against the new result, so Francesco is
    never asked to re-accept a violation the edit did not touch. Matching
    uses a ``collections.Counter`` over the old reviewed rows' own keys,
    consumed one-for-one as each match carries forward (code-review fix):
    two violations can share identical content, and a plain set membership
    check would double-accept an unreviewed twin of an accepted one, rather
    than carrying forward at most as many duplicate-content acceptances as
    were actually reviewed.

    The correction itself -- the new ``ReportDraft``, the new
    ``StoredGateResult``, and any carried-forward reviews -- is committed
    immediately after that carry-forward step, before branching on the
    outcome (code-review fix): every branch below performs its own
    subsequent write, and if that write hits a concurrent-writer
    ``IntegrityError`` and rolls back (``_close_run_via_accepted_violations``'s
    own closing-``Report`` attempt), that rollback must only ever undo its
    own write, never discard the correction this request already made.

    On a genuine pass (``result.passed``), a normal ``Report`` row is written
    -- no ``accepted_violation_count``/``closing_gate_result_id`` -- exactly
    like an automatic Gate pass, ``run.stage`` advances to ``gate_passed``,
    and the response redirects to the poll page. Otherwise,
    ``_close_run_via_accepted_violations`` (shared with the accept route
    above, passed this route's own already-fetched ``stored_new_draft``/
    ``stored_payload`` to avoid re-querying them) is tried against the new
    result and its carried-forward reviews: if it closes the run (every
    remaining violation was already accepted, and the new result is still
    ``run``'s true current one -- see that function's own docstring for the
    concurrent-correction guard), same poll-page redirect; if violations
    remain open, ``run.updated_at`` is bumped and the response redirects back
    to the draft page instead, where the remaining cards -- re-numbered
    against the new result -- each still offer Accetta and Modifica e
    ricontrolla.
    """
    run = session.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404)

    stored_gate_result = _current_cycle_gate_failure(session, run)
    if stored_gate_result is None:
        raise HTTPException(status_code=404)

    violations = stored_gate_result.violations
    if violation_index < 0 or violation_index >= len(violations):
        raise HTTPException(status_code=404)

    if not sentence_text.strip():
        # A blank/whitespace-only submission would persist as an empty
        # Sentence -- since empty text contains no closed-vocabulary token,
        # `is_claim()` would stop flagging it entirely, silently deleting
        # this sentence's content from Gate scrutiny (code-review fix,
        # 2026-09-02). Write nothing, redirect back to the draft page the
        # same way a concurrent-mint conflict below does.
        response = RedirectResponse(f"/report-runs/{run_id}/draft", status_code=303)
        set_flash(
            response,
            "danger",
            "Il testo non può essere vuoto.",
            environment=request.app.state.settings.environment,
        )
        return response

    violation = violations[violation_index]
    section = violation["section"]
    sentence_index = violation.get("sentence_index")
    if sentence_index is None:
        # A `StoredGateResult` row written before this story shipped has no
        # `"sentence_index"` key at all -- defaulting to `0` would risk
        # silently rewriting an unrelated sentence at that position instead
        # of the real one (code-review fix, 2026-09-02). Treat it the same
        # as any other "no longer resolvable" state: a 404, never a guess.
        raise HTTPException(status_code=404)

    stored_draft = session.exec(
        select(ReportDraft)
        .where(ReportDraft.report_run_id == run.id)
        .order_by(ReportDraft.attempt.desc())
    ).first()
    if stored_draft is None:
        raise RuntimeError(f"ReportRun {run.id} has a Gate failure but no ReportDraft.")
    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run.id)
    ).first()
    if stored_payload is None:
        raise RuntimeError(f"ReportRun {run.id} has a Gate failure but no ReportPayload.")

    draft = deserialize_generated_draft(stored_draft.draft)
    sentences = getattr(draft, section, None)
    if sentences is None:
        # An unresolvable `section` (impossible from a `run_gate()`-produced
        # violation, but not from a hand-built or corrupted stored row) --
        # 404, never an unguarded `AttributeError` (code-review fix,
        # 2026-09-02).
        raise HTTPException(status_code=404)
    try:
        old_sentence = sentences[sentence_index]
    except IndexError:
        # The flagged violation's own `sentence_index` no longer resolves
        # against the latest draft -- a stale index, the same class of "no
        # longer applies" state `accept_gate_violation`'s range check
        # guards against for `violation_index` itself.
        raise HTTPException(status_code=404) from None

    corrected_sentence = Sentence(text=sentence_text, entry_ids=old_sentence.entry_ids)
    corrected_sentences = tuple(
        corrected_sentence if index == sentence_index else existing
        for index, existing in enumerate(sentences)
    )
    corrected_draft = dataclasses_replace(draft, **{section: corrected_sentences})

    try:
        stored_new_draft = store_report_draft(
            session,
            run=run,
            style_guide_version=stored_draft.style_guide_version,
            sections_config_version=stored_draft.sections_config_version,
            draft=corrected_draft,
            attempt=next_report_draft_attempt(session, run.id),
        )
    except IntegrityError:
        # A concurrent request (another hand-correction, or a Rigenera)
        # minted the same next `attempt` first -- roll back and let
        # Francesco retry rather than surfacing a raw 500 (this story's I/O
        # & Edge-Case Matrix, "Concurrent correct + regenerate").
        session.rollback()
        response = RedirectResponse(f"/report-runs/{run_id}/draft", status_code=303)
        set_flash(
            response,
            "danger",
            "Un'altra operazione ha già modificato questo Report: riprova.",
            environment=request.app.state.settings.environment,
        )
        return response

    result = run_gate(corrected_draft, stored_payload.payload, request.app.state.gate_vocabulary)
    new_stored_gate_result = store_gate_result(
        session,
        run=run,
        passed=result.passed,
        regeneration_count=run.regeneration_count,
        vocabulary_version=result.vocabulary_version,
        vocabulary_content_hash=result.vocabulary_content_hash,
        violations=result.violations,
    )

    # Counted, not a plain set (code-review fix, 2026-09-02): two violations
    # can share identical (kind, section, sentence, entry_ids, detail)
    # content -- a `Counter` over the old reviewed rows' own keys, consumed
    # one-for-one as each match carries forward, means N old-accepted
    # duplicates carry forward to at most N new duplicate-content
    # violations, never silently double-accepting an unreviewed twin.
    old_reviewed_keys = Counter(
        (review.kind, review.section, review.sentence, tuple(review.entry_ids), review.detail)
        for review in session.exec(
            select(GateViolationReview).where(
                GateViolationReview.gate_result_id == stored_gate_result.id
            )
        ).all()
    )
    for new_index, new_violation in enumerate(result.violations):
        key = (
            new_violation.kind,
            new_violation.section,
            new_violation.sentence,
            new_violation.entry_ids,
            new_violation.detail,
        )
        if old_reviewed_keys[key] > 0:
            old_reviewed_keys[key] -= 1
            store_gate_violation_review(
                session,
                run=run,
                gate_result=new_stored_gate_result,
                violation_index=new_index,
                kind=new_violation.kind,
                section=new_violation.section,
                sentence=new_violation.sentence,
                entry_ids=new_violation.entry_ids,
                detail=new_violation.detail,
            )

    # Commit the correction itself -- the new ReportDraft, the new
    # StoredGateResult, and any carried-forward GateViolationReview rows --
    # before branching on the outcome (code-review fix, 2026-09-02). Every
    # branch below performs its own subsequent write (a genuine pass's
    # `store_report`, or `_close_run_via_accepted_violations`'s own
    # closing-Report attempt); if either hits a concurrent-writer
    # `IntegrityError` and rolls back, that rollback must only ever undo its
    # own write, never discard the correction this request just made.
    session.commit()

    if result.passed:
        store_report(
            session,
            run=run,
            style_guide_version=stored_new_draft.style_guide_version,
            payload_schema_version=stored_payload.schema_version,
            gate_vocabulary_version=result.vocabulary_version,
            gate_vocabulary_content_hash=result.vocabulary_content_hash,
        )
        run.failed_at = None
        run.failure_reason = None
        run.stage = "gate_passed"
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        response = RedirectResponse(f"/report-runs/{run_id}", status_code=303)
        set_flash(
            response,
            "success",
            "Correzione applicata: verifica di fondatezza superata.",
            environment=request.app.state.settings.environment,
        )
        return response

    if _close_run_via_accepted_violations(
        session,
        run,
        new_stored_gate_result,
        new_stored_gate_result.violations,
        stored_draft=stored_new_draft,
        stored_payload=stored_payload,
    ):
        response = RedirectResponse(f"/report-runs/{run_id}", status_code=303)
        set_flash(
            response,
            "success",
            "Correzione applicata: verifica completata con eccezioni.",
            environment=request.app.state.settings.environment,
        )
        return response

    # Still open: at least one violation on the new result remains
    # unreviewed. This branch persists a real new ReportDraft/StoredGateResult
    # pair for `run` without otherwise touching it -- bump `updated_at` here,
    # the same way the other two outcome branches above already do
    # (code-review fix, 2026-09-02).
    run.updated_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    response = RedirectResponse(f"/report-runs/{run_id}/draft", status_code=303)
    set_flash(
        response,
        "success",
        "Correzione applicata.",
        environment=request.app.state.settings.environment,
    )
    return response


@router.get("/report-runs/{run_id}/payload", include_in_schema=False)
def view_report_payload(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Read the frozen Payload behind ``run_id``'s Report, entry by entry
    (Story 3.9, PRD FR-15).

    404 covers both "no such ``ReportRun``" and "that run hasn't reached
    ``payload_ready`` yet" -- both collapse to the same query finding no
    ``ReportPayload`` row for ``run_id``, so no separate ``ReportRun`` lookup
    is needed first.
    """
    stored = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run_id)
    ).first()
    if stored is None:
        raise HTTPException(status_code=404)

    client = session.get(Client, stored.client_id)
    if client is None:
        raise RuntimeError(f"ReportPayload {stored.id} references a missing Client.")

    run = session.get(ReportRun, run_id)
    if run is None:
        raise RuntimeError(f"ReportPayload {stored.id} references a missing ReportRun.")

    localized = localize_payload(stored.payload, iana_zone=client.iana_zone)

    return _templates.TemplateResponse(
        request,
        "report_payload.html",
        {
            "payload": localized,
            "section_titles": SECTION_TITLES,
            "field_titles": FIELD_TITLES,
            "client": client,
            "run": run,
        },
    )


@router.get("/report-runs/{run_id}/draft", include_in_schema=False)
def view_report_draft(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Read the persisted ``GeneratedDraft`` behind ``run_id``'s Report,
    rendered into prose Sections 1-5/8 and dated-list Sections 6-7, in the
    draft's own fixed 1-8 order (Story 4.6, AD-6).

    404s if ``run_id`` names no ``ReportRun`` at all, or if that run hasn't
    reached ``draft_ready`` yet (no ``ReportDraft`` row) -- the latter also
    covers a run that failed generically before any draft existed (Story
    5.5's I/O & Edge-Case Matrix).

    Ordered by ``attempt`` descending (Story 5.4): more than one
    ``ReportDraft`` row can now exist for ``run_id`` once a run has
    regenerated at least once, and Francesco must always see the latest
    attempt, never an arbitrary one.

    When ``run.failed_at`` is set (Story 5.4's regeneration bound exhausted,
    the last ``ReportDraft`` still reachable), the Groundedness Gate is
    *not* recomputed -- ``_current_cycle_gate_failure`` (Story 9.5, review
    -loop 1) reads back the ``StoredGateResult`` row that actually caused
    *this* run's *current* failure (the highest-``regeneration_count`` failing
    row, but only when its ``created_at`` correlates with ``run.failed_at`` --
    see that function's own docstring), so a vocabulary edit landing between
    the run's terminal failure and Francesco opening its draft can never show
    a different violation set than what actually failed (epic-5-retro-item-38),
    and a stale Gate failure from an earlier cycle superseded by a
    ``/regenerate`` rewind can never resurface as if it were current. No
    correlated row found (a generic, non-Gate terminal failure never wrote
    one, or the only row on record predates a rewind) -> ``violations``
    defaults to an empty list and ``gate_failed`` to ``False``. Either way,
    ``run`` itself is added to the template context, for ``failure_reason``
    (Story 5.5). A passing run's context is left byte-for-byte unchanged: no
    query, no new context keys.
    """
    run = session.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404)

    stored_draft = session.exec(
        select(ReportDraft)
        .where(ReportDraft.report_run_id == run_id)
        .order_by(ReportDraft.attempt.desc())
    ).first()
    if stored_draft is None:
        raise HTTPException(status_code=404)

    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run_id)
    ).first()
    if stored_payload is None:
        raise RuntimeError(f"ReportDraft {stored_draft.id} has no matching ReportPayload.")

    client = session.get(Client, stored_draft.client_id)
    if client is None:
        raise RuntimeError(f"ReportDraft {stored_draft.id} references a missing Client.")

    rendered = _render_stored_draft(stored_draft, stored_payload, client)

    context: dict[str, Any] = {
        "draft": rendered,
        "section_order": SECTION_ORDER,
        "list_section_names": LIST_SECTION_NAMES,
        "section_titles": SECTION_TITLES,
        # Story 9.6 amendment (correct-course 2026-08-31): the breadcrumb
        # needs `client`/`run` on every visit, not only a failed one -- the
        # `if run.failed_at` branch below still only adds the Gate-failure
        # extras, unchanged.
        "client": client,
        "run": run,
    }
    if run.failed_at is not None:
        stored_gate_result = _current_cycle_gate_failure(session, run)
        violations = stored_gate_result.violations if stored_gate_result is not None else []
        # Story 5.7: which violation indices already have an accept review
        # row, so a page reload after an accept shows a resolved strip
        # instead of the still-open card -- read only when a current-cycle
        # Gate failure actually exists (no `stored_gate_result.id` to query
        # against otherwise).
        accepted_indices: set[int] = set()
        if stored_gate_result is not None:
            accepted_indices = set(
                session.exec(
                    select(GateViolationReview.violation_index).where(
                        GateViolationReview.gate_result_id == stored_gate_result.id
                    )
                ).all()
            )
        context["violations"] = [
            {
                **violation,
                "kind_label": violation_kind_label(violation["kind"]),
                "index": index,
                "accepted": index in accepted_indices,
            }
            for index, violation in enumerate(violations)
        ]
        context["gate_failed"] = stored_gate_result is not None

    return _templates.TemplateResponse(request, "report_draft.html", context)


@router.get("/report-runs/{run_id}/report", include_in_schema=False)
def view_report(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Read the finished, Gate-passed Report behind ``run_id`` (Story 6.1):
    the same eight Sections ``view_report_draft`` renders, plus the
    persisted Gate verdict (Story 5.6's ``StoredGateResult``) and a link to
    the Payload view (Story 3.9) -- Francesco's one-click destination once a
    run's Gate has passed.

    Gated on a persisted ``Report`` row's mere existence, not on
    ``run.stage`` -- mirrors ``shell/export.py::export_report()``'s own
    boundary and ``view_report_payload``'s "row missing = not ready"
    pattern: 404 covers both "no such ``ReportRun``" and "that run's Gate
    hasn't passed yet" (no ``Report`` row is ever written on a failing pass
    or before ``gate_passed`` is reached).

    Once a ``Report`` row exists, the ``ReportDraft``/``ReportPayload``/
    ``Client``/passing ``StoredGateResult`` rows it implies are read back
    with ``RuntimeError`` guards, never a 404 -- their absence at that point
    would be a data-integrity bug, not a not-ready state, mirroring
    ``view_report_draft``'s own ``RuntimeError``-on-missing shape for the
    ``ReportPayload``/``Client`` lookups above.

    The regeneration count shown is read off the persisted, passing
    ``StoredGateResult`` row, never off ``run.regeneration_count`` directly
    -- epic-5-retro-item-38's precedent, see this story's Design Notes.

    ``bundle.report.accepted_violation_count > 0`` (Story 5.7) -- this
    Report was closed via accepted exceptions, not a genuine Gate pass --
    reads ``stored_gate_result`` back via ``closing_gate_result_id``
    directly instead of the ``passed.is_(True)`` query: the closing
    ``StoredGateResult`` row for this path is the *failing* check Francesco
    reviewed and accepted, so no row with ``passed=True`` exists for this
    run at all. The existing clean-pass branch below is otherwise
    unchanged.

    Also passes ``latest_export`` (the most recent ``ExportRecord`` for this
    Report, or ``None`` before the first export) and ``disposition_choices``
    (Story 6.3) -- ``report.html`` uses these to show the one-click
    "how did it go out" forms once an export exists and disposition is still
    unset, or the recorded choice once it is set. Also passes ``report``
    (``bundle.report``, Story 5.7) so the template can render the
    "Superato con N eccezioni" badge.
    """
    bundle = _load_passed_report_bundle(session, run_id)

    if bundle.report.accepted_violation_count > 0:
        stored_gate_result = session.get(StoredGateResult, bundle.report.closing_gate_result_id)
    else:
        stored_gate_result = session.exec(
            select(StoredGateResult)
            .where(StoredGateResult.report_run_id == run_id)
            .where(StoredGateResult.passed.is_(True))
            .order_by(StoredGateResult.regeneration_count.desc())
        ).first()
    if stored_gate_result is None:
        raise RuntimeError(f"Report {bundle.report.id} has no matching passed StoredGateResult.")

    n = stored_gate_result.regeneration_count
    regeneration_note = (
        f"Verifica superata dopo {n} rigenerazione."
        if n == 1
        else f"Verifica superata dopo {n} rigenerazioni."
    )

    return _templates.TemplateResponse(
        request,
        "report.html",
        {
            "draft": bundle.rendered,
            "section_order": SECTION_ORDER,
            "list_section_names": LIST_SECTION_NAMES,
            "section_titles": SECTION_TITLES,
            "run_id": run_id,
            "run": bundle.run,
            "client": bundle.client,
            "report": bundle.report,
            "gate_result": stored_gate_result,
            "regeneration_note": regeneration_note,
            "latest_export": _latest_export_record(session, run_id),
            "disposition_choices": DISPOSITION_CHOICES,
        },
    )


@router.get("/report-runs/{run_id}/export/pdf", include_in_schema=False)
def download_report_pdf(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Download a passed Report's eight Sections plus the Client's name as a
    standalone PDF file (Story 6.2) -- Francesco's hand-to-a-client artifact.

    Gated on the same persisted ``Report`` row's mere existence
    ``view_report`` (Story 6.1) gates on, never on ``run.stage``: 404 covers
    both "no such ``ReportRun``" and "that run's Gate hasn't passed yet",
    exactly mirroring ``view_report``'s own boundary
    (``shell/export.py::export_report()``'s structural gate).

    Once a ``Report`` row exists, the same ``ReportDraft``/``ReportPayload``/
    ``Client`` rows it implies are read back with ``RuntimeError`` guards,
    never a 404 -- their absence at that point would be a data-integrity
    bug, mirroring ``view_report``'s own shape exactly (this route does not
    call ``view_report`` itself -- Boundaries: that route/its template stay
    untouched beyond one added link).

    The PDF itself carries only the eight Sections and the Client's name
    (``shell/http/templates/report_export.html``) -- no chart wheel, no
    Payload, no Gate result, no run identifier, no internal metadata
    (this story's Boundaries).

    The first successful export advances ``run.stage`` to ``"exported"``
    once, mirroring how ``run.stage`` only ever advances forward; every
    export after that leaves ``run.stage`` alone and only writes a new
    ``ExportRecord`` row (``shell/adapters/postgres/export_record.py``) --
    one row per export, first or repeat. That row's ``elapsed_seconds``
    (Story 6.3) is computed here, from ``run.created_at`` (Client selection)
    to now, never estimated later; its ``disposition`` starts ``NULL`` and is
    set afterward, in one click, by ``record_export_disposition`` below.

    **Accepted GET-with-side-effects deviation (epic-6-retro-item-49).** This
    route mutates on ``GET``: every hit writes an ``ExportRecord`` row, the
    first advances ``run.stage``, and it commits -- on any ``GET``, including
    an incidental one from a browser prefetch or a crawler. That is accepted,
    not a bug, on the same rationale already ratified for ``GET /backup`` (a
    plain-link download; moving it to ``POST`` was declined): an incidental
    hit only writes a harmless extra ``ExportRecord``, and the ``run.stage``
    advance is monotonic and idempotent, so there is no analogue here of the
    staleness-warning-clearing risk that motivated gating ``/backup``'s
    ``backup_record`` write behind ``?record=1``. ``download_report_markdown``
    below carries the same deviation. Recorded in ``docs/decisions/`` as RGD-4.
    """
    bundle = _load_passed_report_bundle(session, run_id)

    export_html = _templates.get_template("report_export.html").render(
        {
            "client_name": bundle.client.name,
            "draft": bundle.rendered,
            "section_order": SECTION_ORDER,
            "list_section_names": LIST_SECTION_NAMES,
            "section_titles": SECTION_TITLES,
        }
    )
    pdf_bytes = html_to_pdf(export_html)

    if bundle.run.stage != "exported":
        bundle.run.stage = "exported"
        session.add(bundle.run)
    elapsed_seconds = int((datetime.now(UTC) - bundle.run.created_at).total_seconds())
    store_export_record(
        session, report=bundle.report, format="pdf", elapsed_seconds=elapsed_seconds
    )
    session.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{run_id}.pdf"'},
    )


@router.get("/report-runs/{run_id}/export/markdown", include_in_schema=False)
def download_report_markdown(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Download a passed Report's eight Sections plus the Client's name as a
    standalone Markdown file (spec-6-2b, epic-6 retrospective item 47) -- the
    plain-text sibling of :func:`download_report_pdf`, for pasting into an
    email or a message without the PDF round-trip.

    Structurally identical to :func:`download_report_pdf`: the same
    ``_load_passed_report_bundle`` gate (404 on "no such run" / "Gate hasn't
    passed yet", ``RuntimeError`` on any row it implies being missing once a
    ``Report`` exists), the same first-export-advances-``run.stage``-to-
    ``"exported"``-once and every-export-writes-one-``ExportRecord`` semantics,
    the same ``elapsed_seconds`` computed from ``run.created_at``. Only the
    body serializer (``render_report_markdown`` instead of ``html_to_pdf``)
    and ``ExportRecord.format`` (``"markdown"``) differ. ``ExportRecord.format``
    already stores an arbitrary string, so no schema change and no migration.

    The Markdown body carries only the eight Italian-titled Sections and the
    Client's name -- no chart wheel, no Payload, no Gate result, no run
    identifier, no internal metadata. It is the plain-text counterpart of
    ``report_export.html`` with the same section set and ordering; the
    per-entry layout is not line-for-line identical (an uncited day entry
    renders date-only in Markdown -- see ``render_report_markdown``). The
    accepted GET-with-side-effects deviation recorded on
    :func:`download_report_pdf` (retro item 49) applies here verbatim.
    """
    bundle = _load_passed_report_bundle(session, run_id)

    markdown_body = render_report_markdown(
        bundle.rendered,
        client_name=bundle.client.name,
        section_order=SECTION_ORDER,
        list_section_names=LIST_SECTION_NAMES,
        section_titles=SECTION_TITLES,
    )

    if bundle.run.stage != "exported":
        bundle.run.stage = "exported"
        session.add(bundle.run)
    elapsed_seconds = int((datetime.now(UTC) - bundle.run.created_at).total_seconds())
    store_export_record(
        session, report=bundle.report, format="markdown", elapsed_seconds=elapsed_seconds
    )
    session.commit()

    return Response(
        content=markdown_body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report-{run_id}.md"'},
    )


@router.post("/report-runs/{run_id}/export/disposition", include_in_schema=False)
def record_export_disposition(
    run_id: UUID,
    request: Request,
    disposition: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    """Record how the latest export of ``run_id``'s Report actually went out
    -- ``"as_generated"`` or ``"edited"`` -- in one click (Story 6.3).

    404s if no ``ExportRecord`` exists yet for ``run_id``'s ``Report``
    (covering "no such run" too, since neither can exist without the
    other) -- checked directly via ``_latest_export_record`` before
    ``record_send_disposition`` is ever called, so that function's own
    ``False`` return (no row updated) can only mean "already set", never
    "nothing to update": a genuine no-op, not an error, redirecting exactly
    like a first-time set does (this story's I/O & Edge-Case Matrix).
    """
    if disposition not in _DISPOSITION_VALUES:
        raise HTTPException(
            status_code=422,
            detail="disposition must be one of: " + ", ".join(sorted(_DISPOSITION_VALUES)),
        )

    if _latest_export_record(session, run_id) is None:
        raise HTTPException(
            status_code=404,
            detail="this Report has not been exported yet -- there is no export to record a "
            "disposition against.",
        )

    record_send_disposition(session, run_id=run_id, disposition=disposition)
    session.commit()

    response = RedirectResponse(f"/report-runs/{run_id}/report", status_code=303)
    set_flash(
        response,
        "success",
        "Esito di invio registrato.",
        environment=request.app.state.settings.environment,
    )
    return response
