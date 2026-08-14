"""Migrations complete before the service accepts traffic, and a failure aborts.

Render's pre-deploy command is a paid-instance feature, so the ordering lives in
the container entrypoint instead. That makes the ordering a property of two
files rather than of a platform setting — and a property nobody would notice
losing, because an image whose migrations run *after* the server starts still
boots, still passes a health check, and still serves the previous schema.

This is a structural test on purpose: it asserts the ordering the entrypoint
encodes, so a reordering is caught in the test run rather than in a deploy.
Every check reads *code* rather than raw text, because a comment describing the
right behavior must never be able to satisfy an assertion about it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "docker-entrypoint.sh"
DOCKERFILE = REPO_ROOT / "Dockerfile"


def strip_comments(script: str) -> list[str]:
    """Executable lines only: whole-line and trailing ``#`` comments removed.

    The entrypoint documents its own ordering in a header comment that names
    ``alembic upgrade head``. Matching against raw text would let that comment
    stand in for the command it describes.
    """
    lines: list[str] = []
    for raw in script.splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        lines.append(line)
    return lines


@pytest.fixture(scope="module")
def entrypoint() -> str:
    assert ENTRYPOINT.exists(), "the entrypoint that orders migrations before traffic is gone"
    return ENTRYPOINT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(entrypoint: str) -> list[str]:
    return strip_comments(entrypoint)


def line_index(code: list[str], predicate) -> int | None:
    for index, line in enumerate(code):
        if predicate(line):
            return index
    return None


def errexit_is_enabled(code: list[str]) -> tuple[bool, int | None]:
    """Resolve the final state of ``-e``, honouring long form and later ``set +e``.

    Returns ``(enabled, index_of_first_enabling_line)``.
    """
    enabled = False
    first_enabled_at: int | None = None

    for index, line in enumerate(code):
        tokens = line.strip().split()
        if not tokens or tokens[0] != "set":
            continue

        position = 1
        while position < len(tokens):
            token = tokens[position]
            if token in ("-o", "+o"):
                option = tokens[position + 1] if position + 1 < len(tokens) else ""
                if option == "errexit":
                    enabled = token == "-o"
                    if enabled and first_enabled_at is None:
                        first_enabled_at = index
                position += 2
                continue
            if token.startswith(("-", "+")) and "e" in token[1:]:
                enabled = token.startswith("-")
                if enabled and first_enabled_at is None:
                    first_enabled_at = index
            position += 1

    return enabled, first_enabled_at


# --- A failed migration aborts the deploy -------------------------------------


def test_errexit_is_in_force(code: list[str]) -> None:
    """`set -e` is what turns a failed migration into a failed deploy — matrix row 6."""
    enabled, _ = errexit_is_enabled(code)

    assert enabled, (
        "the entrypoint does not leave `-e` in force; a failed migration would "
        "fall through and the server would start against an unmigrated database"
    )


def test_errexit_is_in_force_before_the_migration(code: list[str]) -> None:
    """Enabling it after the migration protects nothing."""
    _, enabled_at = errexit_is_enabled(code)
    upgrade_at = line_index(code, lambda line: "alembic upgrade head" in line)

    assert enabled_at is not None
    assert upgrade_at is not None, "the entrypoint no longer applies migrations"
    assert enabled_at < upgrade_at, (
        "`-e` is enabled after migrations run; a failure before that point "
        "would be swallowed"
    )


def test_the_errexit_parser_understands_the_forms_it_must() -> None:
    """The guard is worthless if it cannot tell these apart."""
    assert errexit_is_enabled(["set -eu"])[0]
    assert errexit_is_enabled(["set -e"])[0]
    assert errexit_is_enabled(["set -o errexit"])[0]
    assert errexit_is_enabled(["set -eu", "set +e"])[0] is False
    assert errexit_is_enabled(["set -o errexit", "set +o errexit"])[0] is False
    assert errexit_is_enabled(["set -u"])[0] is False
    assert errexit_is_enabled(["set"])[0] is False  # bare `set` must not crash
    assert errexit_is_enabled(["set -o"])[0] is False  # nor a truncated one


# --- Ordering -----------------------------------------------------------------


def test_migrations_run_before_the_server(code: list[str]) -> None:
    """Ordering, not merely presence: upgrade must precede the exec."""
    upgrade_at = line_index(code, lambda line: "alembic upgrade head" in line)
    exec_at = line_index(code, lambda line: line.strip().startswith("exec "))

    assert upgrade_at is not None, "the entrypoint no longer applies migrations"
    assert exec_at is not None, "the entrypoint never execs the server"
    assert upgrade_at < exec_at, (
        "the server is exec'd before migrations are applied; traffic would be "
        "accepted against an unmigrated database"
    )


def test_a_comment_cannot_satisfy_the_ordering_check() -> None:
    """Proof that stripping comments is doing real work."""
    only_a_comment = "#!/bin/sh\nset -eu\n# alembic upgrade head\nexec \"$@\"\n"
    code = strip_comments(only_a_comment)

    assert line_index(code, lambda line: "alembic upgrade head" in line) is None


def test_the_server_replaces_the_shell(code: list[str]) -> None:
    """`exec` keeps the container to a single process, as the image promises."""
    assert line_index(code, lambda line: line.strip().startswith("exec ")) is not None, (
        "the server is started without exec; the shell would remain as PID 1"
    )


# --- Everything that can fail cheaply fails before the irreversible step -------


def test_the_port_is_validated_before_migrations(code: list[str]) -> None:
    """`set -u` on an unset PORT would abort *after* the database was migrated."""
    port_check_at = line_index(code, lambda line: "PORT" in line)
    upgrade_at = line_index(code, lambda line: "alembic upgrade head" in line)

    assert port_check_at is not None, "the entrypoint never checks PORT"
    assert upgrade_at is not None
    assert port_check_at < upgrade_at, (
        "PORT is only touched after migrations run; an unset PORT would leave "
        "the schema ahead of any code that is serving"
    )


def test_a_missing_command_is_refused(code: list[str]) -> None:
    """`exec "$@"` with no arguments migrates, exits 0, and serves nothing."""
    guard_at = line_index(code, lambda line: '"$#"' in line or "$#" in line)
    upgrade_at = line_index(code, lambda line: "alembic upgrade head" in line)

    assert guard_at is not None, (
        "the entrypoint does not check that a command was given; a deleted CMD "
        "would make it migrate and then exit successfully without serving"
    )
    assert upgrade_at is not None
    assert guard_at < upgrade_at


# --- The image invokes it -----------------------------------------------------


def test_the_image_runs_through_the_entrypoint() -> None:
    """An entrypoint that the image does not invoke enforces nothing."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    entrypoint_line = next(
        (line for line in dockerfile.splitlines() if line.startswith("ENTRYPOINT")),
        None,
    )

    assert entrypoint_line is not None, "the image declares no ENTRYPOINT"
    assert ENTRYPOINT.name in entrypoint_line, (
        f"the image's ENTRYPOINT does not invoke {ENTRYPOINT.name}: {entrypoint_line!r}"
    )


def test_the_image_declares_the_command_the_entrypoint_execs() -> None:
    """Without a CMD the entrypoint has nothing to exec — the P7(b) failure mode."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    cmd_line = next(
        (line for line in dockerfile.splitlines() if line.startswith("CMD")), None
    )

    assert cmd_line is not None, "the image declares no CMD; the entrypoint would serve nothing"
    assert "shell.http.app:app" in cmd_line, (
        f"the image's CMD does not start the application: {cmd_line!r}"
    )
