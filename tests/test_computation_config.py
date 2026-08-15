"""Computation config loading -- one test per row of the story's I/O matrix,
plus the properties the matrix implies: the value is frozen, its dict-shaped
fields are genuinely immutable, and the shipped file's own default orbs load
without error.
"""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from core.errors import ComputationConfigError
from core.types.computation import ComputationConfig
from shell.computation import DEFAULT_COMPUTATION_PATH, load_computation_config

REPO_ROOT = Path(__file__).resolve().parent.parent

_VALID_TOML = """\
version = 1

[orbs]
natal = "7.0"
transit = "2.0"

[house_system]
name = "placidus"

[bodies]
fast = ["sun", "mercury", "venus", "mars"]
slow = ["jupiter", "saturn", "uranus", "neptune", "pluto"]

[rulers.traditional]
aries = "mars"
taurus = "venus"
gemini = "mercury"
cancer = "moon"
leo = "sun"
virgo = "mercury"
libra = "venus"
scorpio = "mars"
sagittarius = "jupiter"
capricorn = "saturn"
aquarius = "saturn"
pisces = "jupiter"

[rulers.modern]
aries = "mars"
taurus = "venus"
gemini = "mercury"
cancer = "moon"
leo = "sun"
virgo = "mercury"
libra = "venus"
scorpio = "pluto"
sagittarius = "jupiter"
capricorn = "saturn"
aquarius = "uranus"
pisces = "neptune"

[harmonic]
harmonic_aspects = ["trine", "sextile"]
disharmonic_aspects = ["square", "opposition"]
harmonic_conjunction_bodies = ["venus", "jupiter"]
disharmonic_conjunction_bodies = ["mars", "saturn", "pluto"]
"""


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "computation.toml"
    path.write_text(content, encoding="utf-8")
    return path


# --- Matrix row: valid file, all values in range --------------------------------


def test_a_valid_file_returns_a_populated_frozen_config(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_TOML)

    config = load_computation_config(path)

    assert isinstance(config, ComputationConfig)
    assert config.version == 1
    assert config.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert config.orbs.natal == Decimal("7.0")
    assert config.orbs.transit == Decimal("2.0")
    assert config.house_system.name == "placidus"
    assert config.bodies.fast == ("sun", "mercury", "venus", "mars")
    assert config.bodies.slow == ("jupiter", "saturn", "uranus", "neptune", "pluto")
    assert config.rulers.traditional["scorpio"] == "mars"
    assert config.rulers.traditional["aquarius"] == "saturn"
    assert config.rulers.traditional["pisces"] == "jupiter"
    assert config.rulers.modern["scorpio"] == "pluto"
    assert config.rulers.modern["aquarius"] == "uranus"
    assert config.rulers.modern["pisces"] == "neptune"
    assert config.harmonic.harmonic_aspects == ("trine", "sextile")
    assert config.harmonic.disharmonic_aspects == ("square", "opposition")
    assert config.harmonic.harmonic_conjunction_bodies == ("venus", "jupiter")
    assert config.harmonic.disharmonic_conjunction_bodies == ("mars", "saturn", "pluto")


def test_content_hash_is_the_sha256_of_the_raw_file_bytes_not_a_field_in_the_file(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, _VALID_TOML)

    config = load_computation_config(path)

    assert "content_hash" not in _VALID_TOML
    assert config.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()


# --- Matrix row: natal orb out of range ------------------------------------------


@pytest.mark.parametrize("value", ["5.9", "8.1"])
def test_a_natal_orb_out_of_range_fails_and_names_the_field_and_value(
    tmp_path: Path, value: str
) -> None:
    content = _VALID_TOML.replace('natal = "7.0"', f'natal = "{value}"')
    path = _write(tmp_path, content)

    with pytest.raises(ComputationConfigError) as raised:
        load_computation_config(path)

    message = str(raised.value)
    assert "orbs.natal" in message
    assert value in message


# --- Matrix row: transit orb out of range ----------------------------------------


@pytest.mark.parametrize("value", ["1.4", "2.6"])
def test_a_transit_orb_out_of_range_fails_and_names_the_field_and_value(
    tmp_path: Path, value: str
) -> None:
    content = _VALID_TOML.replace('transit = "2.0"', f'transit = "{value}"')
    path = _write(tmp_path, content)

    with pytest.raises(ComputationConfigError) as raised:
        load_computation_config(path)

    message = str(raised.value)
    assert "orbs.transit" in message
    assert value in message


# --- Non-finite orb values fail cleanly, not with a raw InvalidOperation ---------


@pytest.mark.parametrize("value", ["nan", "snan", "inf", "-inf"])
def test_a_non_finite_orb_fails_cleanly_rather_than_crashing(tmp_path: Path, value: str) -> None:
    """`Decimal(value)` constructs successfully for all four of these; only
    the range comparison would fail, and for NaN specifically that comparison
    raises `decimal.InvalidOperation` instead of returning `False` -- verified
    directly against `decimal.Decimal` before this guard was added."""
    content = _VALID_TOML.replace('natal = "7.0"', f'natal = "{value}"')
    path = _write(tmp_path, content)

    with pytest.raises(ComputationConfigError) as raised:
        load_computation_config(path)

    assert "orbs.natal" in str(raised.value)


# --- Unexpected keys are flagged, not silently ignored ---------------------------


