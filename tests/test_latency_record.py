"""Guard suite for the dated latency-measurement record
(``docs/release-validation/latency.md``, Story 8.3), plus the opt-in
measurement harness that produces the numbers it holds.

The always-on guard tests mirror the read-the-file style of
``tests/test_data_terms_record.py``: read the files, parse in-process, no
network and no Docker. The record's machine-readable block is a fenced
```toml``` block parsed with ``tomllib`` (stdlib) -- no YAML parser is a
dependency in this repo. The guard suite stays red while the recorded
measured p90s sit outside their recorded budgets, while those budgets drift
from ``epics.md``'s NFR-5 / NFR-10, or while ``outcome`` is anything other
than ``"pass"`` -- so an un-reconciled over-budget measurement, or a record
that has not yet been completed with a live-Gemini generation sample and
ratified, keeps the release gate from going green.

``test_measure_latency`` is the harness: 40 end-to-end runs -- each a full
poll-drain of ``advance()`` (AD-20's one-stage-per-poll runner, Story 3.10)
through ``RecordedResponseGenerator`` -- plus an isolated full-month transit
scan, each timed with ``time.perf_counter()``. It never asserts on elapsed
time -- timings are environment-dependent data, not pass/fail -- only that
every run reaches ``gate_passed`` with ``failed_at is None`` (the throughput
guarantee). It is skipped unless ``RUN_LATENCY_MEASUREMENT=1`` so the
default ``uv run pytest`` stays fast; run it deliberately as a release
action and paste its printed block into ``latency.md``.

Story 10.7 adds ``test_measure_epic10_latency`` (``RUN_LATENCY_MEASUREMENT=epic10``):
the same idea against the running local docker app with real Gemini -- draft,
per-Section, regeneration and PDF timings, which the guards below hold to the
Epic 10 targets. Each guard is a plain function over the record's dict so a
negative test can prove it fails (``test_the_guard_detects_a_*``).
"""

from __future__ import annotations

import datetime
import math
import os
import re

import pytest

from tests._latency_epic10 import bound_one_regen_seconds
from tests._release_validation import (
    REPO_ROOT,
    assert_outcome_permits_release,
    assert_record_not_stale,
    load_record_meta,
)

RECORD_FILE = REPO_ROOT / "docs" / "release-validation" / "latency.md"
EPICS_FILE = REPO_ROOT / "_bmad-output" / "planning-artifacts" / "epics.md"

#: Max age of `checked` before the record is flagged stale (epic-8-retro-item-62).
_MAX_RECORD_AGE_DAYS = 550

#: NFR-5's minutes x 60 and NFR-10's seconds, as written in the Boundaries --
#: the guard tests bind the recorded budgets to both these literals *and* to
#: the numbers parsed live out of ``epics.md``, so the record, the epic and
#: this suite can never silently disagree.
_REPORT_BUDGET_SECONDS = 180
_MONTH_SCAN_BUDGET_SECONDS = 10

#: The throughput target NFR-5 states: forty Reports in a single working
#: session.
_SESSION_REPORTS_TARGET = 40

#: Epic 10's targets (Story 10.7; the draft target was revised from 60 s to 90 s by
#: Francesco on 2026-10-02): draft p90 at most, PDF first export at most,
#: repeat download strictly under.
_DRAFT_BUDGET_SECONDS = 90
_PDF_FIRST_BUDGET_SECONDS = 6
_PDF_REPEAT_BUDGET_SECONDS = 1

#: The fewest successful runs the Epic 10 figures may rest on.
_MIN_EPIC10_RUNS_OK = 15

_EXPECTED_KEYS = {
    "checked",
    "ratified_by",
    "ratified_on",
    "environment",
    "report_budget_seconds",
    "draft_budget_seconds",
    "pdf_first_budget_seconds",
    "pdf_repeat_budget_seconds",
    "runs_ok",
    "draft_p90_seconds",
    "section_p90_seconds",
    "one_regen_p90_seconds",
    "one_regen_basis",
    "regen_runs_observed",
    "pdf_first_p90_seconds",
    "pdf_repeat_p90_seconds",
    "month_scan_p90_seconds",
    "month_scan_budget_seconds",
    "session_reports",
    "sitting_confirmed",
    "repetition_reviewed",
    "outcome",
}


