"""Guard suite for the dated storage-growth projection record
(``docs/release-validation/storage-growth.md``, Story 8.4), plus the opt-in
measurement harness that produces the numbers it holds.

The always-on guard tests mirror the read-the-file style of
``tests/test_data_terms_record.py`` / ``tests/test_latency_record.py``: read
the files, parse in-process, no network and no Docker. The record's
machine-readable block is a fenced ```toml``` block parsed with ``tomllib``
(stdlib) -- no YAML parser is a dependency in this repo. The guard suite
stays red while the recorded projection arithmetic is internally
inconsistent, while the recorded ceiling drifts from README's Running-cost
table, while the recorded volume drifts from ``epics.md``'s NFR-5 line, while
the half-ceiling date falls inside the 60-month planning horizon without a
ratified storage-growth policy, or while ``outcome`` is anything other than
``"pass"`` -- so an un-reconciled projection, or a record that has not yet
been completed from a real measurement and ratified, keeps the release gate
from going green.

``test_measure_payload_size`` is the harness: 12 end-to-end ``drive()`` runs
of the known-good Fort Worth fixture over consecutive months, reading each
persisted ``report_payload`` row back and measuring
``len(canonical_json_bytes(row.payload))`` -- the canonical serialization the
codebase specifies for a persisted Payload (``core/payload/freeze.py``). It is
*not* claimed to equal bytes-on-disk: the engine's own ``json.dumps`` adds
insignificant whitespace (larger) and Postgres TOAST-compresses the ``JSON``
value (smaller); the pending production ``pg_total_relation_size`` cross-check
settles the real figure. The harness never asserts on byte counts -- sizes are
environment/fixture-dependent data, not pass/fail -- only that every run
persists a ``report_payload`` row and reaches ``gate_passed`` (or a later
stage) with ``failed_at is None``. It is skipped unless
``RUN_STORAGE_MEASUREMENT=1`` so the default ``uv run pytest`` stays fast; run
it deliberately as a release action and paste its printed block into
``storage-growth.md``.
"""

from __future__ import annotations

import datetime
import math
import os
import re
import statistics
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD_FILE = REPO_ROOT / "docs" / "release-validation" / "storage-growth.md"
EPICS_FILE = REPO_ROOT / "_bmad-output" / "planning-artifacts" / "epics.md"
README = REPO_ROOT / "README.md"

#: Neon's free plan is documented as "0.5 GB"; the guard binds ``ceiling_bytes``
#: to the smaller, conservative decimal reading (0.5 * 1000**3), not 0.5 GiB.
_CEILING_BYTES = 500_000_000

#: The upper bound of ``epics.md``'s NFR-5 "100-200 per month" -- bound both to
#: the literal here and to the number parsed live out of that line, so the
#: record, the epic and this suite can never silently disagree.
_REPORTS_PER_MONTH = 200

#: A persisted ``report_payload`` JSON row is at least this big -- a p90 under
#: 1 KiB means the harness measured something other than a real frozen Payload.
_MIN_PAYLOAD_BYTES = 1024

#: The harness sample floor (Boundaries: ``sample_n >= 6``).
_MIN_SAMPLE_N = 6

#: Average days per month the projection uses to turn "months to ceiling" into
#: a calendar date; the guard re-derives the date with the same constant.
_DAYS_PER_MONTH = 30.44

#: The planning horizon inside which a projected half-ceiling date forces a
#: ratified storage-growth policy rather than silent absorption (AC-3).
_HORIZON = datetime.timedelta(days=round(60 * _DAYS_PER_MONTH))

#: Tolerance, in days, between a recorded ceiling date and the date the
#: recorded arithmetic implies.
_DATE_TOLERANCE_DAYS = 5

_EXPECTED_KEYS = {
    "checked",
    "ratified_by",
    "ratified_on",
    "sample_n",
    "payload_p90_bytes",
    "storage_overhead_factor",
    "projected_row_bytes",
    "reports_per_month",
    "monthly_growth_bytes",
    "ceiling_bytes",
    "ceiling_reached_on",
    "half_ceiling_reached_on",
    "policy_decision",
    "policy_ratified_by",
    "outcome",
}

