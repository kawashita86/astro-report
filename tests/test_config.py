"""Configuration validation — the load-bearing behavior of the skeleton.

One test per row of the story's I/O and edge-case matrix, plus the two properties
the matrix implies: the settings object is frozen, and a process that imports
``shell.config`` with a bad environment dies with a non-zero exit.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from shell.config import ConfigError, Environment, Settings, load_settings

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Argon2 hash of "correct horse battery staple" — a fixed test password, never
#: a real one.
VALID_AUTH_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
)

VALID_ENVIRONMENT = {
    "ENVIRONMENT": "local",
    "DATABASE_URL": "postgresql://astro:astro@localhost:5432/astro_report",
    "PORT": "8000",
    "AUTH_PASSWORD_HASH": VALID_AUTH_PASSWORD_HASH,
    "SESSION_SECRET_KEY": "test-session-secret-key-at-least-32-chars-long",
    "GEMINI_API_KEY": "test-gemini-api-key",
    "GEMINI_DATA_TERMS_VERIFIED_AT": "2026-01-15",
}


def environment_without(name: str) -> dict[str, str]:
    return {key: value for key, value in VALID_ENVIRONMENT.items() if key != name}


def environment_with(**overrides: str) -> dict[str, str]:
    return VALID_ENVIRONMENT | overrides


# --- Matrix row: valid environment -------------------------------------------


def test_valid_environment_builds_settings() -> None:
    settings = load_settings(VALID_ENVIRONMENT)

    assert settings.environment is Environment.LOCAL
    assert settings.database_url == VALID_ENVIRONMENT["DATABASE_URL"]
    assert settings.port == 8000
    assert settings.auth_password_hash == VALID_AUTH_PASSWORD_HASH
    assert settings.session_secret_key == VALID_ENVIRONMENT["SESSION_SECRET_KEY"]
    assert settings.gemini_api_key == VALID_ENVIRONMENT["GEMINI_API_KEY"]
    assert (
        settings.gemini_data_terms_verified_at
        == VALID_ENVIRONMENT["GEMINI_DATA_TERMS_VERIFIED_AT"]
    )


def test_production_is_a_permitted_environment() -> None:
    settings = load_settings(environment_with(ENVIRONMENT="production"))

    assert settings.environment is Environment.PRODUCTION


def test_sqlalchemy_url_pins_the_psycopg_dialect() -> None:
    """A provider-supplied ``postgresql://`` URL must not resolve to psycopg 2."""
    settings = load_settings(
        environment_with(DATABASE_URL="postgresql://user:pw@db.example.eu/astro")
    )

    assert settings.sqlalchemy_url == "postgresql+psycopg://user:pw@db.example.eu/astro"
    assert settings.database_url == "postgresql://user:pw@db.example.eu/astro"


# --- Matrix row: missing required variable -----------------------------------


@pytest.mark.parametrize("missing", sorted(VALID_ENVIRONMENT))
def test_a_missing_variable_aborts_and_is_named(missing: str) -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_without(missing))

    assert missing in str(raised.value)
    assert "required" in str(raised.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_variable_counts_as_missing(blank: str) -> None:
    """An empty value is a defaulting accident waiting to happen, not a value."""
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(DATABASE_URL=blank))

    assert "DATABASE_URL" in str(raised.value)


def test_every_offender_is_named_at_once() -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings({})

    message = str(raised.value)
    for name in VALID_ENVIRONMENT:
        assert name in message


# --- Matrix row: malformed value ---------------------------------------------


@pytest.mark.parametrize(
    "malformed",
    [
        "mysql://astro:astro@localhost:3306/astro_report",
        "sqlite:///./astro.db",
        "/var/run/postgresql",
        "astro_report",
    ],
)
def test_a_non_postgres_url_aborts_and_says_why(malformed: str) -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(DATABASE_URL=malformed))

    message = str(raised.value)
    assert "DATABASE_URL" in message
    assert "Postgres" in message


def test_a_postgres_url_without_a_host_aborts() -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(DATABASE_URL="postgresql:///astro_report"))

    message = str(raised.value)
    assert "DATABASE_URL" in message
    assert "host" in message


@pytest.mark.parametrize(
    "scheme", ["postgres", "postgresql", "postgresql+psycopg"]
)
def test_accepted_postgres_schemes(scheme: str) -> None:
    url = f"{scheme}://astro:astro@localhost:5432/astro_report"

    assert load_settings(environment_with(DATABASE_URL=url)).database_url == url


@pytest.mark.parametrize("malformed", ["eight-thousand", "8000.5", "80 00"])
def test_a_non_integer_port_aborts(malformed: str) -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(PORT=malformed))

    message = str(raised.value)
    assert "PORT" in message
    assert "not an integer" in message


def test_a_blank_port_is_reported_as_missing_not_malformed() -> None:
    """An empty PORT is an unset one; the message should say so, not blame syntax."""
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(PORT=""))

    message = str(raised.value)
    assert "PORT" in message
    assert "required" in message


