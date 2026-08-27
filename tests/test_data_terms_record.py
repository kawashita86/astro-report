"""Guard suite for the dated Gemini data-terms re-verification record
(``docs/release-validation/gemini-data-terms.md``, Story 8.2).

Mirrors the read-the-file style of ``tests/test_compose_local_generator.py``:
read the files, parse in-process, no network and no Docker. The record's
machine-readable block is a fenced ```toml``` block parsed with ``tomllib``
(stdlib) -- no YAML parser is a dependency in this repo. A recorded material
change to the data terms sets ``outcome = "blocked"``, which keeps
``test_outcome_permits_release`` red so the release gate does not go green.
"""

from __future__ import annotations

import datetime
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD_FILE = REPO_ROOT / "docs" / "release-validation" / "gemini-data-terms.md"
RENDER_YAML = REPO_ROOT / "render.yaml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE_FILE = REPO_ROOT / "compose.yaml"
README = REPO_ROOT / "README.md"
GENERATOR = REPO_ROOT / "shell" / "adapters" / "gemini" / "generator.py"

# Render region slugs that sit in the EU/EEA (AD-9 / NFR-17). Frankfurt is the
# only one this project deploys to; the set exists so the check reads as intent.
_EU_RENDER_REGIONS = {"frankfurt"}

# PRD §6.2 requires storage in the EU/EEA; this is the Neon project's zone as
# documented in README.md / render.yaml.
_EU_STORAGE_REGION = "Europe/Frankfurt"

_EXPECTED_KEYS = {
    "provider",
    "model",
    "tier",
    "checked",
    "ratified_by",
    "ratified_on",
    "terms_source",
    "terms_effective",
    "terms_snapshot",
    "hosting_region",
    "storage_region",
    "outcome",
}

_TOML_BLOCK = re.compile(r"^```toml\n(.*?)\n```", re.DOTALL | re.MULTILINE)
_VERIFIED_AT = re.compile(
    r'^\s*GEMINI_DATA_TERMS_VERIFIED_AT\s*[:=]\s*"?(\d{4}-\d{2}-\d{2})"?',
    re.MULTILINE,
)
_RENDER_REGION = re.compile(r"^\s*region:\s*(\S+)", re.MULTILINE)
_MODEL_LITERAL = re.compile(r'^_MODEL\s*=\s*"([^"]+)"', re.MULTILINE)


def _extract_toml_block(text: str) -> str:
    match = _TOML_BLOCK.search(text)
    assert match is not None, (
        f"{RECORD_FILE} has no ```toml fenced block -- the machine-readable "
        "data-terms record is missing or malformed"
    )
    return match.group(1)


def _readme_deployment_section() -> str:
    text = README.read_text(encoding="utf-8")
    match = re.search(r"^##\s+Deployment\s*$(.*?)(?=^##\s)", text, re.DOTALL | re.MULTILINE)
    assert match is not None, "README.md has no '## Deployment' section"
    return match.group(1)


@pytest.fixture(scope="module")
def meta() -> dict[str, object]:
    assert RECORD_FILE.exists(), f"data-terms record missing: {RECORD_FILE}"
    return tomllib.loads(_extract_toml_block(RECORD_FILE.read_text(encoding="utf-8")))


def test_record_exists() -> None:
    assert RECORD_FILE.exists(), (
        f"release-validation data-terms record missing: {RECORD_FILE} -- "
        "Story 8.2 requires a dated re-verification of Gemini's data terms"
    )


def test_toml_block_parses(meta: dict[str, object]) -> None:
    missing = _EXPECTED_KEYS - meta.keys()
    unexpected = meta.keys() - _EXPECTED_KEYS
    assert not missing, f"data-terms record toml block missing keys: {sorted(missing)}"
    assert not unexpected, (
        f"data-terms record toml block has unexpected keys: {sorted(unexpected)} -- "
        "update _EXPECTED_KEYS and the matching assertions if a key was added on purpose"
    )


def test_checked_is_a_date(meta: dict[str, object]) -> None:
    assert isinstance(meta["checked"], datetime.date), (
        f"`checked` must be a bare ISO date (parses to datetime.date), got "
        f"{meta['checked']!r}"
    )


