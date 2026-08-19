"""Sections config loading -- one test per row of the story's I/O matrix,
plus the properties the matrix implies: the value is frozen, its ``sections``
mapping is genuinely immutable, and the shipped ``data/sections.toml`` loads
without error.

Mirrors ``tests/test_computation_config.py``'s own structure -- Story 3.6's
Code Map names it as this module's precedent.
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path
from types import MappingProxyType

import pytest

from core.errors import SectionsConfigError
from core.types.sections import SectionsConfig, SectionSpec
from shell.sections import DEFAULT_SECTIONS_PATH, load_sections_config

_VALID_TOML = """\
version = 1

[sections.energia_generale]
houses = [1, 4, 7, 10]
house_bodies = "slow"
aspect_natal_points = ["sun", "moon", "mercury", "venus", "mars"]
aspect_bodies = "slow"
retrogrades = true

[sections.amore]
domain_profile = "amore"
houses = [5, 7]
aspect_natal_points = ["venus", "mars"]

[sections.lavoro]
domain_profile = "lavoro"
houses = [10, 6]
aspect_natal_points = ["mercury", "mars", "saturn"]

[sections.denaro]
domain_profile = "denaro"
houses = [2, 8]
aspect_natal_points = ["jupiter", "saturn"]

[sections.benessere]
domain_profile = "benessere"
houses = [1, 6]
aspect_natal_points = ["mars", "saturn", "moon"]