def _epics_requirement_line(tag: str) -> str:
    """The single ``epics.md`` line that begins ``<tag>:`` (e.g. ``NFR-5``) --
    the guard tests parse the stated bound out of exactly that line, never a
    stray match elsewhere in the document."""
    text = EPICS_FILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.lstrip().startswith(f"{tag}:"):
            return line
    raise AssertionError(f"epics.md has no line starting {tag!r}")


@pytest.fixture(scope="module")
def meta() -> dict[str, object]:
    return load_record_meta(RECORD_FILE, record_label="latency")


# --- Always-on guard tests (validate the record, never measure) ----------------


def test_record_exists() -> None:
    assert RECORD_FILE.exists(), (
        f"release-validation latency record missing: {RECORD_FILE} -- "
        "Story 8.3 requires a dated measurement of the per-Report and "
        "full-month-scan latency the PRD only assumed"
    )


def test_record_is_not_stale(meta: dict[str, object]) -> None:
    assert_record_not_stale(meta, max_age_days=_MAX_RECORD_AGE_DAYS, record_label="latency")


def test_toml_block_parses(meta: dict[str, object]) -> None:
    missing = _EXPECTED_KEYS - meta.keys()
    unexpected = meta.keys() - _EXPECTED_KEYS
    assert not missing, f"latency record toml block missing keys: {sorted(missing)}"
    assert not unexpected, (
        f"latency record toml block has unexpected keys: {sorted(unexpected)} -- "
        "update _EXPECTED_KEYS and the matching assertions if a key was added on purpose"
    )
    for key in (
        "report_budget_seconds",
        "draft_budget_seconds",
        "pdf_first_budget_seconds",
        "pdf_repeat_budget_seconds",
        "runs_ok",
        "regen_runs_observed",
        "month_scan_p90_seconds",
        "month_scan_budget_seconds",
        "session_reports",
    ):
        assert isinstance(meta[key], int), (
            f"`{key}` must be a whole-number integer (whole seconds / a count), got {meta[key]!r}"
        )
    for key in (
        "draft_p90_seconds",
        "section_p90_seconds",
        "one_regen_p90_seconds",
        "pdf_first_p90_seconds",
        "pdf_repeat_p90_seconds",
    ):
        assert isinstance(meta[key], (int, float)) and not isinstance(meta[key], bool), (
            f"`{key}` must be a number of seconds, got {meta[key]!r}"
        )
    assert isinstance(meta["environment"], str) and meta["environment"].strip(), (
        f"`environment` must be a non-empty string describing where the "
        f"measurement ran, got {meta['environment']!r}"
    )


def test_checked_is_a_date(meta: dict[str, object]) -> None:
    checked = meta["checked"]
    assert isinstance(checked, datetime.date), (
        f"`checked` must be a bare ISO date (parses to datetime.date), got {checked!r}"
    )
    assert checked <= datetime.date.today(), (
        f"`checked` = {checked.isoformat()} is in the future -- a measurement "
        "cannot have happened yet (epic-4 retro item 25)"
    )


def test_ratified_on_is_a_date(meta: dict[str, object]) -> None:
    assert isinstance(meta["ratified_on"], datetime.date), (
        f"`ratified_on` must be a bare ISO date, got {meta['ratified_on']!r}"
    )
    assert isinstance(meta["ratified_by"], str) and meta["ratified_by"].strip(), (
        f"`ratified_by` must be a non-empty string, got {meta['ratified_by']!r}"
    )
    assert meta["ratified_on"] >= meta["checked"], (
        f"`ratified_on` {meta['ratified_on'].isoformat()} precedes `checked` "
        f"{meta['checked'].isoformat()} -- a measurement cannot be ratified "
        "before it was taken"
    )


def test_outcome_is_valid(meta: dict[str, object]) -> None:
    assert meta["outcome"] in {"pass", "blocked"}, (
        f'`outcome` must be exactly "pass" or "blocked", got {meta["outcome"]!r}'
    )


