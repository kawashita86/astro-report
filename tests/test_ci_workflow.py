"""The CI workflow actually runs what it claims to (Story 1.6).

Structural tests on purpose, mirroring ``tests/test_dockerfile_ephemeris_build.py``:
a comment can describe the right behavior, but only reading the workflow's
own declared triggers and commands proves it. This also guards the specific
claim ``.github/workflows/ci.yml``'s header comment makes -- that its pinned
``uv`` version matches ``Dockerfile``'s -- since nothing else keeps the two
in sync if one is bumped without the other.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = REPO_ROOT / "Dockerfile"

_UV_VERSION_PATTERN = re.compile(r"uv==(\S+)")


def _uv_version(text: str) -> str:
    match = _UV_VERSION_PATTERN.search(text)
    assert match is not None, "no `uv==X.Y.Z` pin found"
    return match.group(1)


def test_the_workflow_file_exists() -> None:
    assert CI_WORKFLOW.exists(), "no CI workflow -- conformance would be an on-demand check again"


def test_it_triggers_on_push_to_main() -> None:
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "push:" in content
    assert "main" in content


def test_it_triggers_on_pull_request() -> None:
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request" in content


def test_it_runs_lint_and_the_full_test_suite() -> None:
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "uv run ruff check" in content
    assert "uv run pytest" in content


def test_its_pinned_uv_version_matches_the_dockerfiles() -> None:
    """Nothing else keeps these two pins in sync if one is bumped alone."""
    ci_version = _uv_version(CI_WORKFLOW.read_text(encoding="utf-8"))
    dockerfile_version = _uv_version(DOCKERFILE.read_text(encoding="utf-8"))

    assert ci_version == dockerfile_version, (
        f"CI pins uv=={ci_version} but Dockerfile pins uv=={dockerfile_version} -- "
        "these should always move together"
    )


def test_it_declares_least_privilege_permissions() -> None:
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:" in content
    assert "contents: read" in content


def test_it_has_a_job_timeout() -> None:
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "timeout-minutes:" in content
