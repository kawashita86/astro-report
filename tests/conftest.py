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

_IMPORTABLE_ENVIRONMENT = {
    "ENVIRONMENT": "local",
    "DATABASE_URL": "postgresql://astro:astro@localhost:5432/astro_report",
    "PORT": "8000",
}

os.environ.update(_IMPORTABLE_ENVIRONMENT)
