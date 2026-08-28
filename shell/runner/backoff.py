"""``with_backoff``: the one bounded-retry wrapper every stage function in
``shell/runner/driver.py`` is called through (Story 3.5, AD-10).

Generic on purpose -- AD-10 rules against "two builders inventing
incompatible retry semantics" (see the story's Design Notes). Nothing here
knows what it is retrying: a stage call today is entirely local (the
already-persisted chart, the local ephemeris), but the same wrapper is meant
to be reused unchanged once a real rate-limited call exists (the Generator,
Story 4.8).
"""

from __future__ import annotations

import time
from collections.abc import Callable

__all__ = ["with_backoff"]

#: Delay before the first retry; doubles on each subsequent attempt (bounded
#: exponential, no jitter -- the story's Boundaries & Constraints explicitly
#: do not require jitter). Small: nothing this story drives through
#: `with_backoff` is rate-limited yet, so there is no reason to hold a real
#: caller -- Francesco watching the poll view -- waiting any longer than
#: proving the retry actually happened requires.
_BASE_DELAY_SECONDS = 0.1


def with_backoff[T](
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = _BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn()``, retrying on any exception up to ``max_attempts`` times
    total, waiting ``base_delay_seconds * 2 ** attempt`` between attempts.

    Re-raises the final attempt's exception once every attempt is exhausted
    -- this function never swallows a persistent failure. The caller
    (``shell/runner/driver.py::advance()``) decides what "still failing"
    means for a ``ReportRun``: leaving ``run.stage`` at its last successful
    value rather than marking the run failed.

    ``base_delay_seconds`` defaults to the module's small, generic schedule
    (``_BASE_DELAY_SECONDS``) -- right for every stage whose call is local
    and not rate-limited. A call site with a real rate-limited network call
    (``draft_ready``, Story 4.8) passes its own, larger value so consecutive
    attempts stay within the provider's ceiling; ``with_backoff``'s retry
    algorithm itself (catch-all exception, exponential doubling, no jitter)
    is unchanged either way (AD-10: one shared retry primitive).

    ``sleep`` is injectable so a test can prove the retry count and delay
    schedule without actually waiting; it defaults to the real ``time.sleep``.
    """
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as error:  # noqa: BLE001 -- deliberately generic: this wrapper
            # retries any stage failure the same way, never picking and
            # choosing which exception type deserves a retry.
            last_error = error
            if attempt < max_attempts - 1:
                sleep(base_delay_seconds * (2**attempt))

    assert last_error is not None
    raise last_error
