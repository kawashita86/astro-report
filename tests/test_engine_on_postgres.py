"""The app engine's connection bounds, checked against a real Postgres.

The Coolify pool-exhaustion fix (spec-fix-db-pool-exhaustion) sets
``statement_timeout`` with a ``SET`` in a pool ``connect`` listener. Whether
that ``SET`` survives the pool's reset-on-return rollback is driver and
server behaviour that the in-memory SQLite suite and the fake DBAPI connection in
``tests/test_http_app.py`` cannot show. Like
``tests/test_migration_chain_on_postgres.py`` this skips unless
``MIGRATION_TEST_DATABASE_URL`` points at a throwaway Postgres; it creates
nothing there.
"""

from __future__ import annotations

import dataclasses
import os

import pytest
from sqlalchemy import text

from shell.config import Environment, Settings
from shell.http.app import create_app

_SETTINGS = Settings(
    environment=Environment.LOCAL,
    database_url="postgresql://unused@localhost:5432/unused",
    port=8000,
    auth_password_hash="$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA",
    session_secret_key="x" * 32,
    gemini_api_key="test-gemini-api-key",
    gemini_data_terms_verified_at="2026-01-15",
)


def _database_url() -> str:
    url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "set MIGRATION_TEST_DATABASE_URL to a throwaway Postgres URL to run "
            "the real-Postgres engine-bounds test"
        )
    return url


def test_every_checkout_carries_the_statement_timeout() -> None:
    application = create_app(dataclasses.replace(_SETTINGS, database_url=_database_url()))
    engine = application.state.engine
    try:
        # Two checkouts of the same pooled connection: the second proves the
        # `SET` survived the reset-on-return rollback between them.
        for _ in range(2):
            with engine.connect() as connection:
                timeout = connection.execute(text("SHOW statement_timeout")).scalar_one()
                assert timeout == "30s"
    finally:
        engine.dispose()