@pytest.mark.parametrize("out_of_range", ["0", "65536", "-1"])
def test_a_port_outside_the_permitted_range_aborts(out_of_range: str) -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(PORT=out_of_range))

    message = str(raised.value)
    assert "PORT" in message
    assert "range" in message


# --- Matrix row: AUTH_PASSWORD_HASH must be a well-formed Argon2 hash ---------


@pytest.mark.parametrize(
    "malformed",
    [
        "not-a-hash-at-all",
        "plaintext-password",
        "$bcrypt$2b$12$abcdefghijklmnopqrstuv",
    ],
)
def test_a_malformed_auth_password_hash_aborts(malformed: str) -> None:
    """``argon2.extract_parameters()`` raising ``InvalidHashError`` is the
    failure signal -- this needs no password to check, only the hash's shape."""
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(AUTH_PASSWORD_HASH=malformed))

    message = str(raised.value)
    assert "AUTH_PASSWORD_HASH" in message


def test_a_well_formed_auth_password_hash_is_accepted() -> None:
    settings = load_settings(VALID_ENVIRONMENT)

    assert settings.auth_password_hash == VALID_AUTH_PASSWORD_HASH


# --- Matrix row: SESSION_SECRET_KEY must be at least 32 characters -----------


@pytest.mark.parametrize("short", ["", "short-key", "x" * 31])
def test_a_session_secret_key_shorter_than_32_chars_aborts(short: str) -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(SESSION_SECRET_KEY=short))

    message = str(raised.value)
    assert "SESSION_SECRET_KEY" in message


def test_a_session_secret_key_of_exactly_32_chars_is_accepted() -> None:
    settings = load_settings(environment_with(SESSION_SECRET_KEY="x" * 32))

    assert settings.session_secret_key == "x" * 32


# --- Matrix row: GEMINI_DATA_TERMS_VERIFIED_AT must be a non-blank ISO date ---


@pytest.mark.parametrize(
    "malformed", ["not-a-date", "2026-13-40", "15/01/2026", "2026-01-15T00:00:00"]
)
def test_a_malformed_gemini_data_terms_verified_at_aborts(malformed: str) -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(GEMINI_DATA_TERMS_VERIFIED_AT=malformed))

    message = str(raised.value)
    assert "GEMINI_DATA_TERMS_VERIFIED_AT" in message
    assert "ISO date" in message


def test_a_well_formed_gemini_data_terms_verified_at_is_accepted() -> None:
    settings = load_settings(VALID_ENVIRONMENT)

    assert settings.gemini_data_terms_verified_at == "2026-01-15"


def test_a_future_gemini_data_terms_verified_at_aborts() -> None:
    from datetime import date, timedelta

    future = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(GEMINI_DATA_TERMS_VERIFIED_AT=future))

    message = str(raised.value)
    assert "GEMINI_DATA_TERMS_VERIFIED_AT" in message
    assert "future" in message


def test_a_gemini_data_terms_verified_at_of_today_is_accepted() -> None:
    from datetime import date

    today = date.today().isoformat()
    settings = load_settings(environment_with(GEMINI_DATA_TERMS_VERIFIED_AT=today))

    assert settings.gemini_data_terms_verified_at == today


def test_gemini_api_key_is_required() -> None:
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_without("GEMINI_API_KEY"))

    message = str(raised.value)
    assert "GEMINI_API_KEY" in message
    assert "required" in message


# --- Matrix row: unrecognized enum --------------------------------------------


def test_an_unrecognized_environment_names_the_permitted_values() -> None:
    """`staging` is the case that matters: there is deliberately no staging."""
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(ENVIRONMENT="staging"))

    message = str(raised.value)
    assert "ENVIRONMENT" in message
    assert "staging" in message
    assert "local" in message and "production" in message


def test_the_environment_enum_holds_exactly_two_members() -> None:
    assert {member.value for member in Environment} == {"local", "production"}


# --- The password never reaches a repr, a log line or an error ---------------

SECRET = "hunter2SECRET"
SECRET_URL = f"postgresql://astro:{SECRET}@db.eu-central-1.neon.tech:5432/astro"


def test_repr_does_not_leak_the_database_password() -> None:
    """A settings object reaches tracebacks and debuggers; the password must not."""
    settings = load_settings(environment_with(DATABASE_URL=SECRET_URL))

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert SECRET not in f"{settings}"


def test_repr_still_identifies_the_database() -> None:
    """Redaction is not erasure: a repr that says nothing is useless in a log."""
    settings = load_settings(environment_with(DATABASE_URL=SECRET_URL))

    rendered = repr(settings)
    assert "db.eu-central-1.neon.tech" in rendered
    assert "astro" in rendered
    assert "***" in rendered
    assert "port=5432" not in rendered  # the *service* port, not the database's


def test_the_password_is_still_available_on_the_attribute() -> None:
    """Only the rendering is redacted; the connection still needs the real value."""
    settings = load_settings(environment_with(DATABASE_URL=SECRET_URL))

    assert settings.database_url == SECRET_URL
    assert SECRET in settings.sqlalchemy_url


