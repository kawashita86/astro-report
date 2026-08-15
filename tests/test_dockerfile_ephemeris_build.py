"""The built image can actually compile ``pyswisseph`` and ship the ephemeris.

Neither property is exercised by ``uv run pytest`` against a checkout: the repo
checkout already has ``data/ephemeris/`` on disk regardless of what the
Dockerfile does, and no test here invokes Docker. Without a structural check on
the Dockerfile itself, deleting the ``COPY data/ ./data/`` line or the
``build-essential`` install would stay green in this suite and only surface at
an actual deploy — this test closes that gap the same way
``test_migrations_precede_traffic.py`` already does for the migration ordering.

Every check reads *code* (Dockerfile instruction lines with comments stripped),
never raw text, so a comment describing the right behavior can't satisfy an
assertion about it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"


def strip_comments(dockerfile: str) -> list[str]:
    lines: list[str] = []
    for raw in dockerfile.splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        lines.append(line)
    return lines


@pytest.fixture(scope="module")
def code() -> list[str]:
    assert DOCKERFILE.exists(), "the Dockerfile the image is built from is gone"
    return strip_comments(DOCKERFILE.read_text(encoding="utf-8"))


def line_index(lines: list[str], predicate) -> int | None:
    for index, line in enumerate(lines):
        if predicate(line):
            return index
    return None


def test_the_ephemeris_data_directory_is_copied_into_the_image(code: list[str]) -> None:
    copy_at = line_index(code, lambda line: line.startswith("COPY") and "data/" in line)

    assert copy_at is not None, (
        "no COPY line ships data/ into the image; the vendored ephemeris and its "
        "manifest would be missing at runtime regardless of what's committed"
    )


def test_a_compiler_is_installed_before_uv_sync(code: list[str]) -> None:
    """``pyswisseph`` has no prebuilt wheel; ``uv sync`` compiles it from source."""
    compiler_at = line_index(code, lambda line: "build-essential" in line)
    sync_at = line_index(code, lambda line: "uv sync" in line)

    assert compiler_at is not None, (
        "no build-essential (or equivalent compiler) install found; uv sync would "
        "fail to build pyswisseph from its sdist-only distribution"
    )
    assert sync_at is not None, "the image never runs uv sync"
    assert compiler_at < sync_at, (
        "the compiler is installed after uv sync already ran; the build that "
        "needs it would already have failed"
    )


def test_a_comment_cannot_satisfy_the_compiler_check() -> None:
    """Proof that stripping comments is doing real work."""
    only_a_comment = (
        "FROM python:3.13-slim\n# RUN apt-get install -y build-essential\nRUN uv sync\n"
    )
    code = strip_comments(only_a_comment)

    assert line_index(code, lambda line: "build-essential" in line) is None
