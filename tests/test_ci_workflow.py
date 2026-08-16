"""The CI workflow actually runs what it claims to (Story 1.6).

Structural tests on purpose, mirroring ``tests/test_dockerfile_ephemeris_build.py``:
a comment can describe the right behavior, but only reading the workflow's
own declared triggers and commands proves it. This also guards the specific
claim ``.github/workflows/ci.yml``'s header comment makes -- that its pinned
``uv`` version matches ``Dockerfile``'s -- since nothing else keeps the two
in sync if one is bumped without the other.

Every trigger check reads *code* (workflow lines with comments stripped, and
the ``push``/``pull_request`` triggers read from their own indented block
under ``on:``), never raw text, so a comment describing the right behavior
can't satisfy an assertion about it -- the epic-1 retrospective found the
raw-substring version of this file's push-trigger check would still pass
even if ``branches: [main]`` were changed to name a different branch,
because the file's own header comment already contains the word "main".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = REPO_ROOT / "Dockerfile"

_UV_VERSION_PATTERN = re.compile(r"uv==(\S+)")


def strip_comments(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        lines.append(line)
    return lines


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def block_under(lines: list[str], key: str) -> list[str]:
    """The lines indented under the first ``key:`` (or ``key: value``) line.

    Not a real YAML parser -- just enough nesting-awareness that a value
    living under a *different* top-level key (or outside any key at all,
    like a comment) can never satisfy a check scoped to this block.
    """
    key_indent = None
    start = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f"{key}:" or stripped.startswith(f"{key}:"):
            key_indent = indent_of(line)
            start = index + 1
            break
    if start is None:
        return []
    block: list[str] = []
    for line in lines[start:]:
        if indent_of(line) <= key_indent:
            break
        block.append(line)
    return block


def _uv_version(text: str) -> str:
    match = _UV_VERSION_PATTERN.search(text)
    assert match is not None, "no `uv==X.Y.Z` pin found"
    return match.group(1)


@pytest.fixture(scope="module")
def code() -> list[str]:
    assert CI_WORKFLOW.exists(), "no CI workflow -- conformance would be an on-demand check again"
    return strip_comments(CI_WORKFLOW.read_text(encoding="utf-8"))


def test_the_workflow_file_exists() -> None:
    assert CI_WORKFLOW.exists(), "no CI workflow -- conformance would be an on-demand check again"


def test_it_triggers_on_push_to_main(code: list[str]) -> None:
    on_block = block_under(code, "on")
    assert on_block, "no `on:` trigger block found"

    push_block = block_under(on_block, "push")
    assert push_block, "no `push:` trigger declared under `on:`"

    branches_lines = [line for line in push_block if "branches" in line]
    assert branches_lines, "`push:` trigger has no `branches:` filter"
    assert any(re.search(r"\bmain\b", line) for line in branches_lines), (
        f"push trigger's branches filter doesn't name `main`: {branches_lines!r}"
    )


def test_it_triggers_on_pull_request(code: list[str]) -> None:
    on_block = block_under(code, "on")
    assert on_block, "no `on:` trigger block found"

    assert any(line.strip() in ("pull_request:", "pull_request") for line in on_block), (
        "no `pull_request` trigger declared under `on:`"
    )


def test_it_runs_lint_and_the_full_test_suite(code: list[str]) -> None:
    steps_block = block_under(block_under(block_under(code, "jobs"), "test"), "steps")
    assert steps_block, "no `steps:` found under `jobs: -> test:`"

    run_lines = [line for line in steps_block if "run:" in line]
    assert any("uv run ruff check" in line for line in run_lines), (
        "no lint step runs `uv run ruff check`"
    )
    assert any("uv run pytest" in line for line in run_lines), (
        "no test step runs `uv run pytest`"
    )


def test_its_pinned_uv_version_matches_the_dockerfiles() -> None:
    """Nothing else keeps these two pins in sync if one is bumped alone."""
    ci_version = _uv_version(CI_WORKFLOW.read_text(encoding="utf-8"))
    dockerfile_version = _uv_version(DOCKERFILE.read_text(encoding="utf-8"))

    assert ci_version == dockerfile_version, (
        f"CI pins uv=={ci_version} but Dockerfile pins uv=={dockerfile_version} -- "
        "these should always move together"
    )


def test_it_declares_least_privilege_permissions(code: list[str]) -> None:
    assert any(line.strip() == "permissions:" for line in code), "no `permissions:` block declared"
    permissions_block = block_under(code, "permissions")
    assert any(line.strip() == "contents: read" for line in permissions_block), (
        "`permissions:` doesn't declare `contents: read`"
    )


def test_it_has_a_job_timeout(code: list[str]) -> None:
    test_block = block_under(block_under(code, "jobs"), "test")
    assert any(line.strip().startswith("timeout-minutes:") for line in test_block), (
        "the `test` job has no `timeout-minutes:`"
    )


def test_a_comment_cannot_satisfy_the_push_trigger_check() -> None:
    """Proof that stripping comments and scoping to the `on:`/`push:` block
    is doing real work -- the exact false-positive the epic-1 retrospective
    found in this file's previous, raw-substring version."""
    only_a_comment = (
        "# Runs on every push to main.\n"
        "on:\n"
        "  push:\n"
        "    branches: [develop]\n"
    )
    code_lines = strip_comments(only_a_comment)
    on_block = block_under(code_lines, "on")
    push_block = block_under(on_block, "push")
    branches_lines = [line for line in push_block if "branches" in line]

    assert not any(re.search(r"\bmain\b", line) for line in branches_lines)