def test_a_url_without_a_password_is_left_alone() -> None:
    url = "postgresql://astro@localhost:5432/astro_report"

    assert load_settings(environment_with(DATABASE_URL=url)).redacted_database_url == url


def test_config_errors_never_quote_the_database_url() -> None:
    """The offender is named; its value — which carries the password — is not."""
    with pytest.raises(ConfigError) as raised:
        load_settings(environment_with(DATABASE_URL=f"mysql://astro:{SECRET}@h/d"))

    message = str(raised.value)
    assert "DATABASE_URL" in message
    assert SECRET not in message


# --- The auth secrets never reach a repr either --------------------------------


def test_repr_does_not_leak_the_auth_password_hash_salt_or_digest() -> None:
    """The Argon2 salt and digest are the closest thing this hash has to a
    secret; the repr must not print them in full."""
    settings = load_settings(VALID_ENVIRONMENT)

    *_, salt, digest = VALID_AUTH_PASSWORD_HASH.split("$")
    rendered = repr(settings)
    assert salt not in rendered
    assert digest not in rendered


def test_repr_still_identifies_the_auth_password_hash_algorithm() -> None:
    """Redaction is not erasure: the algorithm and cost parameters are not
    secret and are useful in a log line."""
    rendered = repr(load_settings(VALID_ENVIRONMENT))

    assert "argon2id" in rendered
    assert "***" in rendered


def test_repr_does_not_leak_the_session_secret_key() -> None:
    settings = load_settings(VALID_ENVIRONMENT)

    assert VALID_ENVIRONMENT["SESSION_SECRET_KEY"] not in repr(settings)


def test_repr_does_not_leak_the_gemini_api_key() -> None:
    settings = load_settings(VALID_ENVIRONMENT)

    assert VALID_ENVIRONMENT["GEMINI_API_KEY"] not in repr(settings)


def test_repr_still_identifies_when_the_gemini_data_terms_were_verified() -> None:
    """The verification date is not a secret and is useful in a log line."""
    rendered = repr(load_settings(VALID_ENVIRONMENT))

    assert "2026-01-15" in rendered


def test_redacted_auth_password_hash_falls_back_on_a_hash_with_no_dollar_fields() -> None:
    """A redaction helper must never be the thing that crashes a repr, even
    given a value ``load_settings`` itself would never have accepted --
    ``Settings`` can be constructed directly, bypassing validation."""
    settings = dataclasses.replace(
        load_settings(VALID_ENVIRONMENT), auth_password_hash="not-a-hash-at-all"
    )

    assert settings.redacted_auth_password_hash == "<redacted>"
    assert "not-a-hash-at-all" not in repr(settings)


# --- Percent-encoded passwords survive intact (Alembic regression) ------------

PERCENT_URL = "postgresql://astro:p%40ss%25word@db.example.eu:5432/astro"


def test_a_percent_encoded_password_is_not_mangled() -> None:
    """Generated Postgres passwords routinely contain %40; nothing may rewrite it."""
    settings = load_settings(environment_with(DATABASE_URL=PERCENT_URL))

    assert settings.database_url == PERCENT_URL
    assert "p%40ss%25word" in settings.sqlalchemy_url
    assert settings.sqlalchemy_url.startswith("postgresql+psycopg://")


def test_sqlalchemy_accepts_a_percent_encoded_url() -> None:
    """The URL must survive all the way to the engine, decoded exactly once."""
    from sqlalchemy.engine import make_url

    settings = load_settings(environment_with(DATABASE_URL=PERCENT_URL))
    url = make_url(settings.sqlalchemy_url)

    assert url.password == "p@ss%word"
    assert url.host == "db.example.eu"


# --- Matrix row: mutation attempt --------------------------------------------


def test_settings_reject_mutation() -> None:
    settings = load_settings(VALID_ENVIRONMENT)

    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.port = 9000  # type: ignore[misc]


def test_settings_reject_new_attributes() -> None:
    settings = load_settings(VALID_ENVIRONMENT)

    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.debug = True  # type: ignore[attr-defined]


def test_settings_are_frozen_dataclasses() -> None:
    assert dataclasses.is_dataclass(Settings)
    assert Settings.__dataclass_params__.frozen is True


# --- Startup behavior: loudly, and with a non-zero exit ----------------------


def test_importing_config_with_a_bad_environment_exits_non_zero() -> None:
    """The verification command from the story, run as its own process."""
    completed = subprocess.run(
        [sys.executable, "-c", "import shell.config"],
        cwd=REPO_ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(REPO_ROOT),
            "ENVIRONMENT": "local",
            "DATABASE_URL": "",
            "PORT": "8000",
        },
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "DATABASE_URL" in completed.stderr


def test_importing_config_with_a_valid_environment_succeeds() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import shell.config; print(shell.config.settings.port)"],
        cwd=REPO_ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT), **VALID_ENVIRONMENT},
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "8000"
