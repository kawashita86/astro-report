"""The Epic 10 latency harness (Story 10.7), kept out of the guard module so that
``tests/test_latency_record.py`` stays a readable list of guards.

It exists because Epic 10 moved the latency that matters out of one in-process
call and into a background driver, parallel Section generation and a stored-PDF
cache -- none of which an in-process harness exercises. So this drives the
*running* local docker app over HTTP, the way Francesco's browser does, and reads
Section completion times out of Postgres. Draft time is the span from the start
POST to ``gate_passed``; a Section's time is its lease claim to the moment its
row is seen ``complete`` (polled at ``_POLL_SECONDS``, so each figure reads up to
that much high, never low). The pure helpers (p90, repetition count, regeneration
basis) are separate functions so they can be tested without a network.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx2
import psycopg

from shell.http.auth import SESSION_COOKIE_NAME, sign_session
from tests._release_validation import REPO_ROOT

__all__ = [
    "RunSample",
    "bound_one_regen_seconds",
    "ceil_tenth",
    "local_session_secret",
    "measure_run",
    "nearest_rank_p90",
    "repeated_shingle_count",
]

BASE_URL = "http://localhost:8000"
DATABASE_URL = "postgresql://astro:astro@localhost:5432/astro_report"

_POLL_SECONDS = 0.2
_RUN_TIMEOUT_SECONDS = 600.0
_FINISHED_STAGES = ("gate_passed", "exported")
_SHINGLE_WORDS = 6
_SECRET_LINE = re.compile(r"^\s*SESSION_SECRET_KEY:\s*(\S+)\s*$", re.MULTILINE)


@dataclass
class RunSample:
    """What one end-to-end run measured."""

    run_id: UUID
    draft_seconds: float = 0.0
    section_seconds: list[float] = field(default_factory=list)
    max_attempt: int = 0
    pdf_first_seconds: float = 0.0
    pdf_repeat_seconds: float = 0.0
    failure: str | None = None
    violations: list[str] = field(default_factory=list)
    markdown: str = ""


def nearest_rank_p90(samples: list[float]) -> float:
    """Nearest-rank p90, as every other record in this suite computes it."""
    ordered = sorted(samples)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


def ceil_tenth(value: float) -> float:
    """Round *up* to a tenth of a second: a recorded figure never reads lower than measured."""
    return math.ceil(value * 10 - 1e-9) / 10


def bound_one_regen_seconds(draft_p90: float, section_p90: float) -> float:
    """The regeneration figure when none was observed: a regenerated Section, then
    Consiglio finale, run one after the other."""
    return ceil_tenth(draft_p90 + 2 * section_p90)


def repeated_shingle_count(markdown: str) -> int:
    """How many six-word runs appear under more than one ``##`` heading -- a naive
    but honest signal of repetition between Sections for Francesco to look at."""
    sections = re.split(r"^##\s+", markdown, flags=re.MULTILINE)[1:]
    seen: dict[tuple[str, ...], set[int]] = {}
    for index, body in enumerate(sections):
        words = re.findall(r"\w+", body.lower())
        for start in range(len(words) - _SHINGLE_WORDS + 1):
            seen.setdefault(tuple(words[start : start + _SHINGLE_WORDS]), set()).add(index)
    return sum(1 for owners in seen.values() if len(owners) > 1)


def local_session_secret() -> str:
    """The committed local-dev session secret from ``compose.yaml`` -- public in the
    repo by design, so minting a local session cookie reads nothing private."""
    match = _SECRET_LINE.search((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert match is not None, "compose.yaml has no SESSION_SECRET_KEY line"
    return match.group(1)


def authenticated_client() -> httpx2.Client:
    """An HTTP client carrying a valid session cookie for the local app."""
    token = sign_session(int(time.time()) + 3600, local_session_secret())
    return httpx2.Client(
        base_url=BASE_URL,
        cookies={SESSION_COOKIE_NAME: token},
        timeout=120.0,
        follow_redirects=False,
    )


def app_is_up() -> bool:
    try:
        return httpx2.get(f"{BASE_URL}/healthz", timeout=3.0).status_code in (200, 204)
    except httpx2.HTTPError:
        return False


def _observe(
    conn: psycopg.Connection[Any],
    run_id: UUID,
    seen: dict[tuple[int, int], float],
    sample: RunSample,
) -> tuple[str | None, bool]:
    """One poll: record any Section newly seen complete; return (stage, failed)."""
    now = datetime.now(UTC)
    stage, failed_at = conn.execute(
        "select stage, failed_at from report_run where id = %s", (run_id,)
    ).fetchone() or (None, None)
    for attempt, ordinal, status, claimed_at in conn.execute(
        "select attempt, ordinal, status, claimed_at from report_draft_section "
        "where report_run_id = %s",
        (run_id,),
    ):
        sample.max_attempt = max(sample.max_attempt, attempt)
        key = (attempt, ordinal)
        if status == "complete" and key not in seen and claimed_at is not None:
            seen[key] = (now - claimed_at).total_seconds()
    return stage, failed_at is not None


def measure_run(
    http: httpx2.Client,
    client_id: UUID,
    *,
    month: str,
    capture_markdown: bool,
    clock: Callable[[], float] = time.perf_counter,
) -> RunSample:
    """Drive one report from start to PDF and return what was timed. A run that
    fails or times out is returned with ``failure`` set and is excluded upstream."""
    started = clock()
    response = http.post(f"/clients/{client_id}/report-runs", data={"month": month})
    assert response.status_code == 303, f"start returned {response.status_code}"
    run_id = UUID(response.headers["location"].rsplit("/", 1)[1])
    sample = RunSample(run_id=run_id)
    seen: dict[tuple[int, int], float] = {}
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        while True:
            stage, failed = _observe(conn, run_id, seen, sample)
            if failed:
                (reason,) = conn.execute(
                    "select failure_reason from report_run where id = %s", (run_id,)
                ).fetchone()
                sample.failure = f"stage {stage!r}: {str(reason)[:160]}"
                for (violations,) in conn.execute(
                    "select violations from gate_result where report_run_id = %s "
                    "order by created_at desc limit 1",
                    (run_id,),
                ):
                    sample.violations = [
                        f"{v['kind']}: {v['sentence'][:140]} || {v['detail'][:120]}"
                        for v in violations
                    ]
                return sample
            if stage in _FINISHED_STAGES:
                sample.draft_seconds = clock() - started
                break
            if clock() - started > _RUN_TIMEOUT_SECONDS:
                sample.failure = f"timed out at stage {stage!r}"
                return sample
            time.sleep(_POLL_SECONDS)
    sample.section_seconds = list(seen.values())

    for attribute in ("pdf_first_seconds", "pdf_repeat_seconds"):
        pdf_started = clock()
        pdf = http.get(f"/report-runs/{run_id}/export/pdf")
        setattr(sample, attribute, clock() - pdf_started)
        if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF"):
            sample.failure = f"PDF export returned {pdf.status_code}"
            return sample
    if capture_markdown:
        sample.markdown = http.get(f"/report-runs/{run_id}/export/markdown").text
    return sample


def save_reports(samples: list[RunSample], directory: Path) -> list[Path]:
    """Write each captured report's Markdown under ``directory`` for side-by-side reading."""
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, sample in enumerate(s for s in samples if s.markdown):
        path = directory / f"after-epic-10-{index + 1}.md"
        path.write_text(sample.markdown, encoding="utf-8")
        paths.append(path)
    return paths