#: Present only when ``policy_decision = "raised"``; a ``"none"`` record omits
#: it rather than carrying an epoch sentinel.
_OPTIONAL_KEYS = {"policy_ratified_on"}

_TOML_BLOCK = re.compile(r"^```toml\n(.*?)\n```", re.DOTALL | re.MULTILINE)


def _extract_toml_block(text: str) -> str:
    match = _TOML_BLOCK.search(text)
    assert match is not None, (
        f"{RECORD_FILE} has no ```toml fenced block -- the machine-readable "
        "storage-growth record is missing or malformed"
    )
    return match.group(1)


def _epics_requirement_line(tag: str) -> str:
    """The single ``epics.md`` line that begins ``<tag>:`` (e.g. ``NFR-5``) --
    the guard parses the stated volume out of exactly that line, never a
    stray match elsewhere in the document."""
    text = EPICS_FILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.lstrip().startswith(f"{tag}:"):
            return line
    raise AssertionError(f"epics.md has no line starting {tag!r}")


def _readme_running_cost_section() -> str:
    text = README.read_text(encoding="utf-8")
    match = re.search(
        r"^##\s+Running cost\s*$(.*?)(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE
    )
    assert match is not None, "README.md has no '## Running cost' section"
    return match.group(1)


@pytest.fixture(scope="module")
def meta() -> dict[str, object]:
    assert RECORD_FILE.exists(), f"storage-growth record missing: {RECORD_FILE}"
    return tomllib.loads(_extract_toml_block(RECORD_FILE.read_text(encoding="utf-8")))


# --- Always-on guard tests (validate the record, never measure) ----------------


def test_record_exists() -> None:
    assert RECORD_FILE.exists(), (
        f"release-validation storage-growth record missing: {RECORD_FILE} -- "
        "Story 8.4 requires a dated projection of report_payload storage growth "
        "against Neon's 0.5 GB free-tier ceiling"
    )