def test_sitting_confirmed_is_a_bool(meta: dict[str, object]) -> None:
    """epic-8-retro-item-65: the bespoke evidence field gating `outcome =
    "pass"` must be a real TOML boolean -- a typo like a string "false" would
    otherwise slip through the whole `outcome = "blocked"` window undetected."""
    assert isinstance(meta["sitting_confirmed"], bool), (
        f"`sitting_confirmed` must be a TOML boolean (true/false), got "
        f"{meta['sitting_confirmed']!r}"
    )
    assert isinstance(meta["repetition_reviewed"], bool), (
        f"`repetition_reviewed` must be a TOML boolean (true/false), got "
        f"{meta['repetition_reviewed']!r}"
    )


def test_outcome_permits_release(meta: dict[str, object]) -> None:
    assert_outcome_permits_release(
        meta,
        evidence_field="sitting_confirmed",
        evidence_value=True,
        record_label="latency",
    )
    assert meta["repetition_reviewed"] is True, (
        "release blocked until Francesco has read the Epic 10 reports side by side "
        "for repetition between Sections (`repetition_reviewed`)"
    )
    assert meta["outcome"] == "pass", (
        "release blocked until latency is measured, budgets reconciled and the "
        f'record ratified (outcome = {meta["outcome"]!r}, expected "pass")'
    )


def _check_report_within_budget(meta: dict[str, object]) -> None:
    # NFR-5 says "under 3 minutes" -- strict. With regeneration counted in
    # (the one-regeneration figure), not the single-call best case.
    assert meta["one_regen_p90_seconds"] < meta["report_budget_seconds"], (
        f"one-regeneration p90 {meta['one_regen_p90_seconds']}s is not under the "
        f"recorded budget {meta['report_budget_seconds']}s -- reconcile the budget "
        "(revise NFR-5 in epics.md and the PRD to the ratified value) rather than "
        "leaving it unmet"
    )


def _check_draft_within_budget(meta: dict[str, object]) -> None:
    assert meta["draft_p90_seconds"] <= meta["draft_budget_seconds"], (
        f"draft p90 {meta['draft_p90_seconds']}s is over the Epic 10 target "
        f"{meta['draft_budget_seconds']}s -- do not edit the budget silently"
    )


def _check_pdf_within_budget(meta: dict[str, object]) -> None:
    assert meta["pdf_first_p90_seconds"] <= meta["pdf_first_budget_seconds"], (
        f"PDF first-export p90 {meta['pdf_first_p90_seconds']}s is over the target "
        f"{meta['pdf_first_budget_seconds']}s"
    )
    assert meta["pdf_repeat_p90_seconds"] < meta["pdf_repeat_budget_seconds"], (
        f"PDF repeat-download p90 {meta['pdf_repeat_p90_seconds']}s is not under "
        f"{meta['pdf_repeat_budget_seconds']}s -- the stored-PDF cache is not serving"
    )


def _check_regen_basis(meta: dict[str, object]) -> None:
    """A figure derived from a bound may never be recorded as observed, and the
    bound must be the documented sum -- never a hand-typed lower number."""
    observed = meta["regen_runs_observed"] >= 1
    assert (meta["one_regen_basis"] == "observed") == observed, (
        f"one_regen_basis {meta['one_regen_basis']!r} contradicts "
        f"regen_runs_observed = {meta['regen_runs_observed']}"
    )
    if not observed:
        assert meta["one_regen_basis"] == "bound"
        bound = bound_one_regen_seconds(meta["draft_p90_seconds"], meta["section_p90_seconds"])
        assert meta["one_regen_p90_seconds"] >= bound, (
            f"bound-basis one_regen_p90_seconds {meta['one_regen_p90_seconds']}s is below "
            f"draft p90 + 2 x section p90 = {bound}s"
        )


def _check_enough_runs(meta: dict[str, object]) -> None:
    assert meta["runs_ok"] >= _MIN_EPIC10_RUNS_OK, (
        f"runs_ok {meta['runs_ok']} is below the minimum {_MIN_EPIC10_RUNS_OK} -- the "
        "Epic 10 figures must rest on real, successful runs"
    )


def test_report_p90_within_budget(meta: dict[str, object]) -> None:
    _check_report_within_budget(meta)


def test_draft_p90_within_target(meta: dict[str, object]) -> None:
    _check_draft_within_budget(meta)


