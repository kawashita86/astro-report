"""Test support package: the fixture-walking conformance runner (Story 1.6).

Not application code -- exempt from the purity-boundary and
single-environment-reader guards, which only cover ``core/``, ``shell/`` and
``migrations/`` (see ``SOURCE_ROOTS`` in
``tests/test_env_access_is_centralized.py``).
"""

from __future__ import annotations
