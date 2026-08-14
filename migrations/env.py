"""Alembic runtime environment.

The connection URL comes from ``shell/config.py`` — the one reader of the
environment — so a deploy with a missing or malformed ``DATABASE_URL`` fails in
the migration step, before anything is asked to serve traffic.

The URL is deliberately *not* written into the Alembic config object. That path
runs through ``ConfigParser``, which performs pyformat interpolation and rejects
any value containing a bare ``%`` — and percent-encoding is routine in generated
Postgres passwords (``%40`` for ``@``). Passing the URL straight to the engine
and to ``context.configure`` keeps it out of the ini layer entirely.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from shell.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No models exist yet: the baseline revision establishes the chain only.
# Later stories set this to the SQLModel metadata.
target_metadata = None


def run_migrations_offline() -> None:
    """Emit SQL to a script rather than running it against a live database."""
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = create_engine(settings.sqlalchemy_url, poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
