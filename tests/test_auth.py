"""Story 1.4: sign/verify round-trip, tamper/expiry rejection, and proof that
every route outside the allowlist is authenticated by default.

The last of those is the load-bearing test in this file: it walks
``app.routes`` itself rather than a second, hand-maintained list of "routes
that should require auth," so a new route added anywhere in ``shell/http/app.py``
without touching ``shell.http.auth.ALLOWLIST`` fails this suite.
"""

from __future__ import annotations

import logging
import time

import pytest
from fastapi.testclient import TestClient

from shell.config import Environment, Settings
from shell.http.app import app, create_app
from shell.http.auth import (
    ALLOWLIST,
    SESSION_COOKIE_NAME,
    log_failed_login_attempt,
    sign_session,
    verify_password,
    verify_session,
)

SESSION_SECRET_KEY = "test-session-secret-key-at-least-32-chars-long"
OTHER_SESSION_SECRET_KEY = "another-test-session-secret-key-32-chars-plus"

#: Argon2 hash of "correct horse battery staple" — a fixed test password,
#: never a real one.
AUTH_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
)
AUTH_PASSWORD = "correct horse battery staple"

LOCAL = Settings(
    environment=Environment.LOCAL,
    database_url="postgresql://astro:astro@localhost:5432/astro_report",
    port=8000,
    auth_password_hash=AUTH_PASSWORD_HASH,
    session_secret_key=SESSION_SECRET_KEY,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(LOCAL))


# --- sign_session / verify_session: the stateless token -----------------------


def test_a_freshly_signed_session_verifies() -> None:
    expires_at = 2_000_000_000  # far future
    token = sign_session(expires_at, SESSION_SECRET_KEY)

    assert verify_session(token, SESSION_SECRET_KEY, now=1_000_000_000) is True


def test_the_token_carries_the_expiry_as_a_bare_epoch_integer() -> None:
    """Not a dot-joined ISO datetime: its own `.` in microseconds would break
    a naive split on the token's separator."""
    token = sign_session(2_000_000_000, SESSION_SECRET_KEY)

    payload, _, _signature = token.partition(".")
    assert payload == "2000000000"
    assert payload.isdigit()


def test_a_tampered_signature_does_not_verify() -> None:
    token = sign_session(2_000_000_000, SESSION_SECRET_KEY)
    payload, _, signature = token.partition(".")
    tampered = f"{payload}.{signature[:-1]}{'0' if signature[-1] != '0' else '1'}"

    assert verify_session(tampered, SESSION_SECRET_KEY, now=1_000_000_000) is False


def test_a_tampered_payload_does_not_verify() -> None:
    """Changing the expiry without re-signing invalidates the signature too."""
    token = sign_session(2_000_000_000, SESSION_SECRET_KEY)
    _, _, signature = token.partition(".")
    tampered = f"2000000001.{signature}"

    assert verify_session(tampered, SESSION_SECRET_KEY, now=1_000_000_000) is False


def test_an_expired_token_does_not_verify_even_with_a_correct_signature() -> None:
    token = sign_session(1_000_000_000, SESSION_SECRET_KEY)

    assert verify_session(token, SESSION_SECRET_KEY, now=1_000_000_001) is False


def test_a_token_is_already_expired_at_the_exact_expiry_instant() -> None:
    """The boundary itself, not just a margin either side of it: `now ==
    expires_at` must be treated as expired, not as still-valid."""
    token = sign_session(1_000_000_000, SESSION_SECRET_KEY)

    assert verify_session(token, SESSION_SECRET_KEY, now=1_000_000_000) is False


def test_an_absurdly_long_expiry_field_does_not_verify() -> None:
    """A signature can't be forged, but the expiry field itself is attacker-
    controlled text before it's ever parsed. A digit string far past any
    plausible timestamp must fail cleanly rather than reach `int()`, which
    raises instead of failing for strings past Python's own conversion
    limit (thousands of digits)."""
    absurd_expiry = "9" * 5000
    forged = f"{absurd_expiry}.{'0' * 64}"

    assert verify_session(forged, SESSION_SECRET_KEY, now=1_000_000_000) is False


def test_a_token_signed_with_a_different_key_does_not_verify() -> None:
    token = sign_session(2_000_000_000, SESSION_SECRET_KEY)

    assert verify_session(token, OTHER_SESSION_SECRET_KEY, now=1_000_000_000) is False