def test_pdf_within_targets(meta: dict[str, object]) -> None:
    _check_pdf_within_budget(meta)


def test_regeneration_basis_is_honest(meta: dict[str, object]) -> None:
    _check_regen_basis(meta)


def test_epic10_sample_is_large_enough(meta: dict[str, object]) -> None:
    _check_enough_runs(meta)


def test_epic10_budgets_match_the_suite(meta: dict[str, object]) -> None:
    assert meta["draft_budget_seconds"] == _DRAFT_BUDGET_SECONDS
    assert meta["pdf_first_budget_seconds"] == _PDF_FIRST_BUDGET_SECONDS
    assert meta["pdf_repeat_budget_seconds"] == _PDF_REPEAT_BUDGET_SECONDS


def test_the_guard_detects_a_draft_over_budget(meta: dict[str, object]) -> None:
    with pytest.raises(AssertionError):
        _check_draft_within_budget({**meta, "draft_p90_seconds": _DRAFT_BUDGET_SECONDS + 0.1})


def test_the_guard_detects_a_slow_pdf(meta: dict[str, object]) -> None:
    with pytest.raises(AssertionError):
        _check_pdf_within_budget({**meta, "pdf_first_p90_seconds": _PDF_FIRST_BUDGET_SECONDS + 0.1})
    with pytest.raises(AssertionError):
        _check_pdf_within_budget({**meta, "pdf_repeat_p90_seconds": _PDF_REPEAT_BUDGET_SECONDS})


def test_the_guard_detects_a_report_over_the_nfr_budget(meta: dict[str, object]) -> None:
    with pytest.raises(AssertionError):
        _check_report_within_budget({**meta, "one_regen_p90_seconds": _REPORT_BUDGET_SECONDS})


def test_the_guard_detects_a_bound_recorded_as_observed(meta: dict[str, object]) -> None:
    with pytest.raises(AssertionError):
        _check_regen_basis({**meta, "regen_runs_observed": 0, "one_regen_basis": "observed"})
    with pytest.raises(AssertionError):
        _check_regen_basis({**meta, "regen_runs_observed": 2, "one_regen_basis": "bound"})


def test_the_guard_detects_a_too_low_bound(meta: dict[str, object]) -> None:
    with pytest.raises(AssertionError):
        _check_regen_basis(
            {
                **meta,
                "regen_runs_observed": 0,
                "one_regen_basis": "bound",
                "draft_p90_seconds": 50.0,
                "section_p90_seconds": 20.0,
                "one_regen_p90_seconds": 60.0,
            }
        )


def test_the_guard_detects_too_few_runs(meta: dict[str, object]) -> None:
    with pytest.raises(AssertionError):
        _check_enough_runs({**meta, "runs_ok": _MIN_EPIC10_RUNS_OK - 1})


def test_month_scan_p90_within_budget(meta: dict[str, object]) -> None:
    # NFR-10 says "under 10 seconds" -- strict; see test_report_p90_within_budget.
    assert meta["month_scan_p90_seconds"] < meta["month_scan_budget_seconds"], (
        f"measured full-month-scan p90 {meta['month_scan_p90_seconds']}s is not "
        f"under the recorded budget {meta['month_scan_budget_seconds']}s -- "
        "reconcile the budget (revise NFR-10 in epics.md and the PRD) rather "
        "than leaving it unmet"
    )


def test_report_budget_matches_epics(meta: dict[str, object]) -> None:
    line = _epics_requirement_line("NFR-5")
    match = re.search(r"under\s+(\d+)\s*minutes?", line, re.IGNORECASE)
    assert match is not None, (
        f"could not find NFR-5's 'under N minute(s)' bound in epics.md: {line!r}"
    )
    epics_seconds = int(match.group(1)) * 60
    assert epics_seconds == meta["report_budget_seconds"] == _REPORT_BUDGET_SECONDS, (
        f"NFR-5 bound in epics.md is {epics_seconds}s, record "
        f"report_budget_seconds is {meta['report_budget_seconds']}s, this suite "
        f"expects {_REPORT_BUDGET_SECONDS}s -- all three must agree"
    )


