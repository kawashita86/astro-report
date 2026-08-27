"""``compose.yaml``'s ``app`` service declares the two Gemini variables
``load_settings()`` requires unconditionally, so ``docker compose up`` boots
clean under ``RecordedResponseGenerator`` (Story 4.9).

Mirrors ``tests/test_dockerfile_ephemeris_build.py``'s own approach: read the
file, no Docker/compose invoked, no containers started.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "compose.yaml"


@pytest.fixture(scope="module")
def compose_text() -> str:
    assert COMPOSE_FILE.exists(), "compose.yaml is gone"
    return COMPOSE_FILE.read_text(encoding="utf-8")


def _app_service_block(compose_text: str) -> str:
    """The ``app:`` service block -- from its own header line up to (but not
    including) the next top-level (non-indented) key, mirroring how
    ``compose.yaml`` nests ``services.app`` under ``services.postgres``."""
    lines = compose_text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == "app:")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line[0].isspace():
            end = index
            break
    return "\n".join(lines[start:end])


def test_app_service_declares_gemini_api_key(compose_text: str) -> None:
    block = _app_service_block(compose_text)

    assert "GEMINI_API_KEY: local-dev-unused" in block, (
        "load_settings() requires GEMINI_API_KEY unconditionally; without it "
        "here, `docker compose up` fails validation before the server starts"
    )


def test_app_service_declares_gemini_data_terms_verified_at(compose_text: str) -> None:
    block = _app_service_block(compose_text)

    # Assert on structure, not the raw date: load_settings() requires the key,
    # and it must be an ISO date. The exact value is bound to the release-
    # validation record by tests/test_data_terms_record.py, so pinning the
    # literal here too would be a third hand-edit point on every re-verification.
    assert re.search(
        r'^\s*GEMINI_DATA_TERMS_VERIFIED_AT:\s*"\d{4}-\d{2}-\d{2}"\s*$',
        block,
        re.MULTILINE,
    ), (
        "load_settings() requires GEMINI_DATA_TERMS_VERIFIED_AT unconditionally "
        "and as an ISO date; without it here, `docker compose up` fails "
        "validation before the server starts"
    )