@pytest.mark.parametrize(
    "malformed",
    ["", "no-dot-at-all", ".", "abc.def", "123", "-5.abcdef"],
)
def test_malformed_tokens_do_not_verify(malformed: str) -> None:
    assert verify_session(malformed, SESSION_SECRET_KEY, now=1_000_000_000) is False


def test_a_token_still_valid_hours_later_keeps_verifying() -> None:
    """AC4: a multi-hour working batch must not re-prompt."""
    now = 1_000_000_000
    expires_at = now + 60 * 60 * 8  # signed in, 8 hours into a batch
    token = sign_session(expires_at, SESSION_SECRET_KEY)

    assert verify_session(token, SESSION_SECRET_KEY, now=now + 60 * 60 * 6) is True


# --- verify_password ------------------------------------------------------------


def test_the_correct_password_verifies() -> None:
    assert verify_password(AUTH_PASSWORD, AUTH_PASSWORD_HASH) is True


def test_any_other_password_does_not_verify() -> None:
    assert verify_password("wrong password", AUTH_PASSWORD_HASH) is False


def test_an_empty_password_does_not_verify() -> None:
    assert verify_password("", AUTH_PASSWORD_HASH) is False


# --- The allowlist is the single source the enforcement test reads ------------


def test_the_allowlist_holds_exactly_healthz_and_login() -> None:
    assert {"/healthz", "/login"} == ALLOWLIST


def test_every_route_is_authenticated_unless_allowlisted() -> None:
    """Walks the real route table of the real app -- not a second,
    hand-maintained list of routes expected to require auth. A new route
    added to `shell/http/app.py` and left off `ALLOWLIST` fails here the
    moment it is registered, without anyone updating this test."""
    client = TestClient(app)

    paths = sorted({route.path for route in app.routes if hasattr(route, "path")})
    assert paths, "the app registered no routes at all"

    for path in paths:
        response = client.get(path)
        if path in ALLOWLIST:
            assert response.status_code != 401, f"{path} is allowlisted but was rejected"
        else:
            assert response.status_code == 401, f"{path} was reachable anonymously"
            assert response.content == b""


def test_allowlisted_routes_are_reachable_anonymously(client: TestClient) -> None:
    for path in ALLOWLIST:
        response = client.get(path)
        assert response.status_code != 401


# --- Uniform rejection: missing, tampered and expired cookies are alike -------


def test_no_cookie_at_all_is_rejected_uniformly(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 401
    assert response.content == b""


def test_a_tampered_cookie_is_rejected_uniformly(client: TestClient) -> None:
    token = sign_session(2_000_000_000, SESSION_SECRET_KEY)
    payload, _, signature = token.partition(".")
    tampered = f"{payload}.{signature[:-1]}{'0' if signature[-1] != '0' else '1'}"
    client.cookies.set(SESSION_COOKIE_NAME, tampered)

    response = client.get("/")

    assert response.status_code == 401
    assert response.content == b""


def test_an_expired_cookie_is_rejected_uniformly(client: TestClient) -> None:
    expired = sign_session(int(time.time()) - 1, SESSION_SECRET_KEY)
    client.cookies.set(SESSION_COOKIE_NAME, expired)

    response = client.get("/")

    assert response.status_code == 401
    assert response.content == b""


def test_a_valid_cookie_clears_the_checkpoint(client: TestClient) -> None:
    valid = sign_session(int(time.time()) + 3600, SESSION_SECRET_KEY)
    client.cookies.set(SESSION_COOKIE_NAME, valid)

    response = client.get("/")

    # Past the checkpoint, "/" is simply not a registered route.
    assert response.status_code == 404


# --- The failed-login log line carries no secrets ------------------------------


def test_a_failed_login_logs_exactly_one_bare_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        log_failed_login_attempt()

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert AUTH_PASSWORD not in record.getMessage()
    assert AUTH_PASSWORD_HASH not in record.getMessage()
    assert SESSION_SECRET_KEY not in record.getMessage()


def test_posting_the_wrong_password_logs_exactly_one_bare_line(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        client.post("/login", data={"password": "wrong password"})

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert "wrong password" not in messages[0]
    assert AUTH_PASSWORD_HASH not in messages[0]