def test_month_scan_budget_matches_epics(meta: dict[str, object]) -> None:
    line = _epics_requirement_line("NFR-10")
    match = re.search(r"under\s+(\d+)\s*seconds?", line, re.IGNORECASE)
    assert match is not None, (
        f"could not find NFR-10's 'under N second(s)' bound in epics.md: {line!r}"
    )
    epics_seconds = int(match.group(1))
    assert epics_seconds == meta["month_scan_budget_seconds"] == _MONTH_SCAN_BUDGET_SECONDS, (
        f"NFR-10 bound in epics.md is {epics_seconds}s, record "
        f"month_scan_budget_seconds is {meta['month_scan_budget_seconds']}s, this "
        f"suite expects {_MONTH_SCAN_BUDGET_SECONDS}s -- all three must agree"
    )


def test_session_reports_meets_target(meta: dict[str, object]) -> None:
    assert meta["session_reports"] >= _SESSION_REPORTS_TARGET, (
        f"session_reports {meta['session_reports']} is below the "
        f"{_SESSION_REPORTS_TARGET}-in-one-sitting throughput target NFR-5 states"
    )


# --- Opt-in measurement harness ----------------------------------------------------

_RUN_COUNT = 40
_MONTH = "2026-01"


def _nearest_rank_p90(samples: list[float]) -> float:
    """Nearest-rank p90 (Boundaries): ``sorted(d)[ceil(0.9 * len(d)) - 1]``."""
    ordered = sorted(samples)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


