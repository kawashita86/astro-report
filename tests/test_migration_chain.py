"""The migration chain resolves, and `env.py` runs.

Loading revision files one at a time proves each is well-formed and says nothing
about whether they form a chain. A second revision with ``down_revision = None``,
or one naming a parent that does not exist, is a perfectly valid Python module —
it fails at ``alembic upgrade head``, during a deploy, after the image is built.

These tests drive Alembic itself: they resolve the real ``ScriptDirectory`` the
way the entrypoint does, and run an offline upgrade that executes ``migrations/
env.py`` without needing a live Postgres.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import Script, ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
VERSIONS_DIR = REPO_ROOT / "migrations" / "versions"


@pytest.fixture(scope="module")
def script_directory() -> ScriptDirectory:
    assert ALEMBIC_INI.is_file(), "alembic.ini is missing; nothing would be migrated"
    config = Config(str(ALEMBIC_INI))
    # Resolve the location absolutely: relative resolution depends on the
    # working directory, and the test run's is not the container's.
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def revision_files() -> list[Path]:
    """Every revision on disk, including any in nested version directories."""
    return [
        path
        for path in sorted(VERSIONS_DIR.rglob("*.py"))
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    ]


# --- The chain resolves -------------------------------------------------------


def test_exactly_one_head(script_directory: ScriptDirectory) -> None:
    """Two heads make `upgrade head` ambiguous and abort the deploy."""
    heads = script_directory.get_heads()

    assert len(heads) == 1, (
        f"expected a single head, found {heads}. Two revisions share a parent; "
        "merge them before this reaches a deploy."
    )


def test_exactly_one_base(script_directory: ScriptDirectory) -> None:
    """A second base means a revision forgot its parent and is silently orphaned."""
    bases = script_directory.get_bases()

    assert len(bases) == 1, (
        f"expected a single base, found {bases}. A revision has "
        "down_revision = None when it should name its parent."
    )


def test_the_chain_is_linear_and_complete(script_directory: ScriptDirectory) -> None:
    """Walking head to base must visit every revision file exactly once."""
    head = script_directory.get_current_head()
    assert head is not None

    walked: list[Script] = list(script_directory.walk_revisions("base", head))

    assert len(walked) == len(revision_files()), (
        f"{len(revision_files())} revision files exist but {len(walked)} are "
        "reachable from head; one is orphaned or on a branch."
    )
    for revision in walked:
        assert not isinstance(revision.down_revision, tuple), (
            f"{revision.revision} is a merge revision; the chain is meant to be linear."
        )


def test_every_revision_file_is_known_to_alembic(
    script_directory: ScriptDirectory,
) -> None:
    """A file Alembic cannot see is a migration that will never run."""
    known = {revision.revision for revision in script_directory.walk_revisions()}

    assert known, "no revisions found; the guard would pass vacuously"
    assert len(known) == len(revision_files())


def test_the_baseline_is_the_base(script_directory: ScriptDirectory) -> None:
    assert list(script_directory.get_bases()) == ["0001_baseline"]


def test_no_revision_id_exceeds_the_alembic_version_column_width(
    script_directory: ScriptDirectory,
) -> None:
    """Alembic stores the current revision id in ``alembic_version.version_num``,
    a ``VARCHAR(32)`` it creates and never widens. A longer id is accepted on
    SQLite (which ignores the length) but throws ``StringDataRightTruncation`` on
    Postgres the moment ``alembic upgrade`` tries to stamp it -- so every
    migration behind it is unreachable on a real deploy. ``0014`` was 42 chars
    and blocked the entire Epic 6-8 chain; this guard keeps it from recurring.
    """
    over_long = {
        revision.revision
        for revision in script_directory.walk_revisions()
        if len(revision.revision) > 32
    }

    assert not over_long, (
        f"revision id(s) longer than 32 chars: {sorted(over_long)}. "
        "alembic_version.version_num is VARCHAR(32); a longer id fails at "
        "`alembic upgrade head` against Postgres. Shorten the id (and re-point "
        "its child's down_revision)."
    )


# --- env.py actually runs -----------------------------------------------------


def run_offline_upgrade(database_url: str) -> subprocess.CompletedProcess[str]:
    """Drive `alembic upgrade head --sql`, which executes env.py without a database."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from alembic.config import main; main(argv=['upgrade', 'head', '--sql'])",
        ],
        cwd=REPO_ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(REPO_ROOT),
            "ENVIRONMENT": "local",
            "DATABASE_URL": database_url,
            "PORT": "8000",
            "AUTH_PASSWORD_HASH": (
                "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
                "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
            ),
            "SESSION_SECRET_KEY": "test-session-secret-key-at-least-32-chars-long",
            "GEMINI_API_KEY": "test-gemini-api-key",
            "GEMINI_DATA_TERMS_VERIFIED_AT": "2026-01-15",
        },
        capture_output=True,
        text=True,
    )


