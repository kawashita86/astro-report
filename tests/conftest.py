"""Test session setup.

``shell/config.py`` validates the environment at import time, so a test session
must have a valid one before anything imports it. These values are supplied only
to make the module importable; every test that exercises validation calls
``load_settings()`` with an explicit mapping instead of touching the environment.

The assignment is unconditional on purpose. With ``setdefault``, a developer's
ambient ``ENVIRONMENT=dev`` or a stray ``DATABASE_URL`` would leak into the run —
erroring at collection, or worse, quietly testing against values the suite did
not choose. The session owns its environment.
"""

from __future__ import annotations

import os

import pytest

from core.ephemeris.identity import verify_ephemeris_identity

#: Argon2 hash of "correct horse battery staple" — a fixed test password, never
#: a real one. Only its well-formedness matters for import-time validation;
#: tests that exercise sign-in call ``verify_password`` against this hash and
#: password explicitly.
_TEST_AUTH_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
)

_IMPORTABLE_ENVIRONMENT = {
    "ENVIRONMENT": "local",
    "DATABASE_URL": "postgresql://astro:astro@localhost:5432/astro_report",
    "PORT": "8000",
    "AUTH_PASSWORD_HASH": _TEST_AUTH_PASSWORD_HASH,
    "SESSION_SECRET_KEY": "test-session-secret-key-at-least-32-chars-long",
}

os.environ.update(_IMPORTABLE_ENVIRONMENT)


@pytest.fixture(autouse=True)
def _ephemeris_pinned_to_the_real_vendored_files() -> None:
    """``swe.set_ephe_path()`` is process-global C-extension state, not
    per-module: some test modules (``tests/test_ephemeris_identity.py``'s own
    I/O matrix) deliberately point it at temporary fixture directories that
    are gone by the time another module's tests run, in the same pytest
    process, if collection order alone were relied on. Re-pinning to the real
    vendored files before every test in the session -- not just once at
    import time -- keeps any test computing against the ephemeris correct
    regardless of what ran immediately before it.
    """
    verify_ephemeris_identity()