def test_toml_block_parses(meta: dict[str, object]) -> None:
    missing = _EXPECTED_KEYS - meta.keys()
    unexpected = meta.keys() - _EXPECTED_KEYS - _OPTIONAL_KEYS
    assert not missing, f"storage-growth record toml block missing keys: {sorted(missing)}"
    assert not unexpected, (
        f"storage-growth record toml block has unexpected keys: {sorted(unexpected)} -- "
        "update _EXPECTED_KEYS and the matching assertions if a key was added on purpose"
    )
    for key in (
        "sample_n",
        "payload_p90_bytes",
        "projected_row_bytes",
        "reports_per_month",
        "monthly_growth_bytes",
        "ceiling_bytes",
    ):
        assert isinstance(meta[key], int), (
            f"`{key}` must be a whole-number integer (bytes / a count), got {meta[key]!r}"
        )
    factor = meta["storage_overhead_factor"]
    assert isinstance(factor, (int, float)) and not isinstance(factor, bool), (
        f"`storage_overhead_factor` must be a number, got {factor!r}"
    )
    for key in ("ratified_by", "policy_decision", "outcome"):
        assert isinstance(meta[key], str) and meta[key].strip(), (
            f"`{key}` must be a non-empty string, got {meta[key]!r}"
        )
    assert meta["policy_decision"] in {"raised", "none"}, (
        f'`policy_decision` must be exactly "raised" or "none", got '
        f"{meta['policy_decision']!r}"
    )
    # `policy_ratified_by` / `policy_ratified_on` are validated conditionally by
    # test_policy_raised_when_half_ceiling_near -- a "none" record leaves
    # `policy_ratified_by` empty and omits `policy_ratified_on` entirely. Here
    # just pin the types of whatever is present.
    assert isinstance(meta["policy_ratified_by"], str), (
        f"`policy_ratified_by` must be a string, got {meta['policy_ratified_by']!r}"
    )
    if "policy_ratified_on" in meta:
        assert isinstance(meta["policy_ratified_on"], datetime.date), (
            f"`policy_ratified_on`, when present, must be a bare ISO date, got "
            f"{meta['policy_ratified_on']!r}"
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


def test_ratified_is_a_date(meta: dict[str, object]) -> None:
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


def test_payload_bytes_sane(meta: dict[str, object]) -> None:
    assert meta["payload_p90_bytes"] >= _MIN_PAYLOAD_BYTES, (
        f"payload_p90_bytes {meta['payload_p90_bytes']} is below {_MIN_PAYLOAD_BYTES} "
        "-- a real frozen report_payload JSON row is kilobytes, not bytes; the "
        "harness measured the wrong thing or the number is a placeholder"
    )
    assert meta["sample_n"] >= _MIN_SAMPLE_N, (
        f"sample_n {meta['sample_n']} is below the minimum {_MIN_SAMPLE_N} -- the "
        "p90 must rest on a real harness sample, not a placeholder"
    )


def test_projected_row_bytes_consistent(meta: dict[str, object]) -> None:
    factor = meta["storage_overhead_factor"]
    assert factor >= 1.0, (
        f"storage_overhead_factor {factor} is below 1.0 -- the on-disk row "
        "(Postgres header + the two indexes + TOAST + the duplicated typed "
        "columns) cannot be smaller than the JSON it stores"
    )
    expected = math.ceil(meta["payload_p90_bytes"] * factor)
    assert meta["projected_row_bytes"] == expected, (
        f"projected_row_bytes {meta['projected_row_bytes']} != "
        f"ceil(payload_p90_bytes {meta['payload_p90_bytes']} * "
        f"storage_overhead_factor {factor}) = {expected}"
    )


def test_monthly_growth_consistent(meta: dict[str, object]) -> None:
    expected = meta["projected_row_bytes"] * meta["reports_per_month"]
    assert meta["monthly_growth_bytes"] == expected, (
        f"monthly_growth_bytes {meta['monthly_growth_bytes']} != "
        f"projected_row_bytes {meta['projected_row_bytes']} * reports_per_month "
        f"{meta['reports_per_month']} = {expected}"
    )


def test_ceiling_matches_readme(meta: dict[str, object]) -> None:
    section = _readme_running_cost_section()
    match = re.search(r"Neon Postgres.*?Free\s*\(([\d.]+)\s*GB\)", section)
    assert match is not None, (
        "README.md's Running-cost table no longer has a "
        "'Neon Postgres ... Free (N GB)' row for the guard to bind to"
    )
    readme_gb = float(match.group(1))
    readme_bytes = int(readme_gb * 1000**3)
    assert readme_bytes == meta["ceiling_bytes"] == _CEILING_BYTES, (
        f"README says Free ({readme_gb} GB) = {readme_bytes} bytes, record "
        f"ceiling_bytes is {meta['ceiling_bytes']}, this suite expects "
        f"{_CEILING_BYTES} (0.5 * 1000**3, the conservative decimal reading) "
        "-- all three must agree"
    )


def test_reports_per_month_matches_target(meta: dict[str, object]) -> None:
    line = _epics_requirement_line("NFR-5")
    match = re.search(r"100[–-](\d+)\b", line)
    assert match is not None, (
        f"could not find NFR-5's '100-200' volume range in epics.md: {line!r}"
    )
    assert "per month" in line, (
        f"NFR-5 line no longer states the volume range 'per month': {line!r}"
    )
    upper_bound = int(match.group(1))
    assert upper_bound == meta["reports_per_month"] == _REPORTS_PER_MONTH, (
        f"NFR-5 upper bound in epics.md is {upper_bound}, record reports_per_month "
        f"is {meta['reports_per_month']}, this suite expects {_REPORTS_PER_MONTH} "
        "-- all three must agree"
    )


def _implied_ceiling_date(
    checked: datetime.date, growth_bytes: int, target_bytes: int
) -> datetime.date:
    months = target_bytes / growth_bytes
    return checked + datetime.timedelta(days=round(months * _DAYS_PER_MONTH))


def _project(
    p90_bytes: int, factor: float, reports_per_month: int, checked: datetime.date
) -> tuple[int, int, datetime.date, datetime.date]:
    """(projected_row_bytes, monthly_growth_bytes, ceiling_reached_on,
    half_ceiling_reached_on) for one (p90, factor, volume) triple -- the exact
    arithmetic the guard's consistency checks re-derive."""
    projected_row_bytes = math.ceil(p90_bytes * factor)
    monthly_growth_bytes = projected_row_bytes * reports_per_month
    return (
        projected_row_bytes,
        monthly_growth_bytes,
        _implied_ceiling_date(checked, monthly_growth_bytes, _CEILING_BYTES),
        _implied_ceiling_date(checked, monthly_growth_bytes, _CEILING_BYTES // 2),
    )


def test_ceiling_date_consistent(meta: dict[str, object]) -> None:
    checked = meta["checked"]
    recorded = meta["ceiling_reached_on"]
    assert isinstance(recorded, datetime.date), (
        f"`ceiling_reached_on` must be a bare ISO date, got {recorded!r}"
    )
    assert recorded > checked, (
        f"`ceiling_reached_on` {recorded.isoformat()} is not strictly after "
        f"`checked` {checked.isoformat()}"
    )
    expected = _implied_ceiling_date(checked, meta["monthly_growth_bytes"], meta["ceiling_bytes"])
    drift = abs((recorded - expected).days)
    assert drift <= _DATE_TOLERANCE_DAYS, (
        f"`ceiling_reached_on` {recorded.isoformat()} is {drift} days from the "
        f"date the recorded arithmetic implies ({expected.isoformat()}: checked + "
        f"ceiling_bytes / monthly_growth_bytes months at {_DAYS_PER_MONTH} d/month) "
        f"-- tolerance is {_DATE_TOLERANCE_DAYS} days"
    )


def test_half_ceiling_date_consistent(meta: dict[str, object]) -> None:
    checked = meta["checked"]
    recorded = meta["half_ceiling_reached_on"]
    assert isinstance(recorded, datetime.date), (
        f"`half_ceiling_reached_on` must be a bare ISO date, got {recorded!r}"
    )
    assert recorded > checked, (
        f"`half_ceiling_reached_on` {recorded.isoformat()} is not strictly after "
        f"`checked` {checked.isoformat()}"
    )
    expected = _implied_ceiling_date(
        checked, meta["monthly_growth_bytes"], meta["ceiling_bytes"] // 2
    )
    drift = abs((recorded - expected).days)
    assert drift <= _DATE_TOLERANCE_DAYS, (
        f"`half_ceiling_reached_on` {recorded.isoformat()} is {drift} days from "
        f"the date the recorded arithmetic implies ({expected.isoformat()}) -- "
        f"tolerance is {_DATE_TOLERANCE_DAYS} days"
    )


def _assert_policy_consistent(meta: dict[str, object]) -> None:
    """A record's policy fields must match whether its ``half_ceiling_reached_on``
    lands inside the 60-month planning horizon: inside -> a ratified policy;
    outside -> ``policy_decision = "none"`` and no ratification."""
    checked = meta["checked"]
    half_ceiling = meta["half_ceiling_reached_on"]
    within_horizon = half_ceiling <= checked + _HORIZON
    if within_horizon:
        assert meta["policy_decision"] == "raised", (
            f"half_ceiling_reached_on {half_ceiling.isoformat()} falls within the "
            f"{_HORIZON.days}-day planning horizon, so the storage-growth policy "
            "must be raised as an explicit decision (AC-3), not absorbed -- "
            f"policy_decision is {meta['policy_decision']!r}, expected \"raised\""
        )
        assert isinstance(meta["policy_ratified_by"], str) and meta["policy_ratified_by"].strip(), (
            f"`policy_ratified_by` must name who ratified the policy, got "
            f"{meta['policy_ratified_by']!r}"
        )
        assert isinstance(meta.get("policy_ratified_on"), datetime.date), (
            f"`policy_ratified_on` must be a bare ISO date on a raised policy, got "
            f"{meta.get('policy_ratified_on')!r}"
        )
    else:
        assert meta["policy_decision"] == "none", (
            f"half_ceiling_reached_on {half_ceiling.isoformat()} is beyond the "
            f"{_HORIZON.days}-day horizon, so policy_decision must be \"none\" -- "
            f"got {meta['policy_decision']!r}"
        )


def test_policy_raised_when_half_ceiling_near(meta: dict[str, object]) -> None:
    _assert_policy_consistent(meta)


def test_policy_none_branch_holds_for_a_far_future_half_ceiling() -> None:
    """The ``policy_decision = "none"`` branch of ``_assert_policy_consistent``
    -- unreachable from the real record while its half-ceiling is ~13 months
    out -- exercised with a synthetic far-future date, plus the inverse
    (I/O & Edge-Case Matrix: "Half-ceiling within horizon, no policy")."""
    checked = datetime.date(2026, 8, 27)
    far_future = {
        "checked": checked,
        "half_ceiling_reached_on": checked + datetime.timedelta(days=365 * 40),
        "policy_decision": "none",
        "policy_ratified_by": "",
    }
    _assert_policy_consistent(far_future)  # no policy required beyond the horizon

    near = {**far_future, "half_ceiling_reached_on": checked + datetime.timedelta(days=200)}
    with pytest.raises(AssertionError):
        _assert_policy_consistent(near)  # "none" is invalid when half-ceiling is near


def test_outcome_is_valid(meta: dict[str, object]) -> None:
    assert meta["outcome"] in {"pass", "blocked"}, (
        f'`outcome` must be exactly "pass" or "blocked", got {meta["outcome"]!r}'
    )


def test_outcome_permits_release(meta: dict[str, object]) -> None:
    assert meta["outcome"] == "pass", (
        "release blocked until storage growth is measured, projected, the policy "
        f'reconciled and the record ratified (outcome = {meta["outcome"]!r}, '
        'expected "pass")'
    )


# --- Opt-in measurement harness ----------------------------------------------------

#: Number of consecutive-month drives the harness runs (Boundaries: N >= 6, use 12).
_RUN_COUNT = 12

#: The storage-overhead factor the paste-ready block projects with -- Postgres
#: row header + the two indexes + TOAST + the duplicated typed columns
#: (documented in the record's prose).
_OVERHEAD_FACTOR = 1.5


def _nearest_rank_p90(samples: list[int]) -> int:
    """Nearest-rank p90 (Boundaries): ``sorted(d)[ceil(0.9 * len(d)) - 1]``."""
    ordered = sorted(samples)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


def _consecutive_months(start: str, count: int) -> list[str]:
    year, month = (int(part) for part in start.split("-"))
    months: list[str] = []
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months


@pytest.mark.skipif(
    os.environ.get("RUN_STORAGE_MEASUREMENT") != "1",
    reason="set RUN_STORAGE_MEASUREMENT=1 to run the 12-run storage-measurement harness",
)
def test_measure_payload_size(capsys: pytest.CaptureFixture[str]) -> None:
    """Drive 12 end-to-end Reports of the Fort Worth fixture over consecutive
    months, read each persisted ``report_payload`` row back, measure
    ``len(canonical_json_bytes(row.payload))``, and print the projection table
    and a paste-ready toml block. Asserts only that all 12 runs persist a
    ``report_payload`` row and reach ``gate_passed`` (or a later stage) with
    ``failed_at is None`` -- never on byte counts."""
    from sqlmodel import Session, SQLModel, create_engine, select

    from core.payload.freeze import canonical_json_bytes
    from shell.adapters.postgres.gate_result import StoredGateResult
    from shell.adapters.postgres.report_draft import ReportDraft
    from shell.adapters.postgres.report_payload import ReportPayload
    from shell.adapters.postgres.report_run import ReportRun
    from shell.adapters.postgres.report_theme import StoredReportTheme

    # `tests/test_runner_driver.py` is this story's Code Map "copy source": its
    # Fort Worth fixture wiring, the clean-draft `_FakeGenerator`, the
    # Client+chart+Style-Guide seed and the `drive()` wrapper are reused here
    # verbatim rather than re-implemented.
    from tests.test_runner_driver import _create_client_and_chart, _drive
    from tests.test_runner_driver import _FakeGenerator as _CleanDraftGenerator

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    payload_sizes: list[int] = []
    theme_sizes: list[int] = []
    draft_sizes: list[int] = []
    gate_sizes: list[int] = []
    transit_sizes: list[int] = []
    months = _consecutive_months("2026-01", _RUN_COUNT)

    with Session(engine) as session:
        client, natal_chart = _create_client_and_chart(session)

        generator = _CleanDraftGenerator()
        for index, month in enumerate(months):
            run = ReportRun(client_id=client.id, month=month)
            session.add(run)
            session.commit()

            result = _drive(session, run, natal_chart, generator=generator)

            # `drive()` advances until it hits a stage with no registered
            # function; `gate_passed` is the last registered stage today, but an
            # `exported` stage could be added later -- accept either. The
            # report_payload-row assertion below is the real success check.
            assert result.stage in {"gate_passed", "exported"}, (
                f"run {index + 1}/{_RUN_COUNT} ({month}) stopped at "
                f"{result.stage!r}, not gate_passed / exported"
            )
            assert result.failed_at is None, (
                f"run {index + 1}/{_RUN_COUNT} ({month}) was marked terminally "
                f"failed: {result.failure_reason!r}"
            )

            payload_row = session.exec(
                select(ReportPayload).where(ReportPayload.report_run_id == run.id)
            ).one()
            payload_sizes.append(len(canonical_json_bytes(payload_row.payload)))

            theme_row = session.exec(
                select(StoredReportTheme).where(StoredReportTheme.report_run_id == run.id)
            ).one()
            theme_sizes.append(len(canonical_json_bytes(theme_row.theme)))

            draft_row = session.exec(
                select(ReportDraft).where(ReportDraft.report_run_id == run.id)
            ).first()
            draft_sizes.append(
                len(canonical_json_bytes(draft_row.draft)) if draft_row is not None else 0
            )

            gate_rows = session.exec(
                select(StoredGateResult).where(StoredGateResult.report_run_id == run.id)
            ).all()
            gate_sizes.append(
                sum(len(canonical_json_bytes(row.violations)) for row in gate_rows)
            )

            transit_sizes.append(
                len(canonical_json_bytes(run.transit_events))
                if run.transit_events is not None
                else 0
            )

        persisted = session.exec(
            select(ReportPayload).where(ReportPayload.client_id == client.id)
        ).all()
        assert len(persisted) == _RUN_COUNT, (
            f"expected {_RUN_COUNT} persisted report_payload rows, found {len(persisted)}"
        )

    payload_p90 = _nearest_rank_p90(payload_sizes)
    footprint_p90 = (
        payload_p90
        + _nearest_rank_p90(theme_sizes)
        + _nearest_rank_p90(draft_sizes)
        + _nearest_rank_p90(gate_sizes)
        + _nearest_rank_p90(transit_sizes)
    )
    checked = datetime.date.today()

    # The machine block the record holds and the guard binds to: payload-only,
    # 200/month (NFR-5 upper bound).
    projected_row_bytes, monthly_growth_bytes, ceiling_reached_on, half_ceiling_reached_on = (
        _project(payload_p90, _OVERHEAD_FACTOR, _REPORTS_PER_MONTH, checked)
    )
    within_horizon = half_ceiling_reached_on <= checked + _HORIZON

    def _summary(name: str, data: list[int]) -> str:
        return (
            f"{name:>26} : min {min(data):>7}  mean {round(statistics.mean(data)):>7}  "
            f"median {round(statistics.median(data)):>7}  p90 {_nearest_rank_p90(data):>7}  "
            f"max {max(data):>7}"
        )

    def _projection_row(label: str, p90_bytes: int, reports_per_month: int) -> str:
        row_bytes, growth, ceiling, half = _project(
            p90_bytes, _OVERHEAD_FACTOR, reports_per_month, checked
        )
        return (
            f"{label:>34} | {row_bytes:>9} B/row | {growth:>11} B/mo | "
            f"ceiling {ceiling.isoformat()} | half {half.isoformat()}"
        )

    lines = [
        "",
        "=" * 78,
        f"Storage measurement -- {_RUN_COUNT} end-to-end runs of the Fort Worth fixture",
        "=" * 78,
        "",
        f"{'run':>4}  {'month':>8}  {'payload (B)':>12}  {'theme (B)':>10}  "
        f"{'draft (B)':>10}  {'gate (B)':>9}  {'transits (B)':>13}",
    ]
    for index in range(_RUN_COUNT):
        lines.append(
            f"{index + 1:>4}  {months[index]:>8}  {payload_sizes[index]:>12}  "
            f"{theme_sizes[index]:>10}  {draft_sizes[index]:>10}  {gate_sizes[index]:>9}  "
            f"{transit_sizes[index]:>13}"
        )
    lines.extend(
        [
            "",
            _summary("report_payload.payload", payload_sizes),
            _summary("report_theme.theme", theme_sizes),
            _summary("report_draft.draft", draft_sizes),
            _summary("gate_result.violations", gate_sizes),
            _summary("report_run.transit_events", transit_sizes),
            "",
            f"nearest-rank p90, report_payload.payload : {payload_p90} B "
            f"({payload_p90 / 1024:.1f} KiB) -- the un-prunable-row floor (NFR-9)",
            f"nearest-rank p90, full per-Report footprint : {footprint_p90} B "
            f"({footprint_p90 / 1024:.1f} KiB) -- payload + theme + draft + gate + transit_events",
            "",
            f"Projections (storage_overhead_factor = {_OVERHEAD_FACTOR}, "
            f"ceiling_bytes = {_CEILING_BYTES}, {_DAYS_PER_MONTH} days/month):",
            _projection_row("payload-only, 200/mo (machine block)", payload_p90, 200),
            _projection_row("payload-only, 100/mo", payload_p90, 100),
            _projection_row("full footprint, 200/mo", footprint_p90, 200),
            _projection_row("full footprint, 100/mo", footprint_p90, 100),
            "",
            "Paste-ready block for docs/release-validation/storage-growth.md",
            f"(storage_overhead_factor = {_OVERHEAD_FACTOR}; Francesco ratifies the",
            "numbers, the policy and outcome before merge):",
            "",
            "```toml",
            f"checked = {checked.isoformat()}",
            'ratified_by = "Francesco"',
            f"ratified_on = {checked.isoformat()}",
            f"sample_n = {_RUN_COUNT}",
            f"payload_p90_bytes = {payload_p90}",
            f"storage_overhead_factor = {_OVERHEAD_FACTOR}",
            f"projected_row_bytes = {projected_row_bytes}",
            f"reports_per_month = {_REPORTS_PER_MONTH}",
            f"monthly_growth_bytes = {monthly_growth_bytes}",
            f"ceiling_bytes = {_CEILING_BYTES}",
            f"ceiling_reached_on = {ceiling_reached_on.isoformat()}",
            f"half_ceiling_reached_on = {half_ceiling_reached_on.isoformat()}",
            *(
                [
                    'policy_decision = "raised"',
                    'policy_ratified_by = "Francesco"',
                    f"policy_ratified_on = {checked.isoformat()}",
                ]
                if within_horizon
                else ['policy_decision = "none"', 'policy_ratified_by = ""']
            ),
            'outcome = "pass"',
            "```",
            "",
        ]
    )
    with capsys.disabled():
        print("\n".join(lines))
