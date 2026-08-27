"""`alembic upgrade head` reaches a real Postgres from an empty database.

``tests/test_migration_chain.py`` drives Alembic in *offline* mode: it emits the
upgrade SQL and executes none of it, so a statement Postgres would reject still
passes there. SQLite, where the adapter tests run, ignores ``VARCHAR(n)`` length
entirely. Between them, a revision id longer than ``alembic_version.version_num``
(``VARCHAR(32)``) shipped green for three epics: ``alembic upgrade head`` had
never actually run against Postgres from a clean database.

This test does. It runs the real online upgrade -- the same path
``docker-entrypoint.sh`` takes -- against a throwaway Postgres named by
``MIGRATION_TEST_DATABASE_URL``, and skips when that is unset. CI sets it to a
service-container database (see ``.github/workflows/ci.yml``); locally,
``docker compose up -d postgres`` and point it at that instance.

WARNING: the target's ``public`` schema is dropped and recreated on every run.
Never point ``MIGRATION_TEST_DATABASE_URL`` at a database whose contents matter.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

#: Tables that live behind the revision the VARCHAR(32) ceiling used to block
#: (``0014``). If the chain stops short, at least one of these is absent.
TABLES_BEHIND_THE_OLD_BLOCK = ("export_record", "backup_record", "corpus_entry")


def _database_url() -> str:
    url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "set MIGRATION_TEST_DATABASE_URL to a throwaway Postgres URL to run "
            "the real-Postgres migration test (its public schema is reset on "
            "each run)"
        )
    return url


def _libpq_url(url: str) -> str:
    """psycopg wants a plain ``postgresql://`` DSN, not SQLAlchemy's
    ``postgresql+psycopg://`` dialect form."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _expected_head() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _reset_public_schema(url: str) -> None:
    with psycopg.connect(_libpq_url(url), autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


def run_online_upgrade(url: str) -> subprocess.CompletedProcess[str]:
    """Drive `alembic upgrade head` for real -- executes env.py's online path."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from alembic.config import main; main(argv=['upgrade', 'head'])",
        ],
        cwd=REPO_ROOT,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(REPO_ROOT),
            "ENVIRONMENT": "local",
            "DATABASE_URL": url,
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


def test_upgrade_head_reaches_the_head_from_an_empty_database() -> None:
    url = _database_url()
    _reset_public_schema(url)

    completed = run_online_upgrade(url)
    assert completed.returncode == 0, completed.stderr

    with psycopg.connect(_libpq_url(url)) as conn:
        stamped = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchall()
        }

    assert stamped is not None
    assert stamped[0] == _expected_head()
    missing = [name for name in TABLES_BEHIND_THE_OLD_BLOCK if name not in tables]
    assert not missing, f"chain stopped short; missing tables: {missing}"


def test_a_second_upgrade_is_a_no_op() -> None:
    url = _database_url()
    _reset_public_schema(url)

    first = run_online_upgrade(url)
    assert first.returncode == 0, first.stderr

    second = run_online_upgrade(url)
    assert second.returncode == 0, second.stderr

    with psycopg.connect(_libpq_url(url)) as conn:
        stamped = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert stamped is not None
    assert stamped[0] == _expected_head()