def test_checked_date_is_sane(meta: dict[str, object]) -> None:
    checked = meta["checked"]
    terms_effective = meta["terms_effective"]
    assert isinstance(checked, datetime.date), f"`checked` is not a date: {checked!r}"
    assert isinstance(terms_effective, datetime.date), (
        f"`terms_effective` must be a bare ISO date, got {terms_effective!r}"
    )
    assert checked <= datetime.date.today(), (
        f"`checked` = {checked.isoformat()} is in the future -- a verification "
        "cannot have happened yet (epic-4 retro item 25)"
    )
    assert checked >= terms_effective, (
        f"`checked` = {checked.isoformat()} precedes `terms_effective` = "
        f"{terms_effective.isoformat()} -- terms cannot be verified before they take effect"
    )


def test_ratified_on_is_a_date(meta: dict[str, object]) -> None:
    assert isinstance(meta["ratified_on"], datetime.date), (
        f"`ratified_on` must be a bare ISO date, got {meta['ratified_on']!r}"
    )
    assert isinstance(meta["ratified_by"], str) and meta["ratified_by"].strip(), (
        f"`ratified_by` must be a non-empty string, got {meta['ratified_by']!r}"
    )


def test_terms_snapshot_is_wayback_url(meta: dict[str, object]) -> None:
    snapshot = meta["terms_snapshot"]
    assert isinstance(snapshot, str) and snapshot.startswith("https://web.archive.org/"), (
        f"`terms_snapshot` must be a https://web.archive.org/ capture URL, got {snapshot!r}"
    )


def test_provider_model_tier_match_generator(meta: dict[str, object]) -> None:
    match = _MODEL_LITERAL.search(GENERATOR.read_text(encoding="utf-8"))
    assert match is not None, f"could not find `_MODEL = \"...\"` in {GENERATOR}"
    assert meta["model"] == match.group(1), (
        f"record model {meta['model']!r} != configured Generator _MODEL "
        f"{match.group(1)!r} -- re-run the data-terms check when the model changes (AD-9)"
    )
    assert meta["provider"] == "Google", f"unexpected provider: {meta['provider']!r}"
    assert meta["tier"] == "free", f"unexpected tier: {meta['tier']!r}"


def test_outcome_is_valid(meta: dict[str, object]) -> None:
    assert meta["outcome"] in {"pass", "blocked"}, (
        f"`outcome` must be exactly \"pass\" or \"blocked\", got {meta['outcome']!r}"
    )


def test_outcome_permits_release(meta: dict[str, object]) -> None:
    assert meta["outcome"] == "pass", (
        "release blocked until data-terms change reassessed "
        f"(outcome = {meta['outcome']!r}, expected \"pass\")"
    )


def test_hosting_region_is_eu(meta: dict[str, object]) -> None:
    assert meta["hosting_region"] in _EU_RENDER_REGIONS, (
        f"hosting_region {meta['hosting_region']!r} is not an EU render region "
        f"{sorted(_EU_RENDER_REGIONS)}"
    )


def test_storage_region_is_eu(meta: dict[str, object]) -> None:
    assert meta["storage_region"] == _EU_STORAGE_REGION, (
        f"storage_region {meta['storage_region']!r} != {_EU_STORAGE_REGION!r} -- "
        "PRD §6.2 requires storage in the EU/EEA"
    )
    assert _EU_STORAGE_REGION in _readme_deployment_section(), (
        f"README.md's Deployment section no longer documents {_EU_STORAGE_REGION!r} "
        "as the storage location the record binds to"
    )


def test_region_matches_render_yaml(meta: dict[str, object]) -> None:
    regions = _RENDER_REGION.findall(RENDER_YAML.read_text(encoding="utf-8"))
    assert len(regions) == 1, (
        f"expected exactly one `region:` line in render.yaml, found {regions} -- "
        "a second service block would silently rebind this test"
    )
    assert regions[0] == meta["hosting_region"], (
        f"render.yaml region {regions[0]!r} != record hosting_region "
        f"{meta['hosting_region']!r}"
    )


def test_env_example_dates_match_record(meta: dict[str, object]) -> None:
    checked = meta["checked"]
    assert isinstance(checked, datetime.date)
    expected = checked.isoformat()
    for path in (ENV_EXAMPLE, COMPOSE_FILE):
        match = _VERIFIED_AT.search(path.read_text(encoding="utf-8"))
        assert match is not None, (
            f"{path.name}: no GEMINI_DATA_TERMS_VERIFIED_AT date found"
        )
        assert match.group(1) == expected, (
            f"{path.name}: GEMINI_DATA_TERMS_VERIFIED_AT {match.group(1)!r} != "
            f"record checked date {expected!r}"
        )
