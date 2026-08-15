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
