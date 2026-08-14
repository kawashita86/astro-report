"""The single reader of the process environment.

This module is the *only* place in the codebase permitted to touch ``os.environ``
(AD "Configuration" in the architecture spine, enforced by
``tests/test_env_access_is_centralized.py``). Every other module receives a
:class:`Settings` instance, never the environment it came from.

The environment supplies **deployment** facts only. Astronomical tuning values
live in ``data/computation.toml`` and are passed explicitly as a
``ComputationConfig`` (AD-18); they never enter through here.

Loading happens at import time so that a misconfigured process dies before it can
serve anything: importing this module with a missing or invalid variable raises
:class:`ConfigError`, which propagates as a non-zero exit.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

__all__ = ["ConfigError", "Environment", "Settings", "load_settings", "settings"]


class ConfigError(RuntimeError):
    """A required setting is missing, or a supplied setting is invalid.

    Raised at startup only. There is no degraded configuration to fall back to:
    the process refuses to serve rather than serving with a guessed value.
    """


class Environment(StrEnum):
    """The two environments that exist. There is deliberately no staging."""

    LOCAL = "local"
    PRODUCTION = "production"


#: URL schemes accepted for ``DATABASE_URL``. All durable state lives in Postgres
#: (AD-11), so a non-Postgres URL is a configuration error rather than a choice.
_POSTGRES_SCHEMES: tuple[str, ...] = (
    "postgres",
    "postgresql",
    "postgresql+psycopg",
)

#: The SQLAlchemy dialect this project drives Postgres through.
_SQLALCHEMY_SCHEME = "postgresql+psycopg"

_MIN_PORT = 1
_MAX_PORT = 65535


@dataclass(frozen=True, repr=False)
class Settings:
    """Every deployment fact this process was given, validated and frozen.

    Frozen in the mechanical sense: assigning to an attribute raises
    ``dataclasses.FrozenInstanceError``. Configuration is decided once, at
    startup, and cannot drift while the process runs.

    The repr is written by hand rather than generated, because the generated one
    prints ``database_url`` in full — and that string carries the production
    database password. A settings object reaches a traceback, a log line or a
    debugger far too easily for that to be acceptable, and this project's logging
    rule forbids carrying secrets. The value stays available on the attribute;
    only its rendering is redacted.
    """

    environment: Environment
    database_url: str
    port: int

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(environment={self.environment!r}, "
            f"database_url={self.redacted_database_url!r}, port={self.port!r})"
        )

    @property
    def redacted_database_url(self) -> str:
        """``database_url`` with any password replaced — safe to print or log."""
        parts = urlsplit(self.database_url)
        if parts.password is None:
            return self.database_url
        host = parts.hostname or ""
        if parts.port is not None:
            host = f"{host}:{parts.port}"
        return parts._replace(netloc=f"{parts.username or ''}:***@{host}").geturl()

    @property
    def sqlalchemy_url(self) -> str:
        """``database_url`` with the scheme pinned to the psycopg 3 dialect.

        Hosted Postgres providers hand out ``postgresql://`` URLs, which
        SQLAlchemy resolves to the psycopg 2 dialect that this project does not
        install. Normalizing here keeps the raw operator-supplied value intact on
        :attr:`database_url` while giving engine construction an unambiguous one.
        """
        parts = urlsplit(self.database_url)
        return parts._replace(scheme=_SQLALCHEMY_SCHEME).geturl()


def _read_required(
    environ: Mapping[str, str], name: str, hint: str
) -> tuple[str | None, str | None]:
    """Return ``(value, error)``; an unset or blank variable is a missing one."""
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return None, f"{name} is required but was not set. {hint}"
    return raw.strip(), None


def _read_environment(environ: Mapping[str, str]) -> tuple[Environment | None, str | None]:
    permitted = ", ".join(member.value for member in Environment)
    raw, error = _read_required(
        environ, "ENVIRONMENT", f"Permitted values: {permitted}."
    )
    if error is not None:
        return None, error
    assert raw is not None
    try:
        return Environment(raw), None
    except ValueError:
        return None, (
            f"ENVIRONMENT is invalid: {raw!r} is not a recognized environment. "
            f"Permitted values: {permitted}."
        )


def _read_database_url(environ: Mapping[str, str]) -> tuple[str | None, str | None]:
    accepted = ", ".join(_POSTGRES_SCHEMES)
    raw, error = _read_required(
        environ,
        "DATABASE_URL",
        f"Set it to a Postgres connection URL using one of: {accepted}.",
    )
    if error is not None:
        return None, error
    assert raw is not None
    scheme = urlsplit(raw).scheme
    if scheme not in _POSTGRES_SCHEMES:
        return None, (
            f"DATABASE_URL is invalid: scheme {scheme or '(none)'!r} is not a Postgres "
            f"scheme. All durable state lives in Postgres; accepted schemes: {accepted}."
        )
    if not urlsplit(raw).netloc:
        return None, (
            "DATABASE_URL is invalid: the URL names no host. "
            f"Expected the form {scheme}://user:password@host/database."
        )
    return raw, None


def _read_port(environ: Mapping[str, str]) -> tuple[int | None, str | None]:
    raw, error = _read_required(
        environ,
        "PORT",
        f"Set it to the port this process should listen on ({_MIN_PORT}-{_MAX_PORT}). "
        "Hosting platforms supply this variable themselves.",
    )
    if error is not None:
        return None, error
    assert raw is not None
    try:
        port = int(raw)
    except ValueError:
        return None, f"PORT is invalid: {raw!r} is not an integer."
    if not _MIN_PORT <= port <= _MAX_PORT:
        return None, (
            f"PORT is invalid: {port} is outside the permitted range "
            f"{_MIN_PORT}-{_MAX_PORT}."
        )
    return port, None


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Validate ``environ`` into a frozen :class:`Settings`.

    Every variable is checked before anything is reported, so a first run against
    a blank environment names all of the offenders rather than one per attempt.

    Raises:
        ConfigError: naming each missing or invalid variable and why.
    """
    source: Mapping[str, str] = os.environ if environ is None else environ

    environment, environment_error = _read_environment(source)
    database_url, database_url_error = _read_database_url(source)
    port, port_error = _read_port(source)

    problems = [
        problem
        for problem in (environment_error, database_url_error, port_error)
        if problem is not None
    ]
    if problems:
        raise ConfigError(
            "Refusing to start: the environment is not a valid configuration.\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )

    assert environment is not None and database_url is not None and port is not None
    return Settings(environment=environment, database_url=database_url, port=port)


#: The configuration this process is running under. Built once, at import.
settings: Settings = load_settings()
