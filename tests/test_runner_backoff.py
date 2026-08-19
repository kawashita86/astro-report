"""``shell/runner/backoff.py::with_backoff`` -- proven against an injected
fake failing function, since nothing this story drives through it is
rate-limited yet (see the module's own docstring)."""

from __future__ import annotations

import pytest

from shell.runner.backoff import with_backoff


class _AlwaysFails(Exception):
    pass


def _fake_sleep(recorded: list[float]):
    def sleep(seconds: float) -> None:
        recorded.append(seconds)

    return sleep


def test_a_function_that_succeeds_first_try_is_called_once() -> None:
    calls = []

    def fn() -> str:
        calls.append(1)
        return "ok"

    result = with_backoff(fn, sleep=_fake_sleep([]))

    assert result == "ok"
    assert len(calls) == 1


def test_a_function_that_fails_then_succeeds_is_retried() -> None:
    calls = []

    def fn() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise _AlwaysFails("transient")
        return "ok"

    sleeps: list[float] = []
    result = with_backoff(fn, sleep=_fake_sleep(sleeps))

    assert result == "ok"
    assert len(calls) == 2
    assert len(sleeps) == 1


def test_a_function_that_always_fails_is_retried_up_to_max_attempts() -> None:
    calls = []

    def fn() -> None:
        calls.append(1)
        raise _AlwaysFails("permanent")

    sleeps: list[float] = []
    with pytest.raises(_AlwaysFails):
        with_backoff(fn, max_attempts=3, sleep=_fake_sleep(sleeps))

    assert len(calls) == 3
    # One sleep between each pair of attempts -- never after the last.
    assert len(sleeps) == 2


def test_the_delay_schedule_is_bounded_exponential_with_no_jitter() -> None:
    def fn() -> None:
        raise _AlwaysFails("permanent")

    sleeps: list[float] = []
    with pytest.raises(_AlwaysFails):
        with_backoff(fn, max_attempts=4, sleep=_fake_sleep(sleeps))

    assert len(sleeps) == 3
    # Each delay is exactly double the one before it -- deterministic, no
    # jitter added.
    assert sleeps[1] == sleeps[0] * 2
    assert sleeps[2] == sleeps[1] * 2


def test_max_attempts_of_one_never_sleeps() -> None:
    calls = []

    def fn() -> None:
        calls.append(1)
        raise _AlwaysFails("permanent")

    sleeps: list[float] = []
    with pytest.raises(_AlwaysFails):
        with_backoff(fn, max_attempts=1, sleep=_fake_sleep(sleeps))

    assert len(calls) == 1
    assert sleeps == []


def test_no_explicit_sleep_still_retries_and_succeeds() -> None:
    """No `sleep=` override -- exercises the real default (`time.sleep`)
    end-to-end. The configured base delay is small enough (0.1s, doubling)
    that a genuine short wait here is fine."""
    calls = []

    def fn() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise _AlwaysFails("transient")
        return "ok"

    result = with_backoff(fn)

    assert result == "ok"
    assert len(calls) == 2