@pytest.mark.parametrize(
    "table_name,bad_line,good_line",
    [
        ("orbs", 'natal = "7.0"\nbogus = "1"', 'natal = "7.0"'),
        ("house_system", 'name = "placidus"\nbogus = "1"', 'name = "placidus"'),
        (
            "bodies",
            'fast = ["sun", "mercury", "venus", "mars"]\nbogus = ["x"]',
            'fast = ["sun", "mercury", "venus", "mars"]',
        ),
        (
            "harmonic",
            'harmonic_aspects = ["trine", "sextile"]\nbogus = ["x"]',
            'harmonic_aspects = ["trine", "sextile"]',
        ),
    ],
)
def test_an_unexpected_key_is_flagged_not_silently_ignored(
    tmp_path: Path, table_name: str, bad_line: str, good_line: str
) -> None:
    content = _VALID_TOML.replace(good_line, bad_line, 1)
    path = _write(tmp_path, content)

    with pytest.raises(ComputationConfigError) as raised:
        load_computation_config(path)

    message = str(raised.value)
    assert f"[{table_name}]" in message
    assert "bogus" in message


def test_an_unexpected_key_in_rulers_is_flagged(tmp_path: Path) -> None:
    content = _VALID_TOML.replace(
        "[rulers.traditional]", "[rulers.bogus]\nplaceholder = \"x\"\n\n[rulers.traditional]"
    )
    path = _write(tmp_path, content)

    with pytest.raises(ComputationConfigError) as raised:
        load_computation_config(path)

    message = str(raised.value)
    assert "[rulers]" in message
    assert "bogus" in message


# --- Matrix row: file missing or malformed ---------------------------------------


def test_a_missing_file_fails_with_a_typed_error_naming_the_problem(tmp_path: Path) -> None:
    path = tmp_path / "does-not-exist.toml"

    with pytest.raises(ComputationConfigError) as raised:
        load_computation_config(path)

    assert str(path) in str(raised.value)


def test_malformed_toml_fails_with_a_typed_error_not_a_raw_traceback(tmp_path: Path) -> None:
    path = _write(tmp_path, "this is not [valid toml")

    with pytest.raises(ComputationConfigError) as raised:
        load_computation_config(path)

    assert str(path) in str(raised.value)


def test_a_file_missing_a_required_table_fails_with_a_typed_error_not_a_keyerror(
    tmp_path: Path,
) -> None:
    """A malformed *structure* (a whole table dropped) must not surface as a
    raw `KeyError`/`TypeError` from deep inside parsing."""
    path = _write(tmp_path, "version = 1\n")

    with pytest.raises(ComputationConfigError):
        load_computation_config(path)


# --- Frozen / immutability --------------------------------------------------------


def test_computation_config_and_nested_value_types_are_frozen(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_TOML)
    config = load_computation_config(path)

    assert dataclasses.is_dataclass(config)
    assert type(config).__dataclass_params__.frozen is True

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.version = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.orbs.natal = Decimal("1")  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.house_system.name = "koch"  # type: ignore[misc]


def test_ruler_and_harmonic_tables_are_genuinely_immutable_mappings(tmp_path: Path) -> None:
    """`MappingProxyType`, not a plain `dict` -- a frozen dataclass only stops
    reassigning the field, not mutating the dict object it points at."""
    path = _write(tmp_path, _VALID_TOML)
    config = load_computation_config(path)

    assert isinstance(config.rulers.traditional, MappingProxyType)
    assert isinstance(config.rulers.modern, MappingProxyType)
    with pytest.raises(TypeError):
        config.rulers.traditional["aries"] = "someone-else"  # type: ignore[index]


# --- The shipped file itself -------------------------------------------------------


def test_the_shipped_files_default_orbs_load_without_error() -> None:
    config = load_computation_config(DEFAULT_COMPUTATION_PATH)

    assert config.orbs.natal == Decimal("7.0")
    assert config.orbs.transit == Decimal("2.0")


def test_load_computation_config_defaults_to_the_shipped_file() -> None:
    assert load_computation_config().content_hash == load_computation_config(
        DEFAULT_COMPUTATION_PATH
    ).content_hash


# --- Startup behavior: the shell asserts this eagerly, at import time ----------


def test_importing_the_app_with_a_missing_computation_config_exits_non_zero(
    tmp_path: Path,
) -> None:
    """`shell/http/app.py`'s own docstring promises this loads eagerly at
    import time, "the same way" `ephemeris_identity` does -- but nothing
    previously exercised that promise through the actual import boundary
    (every other test here calls `load_computation_config()` as a unit).
    Moved outside `data/` via `shutil.move`, not merely renamed in place, and
    not `Path.rename` -- `tmp_path` and the repo checkout aren't guaranteed to
    share a filesystem (the same lesson `test_ephemeris_identity.py` already
    encoded).
    """
    target = DEFAULT_COMPUTATION_PATH
    displaced = tmp_path / "computation.toml.displaced-by-test"
    assert target.is_file(), "the shipped computation config must exist for this test to matter"

    shutil.move(str(target), str(displaced))
    try:
        completed = subprocess.run(
            [sys.executable, "-c", "from shell.http import app"],
            cwd=REPO_ROOT,
            env={
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": str(REPO_ROOT),
                "ENVIRONMENT": "local",
                "DATABASE_URL": "postgresql://astro:astro@localhost:5432/astro_report",
                "PORT": "8000",
                "AUTH_PASSWORD_HASH": (
                    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
                    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
                ),
                "SESSION_SECRET_KEY": "test-session-secret-key-at-least-32-chars-long",
            },
            capture_output=True,
            text=True,
        )
    finally:
        shutil.move(str(displaced), str(target))

    assert completed.returncode != 0
    assert "computation" in completed.stderr.lower()