@pytest.mark.skipif(
    os.environ.get("RUN_LATENCY_MEASUREMENT") != "1",
    reason="set RUN_LATENCY_MEASUREMENT=1 to run the 40-run latency harness",
)
def test_measure_latency(capsys: pytest.CaptureFixture[str]) -> None:
    """Drive 40 end-to-end Reports and an isolated full-month scan, time each,
    print a paste-ready toml block. Asserts only that every run reaches
    ``gate_passed`` with ``failed_at is None`` -- never on elapsed time."""
    import time
    from datetime import date
    from datetime import time as time_of_day

    from sqlmodel import Session, SQLModel, create_engine

    from core.transits.aspects import find_transit_aspects
    from core.transits.ingresses import find_ingresses
    from core.transits.lunations import find_lunations
    from core.transits.stations import find_stations
    from shell.adapters.local.generator import RecordedResponseGenerator
    from shell.adapters.postgres.client import create_client_with_chart
    from shell.adapters.postgres.report_run import ReportRun
    from shell.adapters.postgres.style_guide import create_style_guide_version
    from shell.runner.month import client_month_interval_utc
    from tests.test_runner_advance import (
        _COMPUTATION_CONFIG,
        _EPHEMERIS_IDENTITY,
        _RESOLVED_PLACE,
        _STYLE_GUIDE_CONTENT,
        _a_natal_chart,
        _drive,
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        natal_chart = _a_natal_chart()
        client = create_client_with_chart(
            session,
            name="Ada Lovelace",
            birth_date=date(2026, 1, 1),
            birth_time=time_of_day(0, 0),
            resolved_place=_RESOLVED_PLACE,
            natal_chart=natal_chart,
            computation_config=_COMPUTATION_CONFIG,
            ephemeris_identity=_EPHEMERIS_IDENTITY,
        )
        create_style_guide_version(session, _STYLE_GUIDE_CONTENT)
        session.commit()

        generator = RecordedResponseGenerator()
        run_seconds: list[float] = []
        for index in range(_RUN_COUNT):
            run = ReportRun(client_id=client.id, month=_MONTH)
            session.add(run)
            session.commit()

            started = time.perf_counter()
            # AD-20 (Story 3.10): advance() moves one stage per call, so the
            # end-to-end timing spans a full drain of it (tests.test_runner_advance._drive).
            result = _drive(session, run, natal_chart, generator=generator)
            elapsed = time.perf_counter() - started
            run_seconds.append(elapsed)

            assert result.stage == "gate_passed", (
                f"run {index + 1}/{_RUN_COUNT} stopped at {result.stage!r}, not "
                "gate_passed -- the 40-in-one-sitting throughput guarantee failed"
            )
            assert result.failed_at is None, (
                f"run {index + 1}/{_RUN_COUNT} was marked terminally failed: "
                f"{result.failure_reason!r}"
            )

        month_start_utc, month_end_utc = client_month_interval_utc(client, _MONTH)
        scan_seconds: list[float] = []
        for _ in range(_RUN_COUNT):
            started = time.perf_counter()
            find_transit_aspects(natal_chart, month_start_utc, month_end_utc, _COMPUTATION_CONFIG)
            find_stations(month_start_utc, month_end_utc, _COMPUTATION_CONFIG)
            find_ingresses(natal_chart, month_start_utc, month_end_utc, _COMPUTATION_CONFIG)
            find_lunations(natal_chart, month_start_utc, month_end_utc)
            scan_seconds.append(time.perf_counter() - started)

    local_stage_p90 = _nearest_rank_p90(run_seconds)
    month_scan_p90 = _nearest_rank_p90(scan_seconds)
    month_scan_p90_seconds = math.ceil(month_scan_p90)

    lines = [
        "",
        "=" * 72,
        f"Latency measurement -- {_RUN_COUNT} end-to-end runs + {_RUN_COUNT} isolated month scans",
        "=" * 72,
        "",
        f"{'run':>4}  {'end-to-end (s)':>16}  {'month scan (s)':>16}",
    ]
    for index in range(_RUN_COUNT):
        lines.append(f"{index + 1:>4}  {run_seconds[index]:>16.4f}  {scan_seconds[index]:>16.4f}")
    lines.extend(
        [
            "",
            f"end-to-end : min {min(run_seconds):.4f}  "
            f"median {sorted(run_seconds)[len(run_seconds) // 2]:.4f}  "
            f"p90 {local_stage_p90:.4f}  max {max(run_seconds):.4f}",
            f"month scan : min {min(scan_seconds):.4f}  "
            f"median {sorted(scan_seconds)[len(scan_seconds) // 2]:.4f}  "
            f"p90 {month_scan_p90:.4f}  max {max(scan_seconds):.4f}",
            "",
            "Only month_scan_p90_seconds is still recorded from this harness (the",
            "local-stage figure is superseded by test_measure_epic10_latency):",
            "",
            f"month_scan_p90_seconds = {month_scan_p90_seconds}",
            "",
        ]
    )
    with capsys.disabled():
        print("\n".join(lines))


@pytest.mark.skipif(
    os.environ.get("RUN_LATENCY_MEASUREMENT") != "epic10",
    reason="set RUN_LATENCY_MEASUREMENT=epic10 to run the real-Gemini Epic 10 harness",
)
def test_measure_epic10_latency(capsys: pytest.CaptureFixture[str]) -> None:
    """Story 10.7: 20 reports through the running local docker app (real Gemini,
    local Postgres), each timed from start to ``gate_passed`` and through two PDF
    exports. Prints a paste-ready toml block and saves five reports under
    ``cache/latency-reports/`` for the side-by-side read. Asserts only that enough
    runs succeeded -- elapsed time is data here, the record's guards judge it."""
    from datetime import date
    from datetime import time as time_of_day

    from sqlmodel import Session, create_engine

    from shell.adapters.postgres.client import (
        Client,
        create_client_with_chart,
        delete_client_and_derived,
    )
    from tests._latency_epic10 import (
        DATABASE_URL,
        app_is_up,
        authenticated_client,
        ceil_tenth,
        measure_run,
        nearest_rank_p90,
        repeated_shingle_count,
        save_reports,
    )
    from tests.test_runner_advance import (
        _COMPUTATION_CONFIG,
        _EPHEMERIS_IDENTITY,
        _RESOLVED_PLACE,
        _a_natal_chart,
    )

    if not app_is_up():
        pytest.skip("the local app is not answering on http://localhost:8000/healthz")
    env_file = REPO_ROOT / ".env"
    if not env_file.exists() or "USE_REAL_GEMINI_LOCALLY=true" not in env_file.read_text():
        pytest.skip("USE_REAL_GEMINI_LOCALLY=true is not set in .env -- no real Gemini")

    total_runs = 20
    engine = create_engine(DATABASE_URL.replace("postgresql://", "postgresql+psycopg://"))
    with Session(engine) as session:
        client = create_client_with_chart(
            session,
            name="Latency Harness Ada",
            birth_date=date(2026, 1, 1),
            birth_time=time_of_day(0, 0),
            resolved_place=_RESOLVED_PLACE,
            natal_chart=_a_natal_chart(),
            computation_config=_COMPUTATION_CONFIG,
            ephemeris_identity=_EPHEMERIS_IDENTITY,
        )
        session.commit()
        client_id = client.id

    samples = []
    try:
        with authenticated_client() as http:
            for index in range(total_runs):
                sample = measure_run(http, client_id, month=_MONTH, capture_markdown=index < 5)
                samples.append(sample)
                with capsys.disabled():  # a crash later must not lose what was measured
                    print(
                        f"run {index + 1}/{total_runs}: draft {sample.draft_seconds:.1f}s "
                        f"attempts {sample.max_attempt + 1} sections "
                        f"{[round(t, 1) for t in sample.section_seconds]} "
                        f"pdf {sample.pdf_first_seconds:.2f}s/{sample.pdf_repeat_seconds:.3f}s "
                        f"{sample.failure or ''}",
                        flush=True,
                    )
    finally:
        with Session(engine) as session:
            leftover = session.get(Client, client_id)
            if leftover is not None:
                delete_client_and_derived(session, client=leftover)
                session.commit()

    ok = [s for s in samples if s.failure is None]
    failed = [s for s in samples if s.failure is not None]
    assert len(ok) >= _MIN_EPIC10_RUNS_OK, (
        f"only {len(ok)}/{total_runs} runs succeeded: {[s.failure for s in failed]}"
    )
    assert ok[0].draft_seconds > 5, (
        f"the first draft took {ok[0].draft_seconds:.1f}s -- that is the recorded "
        "generator, not real Gemini; refusing to record it"
    )

    assert any(s.section_seconds for s in ok), "no Section timing was observed"
    draft_p90 = nearest_rank_p90([s.draft_seconds for s in ok])
    section_p90 = nearest_rank_p90([t for s in ok for t in s.section_seconds])
    regen = [s for s in ok if s.max_attempt == 1]
    if regen:
        one_regen = nearest_rank_p90([s.draft_seconds for s in regen])
        basis = "observed"
    else:
        one_regen = bound_one_regen_seconds(draft_p90, section_p90)
        basis = "bound"
    pdf_first = nearest_rank_p90([s.pdf_first_seconds for s in ok])
    pdf_repeat = nearest_rank_p90([s.pdf_repeat_seconds for s in ok])
    saved = save_reports(ok, REPO_ROOT / "cache" / "latency-reports")

    lines = ["", "=" * 72, f"Epic 10 latency -- {len(ok)}/{total_runs} runs ok", "=" * 72, ""]
    lines.append(f"{'run':>4} {'draft s':>9} {'attempts':>9} {'pdf 1st':>9} {'pdf 2nd':>9}")
    for index, s in enumerate(samples):
        lines.append(
            f"{index + 1:>4} {s.draft_seconds:>9.1f} {s.max_attempt + 1:>9} "
            f"{s.pdf_first_seconds:>9.2f} {s.pdf_repeat_seconds:>9.3f}"
            + (f"  FAILED: {s.failure}" if s.failure else "")
        )
        lines.extend(f"        - {violation}" for violation in s.violations)
    lines += ["", "Repeated six-word runs across Sections (saved reports):"]
    lines += [
        f"  {path.name}: {repeated_shingle_count(path.read_text(encoding='utf-8'))}"
        for path in saved
    ]
    lines += [
        "",
        "```toml",
        f"runs_ok = {len(ok)}",
        f"draft_p90_seconds = {ceil_tenth(draft_p90)}",
        f"section_p90_seconds = {ceil_tenth(section_p90)}",
        f"one_regen_p90_seconds = {ceil_tenth(one_regen)}",
        f'one_regen_basis = "{basis}"',
        f"regen_runs_observed = {len(regen)}",
        f"pdf_first_p90_seconds = {ceil_tenth(pdf_first)}",
        f"pdf_repeat_p90_seconds = {math.ceil(pdf_repeat * 1000) / 1000}",
        "```",
        "",
    ]
    with capsys.disabled():
        print("\n".join(lines))