def test_an_offline_upgrade_runs_env_py_and_emits_the_chain() -> None:
    completed = run_offline_upgrade(
        "postgresql://astro:astro@db.example.eu:5432/astro_report"
    )

    assert completed.returncode == 0, completed.stderr
    assert "CREATE TABLE alembic_version" in completed.stdout
    assert "0001_baseline" in completed.stdout
    # 0002_place_cache: the hand-written migration SQL is never exercised by
    # tests/test_place_cache.py, which builds its schema from the SQLModel
    # class directly -- this is the only check tying the two together.
    assert "CREATE TABLE place_cache" in completed.stdout
    assert "CREATE UNIQUE INDEX ix_place_cache_normalized_query" in completed.stdout
    # 0003_client_and_natal_chart: same reasoning -- ties the hand-written DDL
    # to the Client/StoredNatalChart SQLModel classes it must match, so a
    # schema drift (a wrong `nullable`, a missing column, a dropped index)
    # would fail here rather than pass silently.
    assert "CREATE TABLE client" in completed.stdout
    assert "CREATE TABLE natal_chart" in completed.stdout
    assert "CREATE INDEX ix_natal_chart_client_id" in completed.stdout
    # 0007_style_guide: seeds version 1 from data/style-guide.seed.md inside
    # the same upgrade() -- no adapter-level test exercises this migration's
    # own INSERT (those tests build their schema via SQLModel.create_all()
    # instead), so this is the only check that the seed actually lands.
    assert "CREATE TABLE style_guide" in completed.stdout
    assert "CREATE UNIQUE INDEX ix_style_guide_version" in completed.stdout
    assert "INSERT INTO style_guide" in completed.stdout
    assert "## Purpose and how to read this guide" in completed.stdout
    # 0008_report_theme: the unique index is "exactly one StoredReportTheme
    # per ReportRun" (Story 4.3) enforced at the schema level -- same
    # reasoning as 0006_report_payload's own unique index above.
    assert "CREATE TABLE report_theme" in completed.stdout
    assert "CREATE UNIQUE INDEX ix_report_theme_report_run_id" in completed.stdout
    # 0021_gate_vocabulary_hash: one nullable VARCHAR(64) column added to each
    # of report/gate_result (epic-5-retro item 45) -- no adapter-level test
    # exercises this migration's own ALTER TABLE (those build their schema via
    # SQLModel.create_all()), so this is the only check tying the hand-written
    # add-column SQL to the model fields it must match.
    assert (
        "ALTER TABLE report ADD COLUMN gate_vocabulary_content_hash VARCHAR(64)"
        in completed.stdout
    )
    assert (
        "ALTER TABLE gate_result ADD COLUMN vocabulary_content_hash VARCHAR(64)"
        in completed.stdout
    )


def test_a_percent_encoded_password_does_not_abort_the_migration() -> None:
    """Regression: routing the URL through ConfigParser broke every such deploy.

    ``config.set_main_option("sqlalchemy.url", ...)`` performs pyformat
    interpolation and raises ``ValueError: invalid interpolation syntax`` on a
    bare ``%`` — and ``%40`` for ``@`` is routine in generated Postgres
    passwords. env.py passes the URL straight to the engine instead.
    """
    completed = run_offline_upgrade(
        "postgresql://astro:p%40ss%25word@db.example.eu:5432/astro_report"
    )

    assert completed.returncode == 0, completed.stderr
    assert "interpolation" not in completed.stderr
    assert "CREATE TABLE alembic_version" in completed.stdout


def test_an_invalid_database_url_aborts_the_migration_step() -> None:
    """The deploy must die here, before the server is exec'd — matrix row 6."""
    completed = run_offline_upgrade("mysql://astro:astro@localhost:3306/astro_report")

    assert completed.returncode != 0
    assert "DATABASE_URL" in completed.stderr