[sections.consiglio_finale]
include_all_events = true
"""


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "sections.toml"
    path.write_text(content, encoding="utf-8")
    return path


# --- Matrix row: valid file, every Section present -------------------------


def test_a_valid_file_returns_a_populated_frozen_config(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_TOML)

    config = load_sections_config(path)

    assert isinstance(config, SectionsConfig)
    assert config.version == 1
    assert config.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert set(config.sections) == {
        "energia_generale",
        "amore",
        "lavoro",
        "denaro",
        "benessere",
        "consiglio_finale",
    }

    energia_generale = config.sections["energia_generale"]
    assert energia_generale == SectionSpec(
        domain_profile=None,
        houses=(1, 4, 7, 10),
        house_bodies="slow",
        aspect_natal_points=("sun", "moon", "mercury", "venus", "mars"),
        aspect_bodies="slow",
        retrogrades=True,
        include_all_events=False,
    )

    amore = config.sections["amore"]
    assert amore == SectionSpec(
        domain_profile="amore",
        houses=(5, 7),
        house_bodies=None,
        aspect_natal_points=("venus", "mars"),
        aspect_bodies=None,
        retrogrades=False,
        include_all_events=False,
    )

    consiglio_finale = config.sections["consiglio_finale"]
    assert consiglio_finale == SectionSpec(
        domain_profile=None,
        houses=(),
        house_bodies=None,
        aspect_natal_points=(),
        aspect_bodies=None,
        retrogrades=False,
        include_all_events=True,
    )


def test_content_hash_is_the_sha256_of_the_raw_file_bytes_not_a_field_in_the_file(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, _VALID_TOML)

    config = load_sections_config(path)

    assert "content_hash" not in _VALID_TOML
    assert config.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()


# --- Matrix row: sections.toml missing a required Section key --------------


def test_a_missing_required_section_fails_and_names_the_missing_key(tmp_path: Path) -> None:
    # Drop the `[sections.lavoro]` block (and only that block) by rebuilding
    # from the blank-line-separated blocks the fixture is already written in.
    content = "\n\n".join(
        block
        for block in _VALID_TOML.split("\n\n")
        if "[sections.lavoro]" not in block
    )
    path = _write(tmp_path, content)

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    message = str(raised.value)
    assert "lavoro" in message


# --- Matrix row: sections.toml names an unsupported house_bodies/aspect_bodies value


@pytest.mark.parametrize(
    "old,new,field",
    [
        ('house_bodies = "slow"', 'house_bodies = "medium"', "house_bodies"),
        ('aspect_bodies = "slow"', 'aspect_bodies = "medium"', "aspect_bodies"),
    ],
)
def test_an_unsupported_bodies_selector_fails_and_names_the_field_and_value(
    tmp_path: Path, old: str, new: str, field: str
) -> None:
    content = _VALID_TOML.replace(old, new)
    path = _write(tmp_path, content)

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    message = str(raised.value)
    assert field in message
    assert "medium" in message


# --- Unexpected keys are flagged, not silently ignored ----------------------


def test_an_unexpected_top_level_section_key_is_flagged(tmp_path: Path) -> None:
    content = _VALID_TOML + "\n[sections.bogus]\ninclude_all_events = true\n"
    path = _write(tmp_path, content)

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    message = str(raised.value)
    assert "[sections]" in message
    assert "bogus" in message


def test_an_unexpected_key_within_a_section_table_is_flagged(tmp_path: Path) -> None:
    content = _VALID_TOML.replace(
        'domain_profile = "amore"', 'domain_profile = "amore"\nbogus = "1"'
    )
    path = _write(tmp_path, content)

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    message = str(raised.value)
    assert "[sections.amore]" in message
    assert "bogus" in message


# --- domain_profile must name a real Domain Profile -------------------------


def test_an_unsupported_domain_profile_value_is_flagged(tmp_path: Path) -> None:
    content = _VALID_TOML.replace('domain_profile = "amore"', 'domain_profile = "bogus"')
    path = _write(tmp_path, content)

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    message = str(raised.value)
    assert "sections.amore.domain_profile" in message
    assert "bogus" in message


# --- domain_profile must equal the Section's own name -----------------------


def test_a_domain_profile_naming_a_different_domain_than_its_own_section_is_flagged(
    tmp_path: Path,
) -> None:
    """A valid Domain Profile value (`"amore"`) is still wrong when declared
    under `[sections.denaro]` -- nothing but this cross-check would catch a
    Section silently carrying a contradicting `SectionPayload.profile`."""
    content = _VALID_TOML.replace('domain_profile = "denaro"', 'domain_profile = "amore"')
    path = _write(tmp_path, content)

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    message = str(raised.value)
    assert "sections.denaro.domain_profile" in message
    assert "amore" in message


def test_a_domain_profile_set_on_a_section_with_no_single_domain_profile_is_flagged(
    tmp_path: Path,
) -> None:
    """`energia_generale` has no single Domain Profile -- `domain_profile`
    must be absent there, not merely a valid-looking value."""
    content = _VALID_TOML.replace(
        "retrogrades = true", 'retrogrades = true\ndomain_profile = "amore"'
    )
    path = _write(tmp_path, content)

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    message = str(raised.value)
    assert "sections.energia_generale.domain_profile" in message
    assert "amore" in message


# --- houses must be within 1-12 ----------------------------------------------


def test_an_out_of_range_house_number_is_flagged(tmp_path: Path) -> None:
    content = _VALID_TOML.replace("houses = [5, 7]", "houses = [5, 13]")
    path = _write(tmp_path, content)

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    message = str(raised.value)
    assert "sections.amore.houses" in message


# --- Matrix row: file missing or malformed -----------------------------------


def test_a_missing_file_fails_with_a_typed_error_naming_the_problem(tmp_path: Path) -> None:
    path = tmp_path / "does-not-exist.toml"

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    assert str(path) in str(raised.value)


def test_malformed_toml_fails_with_a_typed_error_not_a_raw_traceback(tmp_path: Path) -> None:
    path = _write(tmp_path, "this is not [valid toml")

    with pytest.raises(SectionsConfigError) as raised:
        load_sections_config(path)

    assert str(path) in str(raised.value)


def test_a_file_missing_the_sections_table_fails_with_a_typed_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "version = 1\n")

    with pytest.raises(SectionsConfigError):
        load_sections_config(path)


# --- Frozen / immutability ----------------------------------------------------


def test_sections_config_and_section_spec_are_frozen(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_TOML)
    config = load_sections_config(path)

    assert dataclasses.is_dataclass(config)
    assert type(config).__dataclass_params__.frozen is True

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.version = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.sections["amore"].retrogrades = True  # type: ignore[misc]


def test_sections_mapping_is_genuinely_immutable(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_TOML)
    config = load_sections_config(path)

    assert isinstance(config.sections, MappingProxyType)
    with pytest.raises(TypeError):
        config.sections["amore"] = config.sections["amore"]  # type: ignore[index]


# --- The shipped file itself --------------------------------------------------


def test_the_shipped_file_loads_without_error() -> None:
    config = load_sections_config(DEFAULT_SECTIONS_PATH)

    assert set(config.sections) == {
        "energia_generale",
        "amore",
        "lavoro",
        "denaro",
        "benessere",
        "consiglio_finale",
    }
    assert config.sections["consiglio_finale"].include_all_events is True


def test_load_sections_config_defaults_to_the_shipped_file() -> None:
    assert load_sections_config().content_hash == load_sections_config(
        DEFAULT_SECTIONS_PATH
    ).content_hash
