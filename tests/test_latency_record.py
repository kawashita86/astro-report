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

``test_measure_latency`` is the harness: 40 end-to-end ``drive()`` runs
through ``RecordedResponseGenerator`` plus an isolated full-month transit
scan, each timed with ``time.perf_counter()``. It never asserts on elapsed
time -- timings are environment-dependent data, not pass/fail -- only that
every run reaches ``gate_passed`` with ``failed_at is None`` (the throughput
guarantee). It is skipped unless ``RUN_LATENCY_MEASUREMENT=1`` so the
default ``uv run pytest`` stays fast; run it deliberately as a release
action and paste its printed block into ``latency.md``.
"""

from __future__ import annotations

import datetime
import math
import os
import re

import pytest

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

#: The minimum live-Gemini generation sample size the composed per-Report p90
#: may rest on (Boundaries: ``real_gen_sample_n >= 5``).
_MIN_REAL_GEN_SAMPLE_N = 5

#: The throughput target NFR-5 states: forty Reports in a single working
#: session.
_SESSION_REPORTS_TARGET = 40

_EXPECTED_KEYS = {
    "checked",
    "ratified_by",
    "ratified_on",
    "environment",
    "report_p90_seconds",
    "report_budget_seconds",
    "local_stage_p90_seconds",
    "real_gen_sample_n",
    "real_gen_p90_seconds",
    "month_scan_p90_seconds",
    "month_scan_budget_seconds",
    "session_reports",
    "sitting_confirmed",
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
        "report_p90_seconds",
        "report_budget_seconds",
        "local_stage_p90_seconds",
        "real_gen_sample_n",
        "real_gen_p90_seconds",
        "month_scan_p90_seconds",
        "month_scan_budget_seconds",
        "session_reports",
    ):
        assert isinstance(meta[key], int), (
            f"`{key}` must be a whole-number integer (whole seconds / a count), "
            f"got {meta[key]!r}"
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


@pytest.mark.xfail(
    strict=True,
    reason="epic-8-retro-item-65: latency.md honestly records outcome = "
    '"blocked" -- AC-4\'s human half (Francesco\'s forty-report one-sitting '
    "produce -> review -> export) has not happened, so `sitting_confirmed` is "
    "false. When that sitting is done and the field flips to true this test "
    "passes -> xfail_strict fires an XPASS -> remove this marker.",
)
def test_outcome_permits_release(meta: dict[str, object]) -> None:
    assert_outcome_permits_release(
        meta,
        evidence_field="sitting_confirmed",
        evidence_value=True,
        record_label="latency",
    )
    assert meta["outcome"] == "pass", (
        "release blocked until latency is measured, budgets reconciled and the "
        f'record ratified (outcome = {meta["outcome"]!r}, expected "pass")'
    )


def test_report_p90_within_budget(meta: dict[str, object]) -> None:
    # NFR-5 says "under 3 minutes" -- strict; a p90 equal to the budget
    # violates the requirement text, so this is `<`, not `<=`.
    assert meta["report_p90_seconds"] < meta["report_budget_seconds"], (
        f"measured per-Report p90 {meta['report_p90_seconds']}s is not under the "
        f"recorded budget {meta['report_budget_seconds']}s -- reconcile the "
        "budget (revise NFR-5 in epics.md and the PRD to the ratified value) "
        "rather than leaving it unmet"
    )


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
    assert (
        epics_seconds == meta["month_scan_budget_seconds"] == _MONTH_SCAN_BUDGET_SECONDS
    ), (
        f"NFR-10 bound in epics.md is {epics_seconds}s, record "
        f"month_scan_budget_seconds is {meta['month_scan_budget_seconds']}s, this "
        f"suite expects {_MONTH_SCAN_BUDGET_SECONDS}s -- all three must agree"
    )


def test_composed_p90_consistent(meta: dict[str, object]) -> None:
    composed = meta["local_stage_p90_seconds"] + meta["real_gen_p90_seconds"]
    assert meta["report_p90_seconds"] == composed, (
        f"report_p90_seconds {meta['report_p90_seconds']}s != "
        f"local_stage_p90_seconds {meta['local_stage_p90_seconds']}s + "
        f"real_gen_p90_seconds {meta['real_gen_p90_seconds']}s = {composed}s -- "
        "the per-Report p90 is the documented sum of its two measured parts"
    )


def test_real_gen_sample_present(meta: dict[str, object]) -> None:
    assert meta["real_gen_sample_n"] >= _MIN_REAL_GEN_SAMPLE_N, (
        f"real_gen_sample_n {meta['real_gen_sample_n']} is below the minimum "
        f"{_MIN_REAL_GEN_SAMPLE_N} -- the composed per-Report p90 must rest on a "
        "live-Gemini generation sample, not a placeholder"
    )
    assert meta["real_gen_p90_seconds"] > 0, (
        "real_gen_p90_seconds must be a positive measured value -- "
        "RecordedResponseGenerator makes no network call, so real generation "
        "latency has to be sampled separately"
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
    from shell.runner.driver import drive
    from shell.runner.month import client_month_interval_utc
    from tests.test_runner_driver import (
        _COMPUTATION_CONFIG,
        _EPHEMERIS_IDENTITY,
        _NATAL_CHART_ID,
        _RESOLVED_PLACE,
        _SECTIONS_CONFIG,
        _STYLE_GUIDE_CONTENT,
        _VOCABULARY,
        _a_natal_chart,
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
            result = drive(
                session,
                run,
                natal_chart=natal_chart,
                natal_chart_id=_NATAL_CHART_ID,
                config=_COMPUTATION_CONFIG,
                ephemeris_identity=_EPHEMERIS_IDENTITY,
                sections_config=_SECTIONS_CONFIG,
                generator=generator,
                vocabulary=_VOCABULARY,
            )
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
            find_transit_aspects(
                natal_chart, month_start_utc, month_end_utc, _COMPUTATION_CONFIG
            )
            find_stations(month_start_utc, month_end_utc, _COMPUTATION_CONFIG)
            find_ingresses(natal_chart, month_start_utc, month_end_utc, _COMPUTATION_CONFIG)
            find_lunations(natal_chart, month_start_utc, month_end_utc)
            scan_seconds.append(time.perf_counter() - started)

    local_stage_p90 = _nearest_rank_p90(run_seconds)
    month_scan_p90 = _nearest_rank_p90(scan_seconds)
    local_stage_p90_seconds = math.ceil(local_stage_p90)
    month_scan_p90_seconds = math.ceil(month_scan_p90)

    lines = [
        "",
        "=" * 72,
        f"Latency measurement -- {_RUN_COUNT} end-to-end runs + "
        f"{_RUN_COUNT} isolated month scans",
        "=" * 72,
        "",
        f"{'run':>4}  {'end-to-end (s)':>16}  {'month scan (s)':>16}",
    ]
    for index in range(_RUN_COUNT):
        lines.append(
            f"{index + 1:>4}  {run_seconds[index]:>16.4f}  {scan_seconds[index]:>16.4f}"
        )
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
            "Paste-ready block for docs/release-validation/latency.md (fill the",
            "real_gen_* keys from a live-Gemini sample of n >= 5, then set",
            "report_p90_seconds = local_stage_p90_seconds + real_gen_p90_seconds",
            "and outcome once reconciled):",
            "",
            "```toml",
            f"checked = {datetime.date.today().isoformat()}",
            'ratified_by = "Francesco"',
            f"ratified_on = {datetime.date.today().isoformat()}",
            'environment = "local in-process harness (SQLite stand-in, '
            'RecordedResponseGenerator) + live-Gemini sample"',
            f"report_budget_seconds = {_REPORT_BUDGET_SECONDS}",
            f"local_stage_p90_seconds = {local_stage_p90_seconds}",
            "real_gen_sample_n = 0",
            "real_gen_p90_seconds = 0",
            f"report_p90_seconds = {local_stage_p90_seconds}",
            f"month_scan_budget_seconds = {_MONTH_SCAN_BUDGET_SECONDS}",
            f"month_scan_p90_seconds = {month_scan_p90_seconds}",
            f"session_reports = {_RUN_COUNT}",
            "sitting_confirmed = false",
            'outcome = "blocked"',
            "```",
            "",
        ]
    )
    with capsys.disabled():
        print("\n".join(lines))
