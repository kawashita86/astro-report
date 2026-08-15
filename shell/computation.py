"""Loads ``data/computation.toml`` into a frozen :class:`ComputationConfig`.

File I/O is shell's job (AD-1): this is the only module that reads
``data/computation.toml``, hashes its bytes and validates its contents.
``core/types/computation.py`` holds the pure, frozen shape the file loads
into; everything downstream receives that value explicitly, never the file
path or the module global.

Loading happens at import time from ``shell/http/app.py``, exactly like
``shell/config.py``'s own ``settings: Settings = load_settings()`` and
``core/ephemeris/identity.py``'s ``verify_ephemeris_identity()`` -- a missing
file, malformed TOML, or an out-of-range orb aborts startup before the
application can serve anything, naming the offending value rather than
letting a raw ``FileNotFoundError``/``TOMLDecodeError``/``KeyError`` escape.
"""

from __future__ import annotations

import hashlib
import tomllib
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any

from core.errors import ComputationConfigError
from core.types.computation import (
    Bodies,
    ComputationConfig,
    HarmonicRule,
    HouseSystem,
    Orbs,
    Rulers,
)

__all__ = ["DEFAULT_COMPUTATION_PATH", "load_computation_config"]

#: The computation config ships alongside the application code -- it is not a
#: deployment fact, so it is not a ``shell/config.py`` setting. Resolved from
#: this file's own location, mirroring ``core/ephemeris/identity.py``'s
#: ``DEFAULT_EPHEMERIS_DIR``.
DEFAULT_COMPUTATION_PATH = Path(__file__).resolve().parent.parent / "data" / "computation.toml"

#: Permitted orb ranges (PRD FR-9 / brief addendum Section 3). Not stored in
#: the file itself -- the file carries only the chosen default, these are the
#: bounds it is validated against.
_NATAL_ORB_MIN = Decimal("6.0")
_NATAL_ORB_MAX = Decimal("8.0")
_TRANSIT_ORB_MIN = Decimal("1.5")
_TRANSIT_ORB_MAX = Decimal("2.5")

_ZODIAC_SIGNS: tuple[str, ...] = (
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ComputationConfigError(
            f"Refusing to start: computation config not found at {path}: {error}."
        ) from error


def _parse_toml(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ComputationConfigError(
            f"Refusing to start: computation config {path} could not be decoded as UTF-8: "
            f"{error}."
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise ComputationConfigError(
            f"Refusing to start: computation config {path} is not valid TOML: {error}."
        ) from error


def _read_version(data: dict[str, Any]) -> tuple[int | None, str | None]:
    raw = data.get("version")
    if not isinstance(raw, int) or isinstance(raw, bool):
        return None, f"version is required and must be an integer, got {raw!r}."
    return raw, None


def _read_table(data: dict[str, Any], name: str) -> tuple[dict[str, Any] | None, str | None]:
    raw = data.get(name)
    if not isinstance(raw, dict):
        return None, f"[{name}] is required."
    return raw, None


def _check_unexpected_keys(
    table: dict[str, Any], table_name: str, expected: frozenset[str]
) -> str | None:
    """A misspelled or extraneous key in a hand-edited TOML table should be
    flagged, not silently ignored -- matching how ``[rulers.*]`` already
    treats a key outside the twelve zodiac signs."""
    unexpected = sorted(key for key in table if key not in expected)
    if unexpected:
        return f"[{table_name}] has unexpected key(s): {', '.join(unexpected)}."
    return None


def _read_orb(
    table: dict[str, Any] | None,
    table_name: str,
    field: str,
    minimum: Decimal,
    maximum: Decimal,
) -> tuple[Decimal | None, str | None]:
    path = f"{table_name}.{field}"
    if table is None:
        return None, f"{path} is required."
    raw = table.get(field)
    if not isinstance(raw, str):
        return None, f"{path} is required and must be a quoted decimal string, got {raw!r}."
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None, f"{path} is invalid: {raw!r} is not a decimal number."
    if not value.is_finite():
        # `Decimal("nan")`/`"inf"` construct successfully -- only the range
        # comparison below would fail, and for NaN specifically it raises
        # InvalidOperation rather than returning False. Caught here instead.
        return None, f"{path} is invalid: {raw!r} is not a finite number."
    if not minimum <= value <= maximum:
        return None, (
            f"{path} is invalid: {raw!r} ({value}) is outside the permitted range "
            f"{minimum}-{maximum}."
        )
    return value, None


def _read_house_system(
    table: dict[str, Any] | None,
) -> tuple[HouseSystem | None, str | None]:
    if table is None:
        return None, "house_system.name is required."
    raw = table.get("name")
    if not isinstance(raw, str) or not raw.strip():
        return None, f"house_system.name is required and must be a non-empty string, got {raw!r}."
    return HouseSystem(name=raw), None


_ORBS_KEYS = frozenset({"natal", "transit"})
_HOUSE_SYSTEM_KEYS = frozenset({"name"})


def _read_orbs(data: dict[str, Any]) -> tuple[Orbs | None, list[str]]:
    """Bundles both orb fields with the same short-circuit-on-missing-table
    shape ``_read_bodies``/``_read_rulers``/``_read_harmonic`` already use --
    calling the field-level readers against a table already known to be
    missing would just repeat ``_read_table``'s own error."""
    table, table_error = _read_table(data, "orbs")
    if table_error is not None:
        return None, [table_error]
    errors: list[str] = []
    if (unexpected := _check_unexpected_keys(table, "orbs", _ORBS_KEYS)) is not None:
        errors.append(unexpected)
    natal, natal_error = _read_orb(table, "orbs", "natal", _NATAL_ORB_MIN, _NATAL_ORB_MAX)
    transit, transit_error = _read_orb(table, "orbs", "transit", _TRANSIT_ORB_MIN, _TRANSIT_ORB_MAX)
    errors.extend(error for error in (natal_error, transit_error) if error is not None)
    if errors:
        return None, errors
    assert natal is not None and transit is not None
    return Orbs(natal=natal, transit=transit), []


def _read_house_system_field(data: dict[str, Any]) -> tuple[HouseSystem | None, list[str]]:
    table, table_error = _read_table(data, "house_system")
    if table_error is not None:
        return None, [table_error]
    errors: list[str] = []
    unexpected = _check_unexpected_keys(table, "house_system", _HOUSE_SYSTEM_KEYS)
    if unexpected is not None:
        errors.append(unexpected)
    house_system, house_system_error = _read_house_system(table)
    if house_system_error is not None:
        errors.append(house_system_error)
    if errors:
        return None, errors
    assert house_system is not None
    return house_system, []


def _read_string_list(
    table: dict[str, Any] | None, table_name: str, field: str
) -> tuple[tuple[str, ...] | None, str | None]:
    path = f"{table_name}.{field}"
    if table is None:
        return None, f"{path} is required."
    raw = table.get(field)
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
        return None, f"{path} is required and must be a list of strings, got {raw!r}."
    return tuple(raw), None


_BODIES_KEYS = frozenset({"fast", "slow"})


def _read_bodies(data: dict[str, Any]) -> tuple[Bodies | None, list[str]]:
    table, table_error = _read_table(data, "bodies")
    if table_error is not None:
        return None, [table_error]
    errors: list[str] = []
    if (unexpected := _check_unexpected_keys(table, "bodies", _BODIES_KEYS)) is not None:
        errors.append(unexpected)
    fast, fast_error = _read_string_list(table, "bodies", "fast")
    slow, slow_error = _read_string_list(table, "bodies", "slow")
    errors.extend(error for error in (fast_error, slow_error) if error is not None)
    if errors:
        return None, errors
    assert fast is not None and slow is not None
    return Bodies(fast=fast, slow=slow), []


def _read_ruler_table(
    table: dict[str, Any] | None, path: str
) -> tuple[MappingProxyType[str, str] | None, str | None]:
    if table is None:
        return None, f"{path} is required."
    missing = [sign for sign in _ZODIAC_SIGNS if sign not in table]
    unexpected = [key for key in table if key not in _ZODIAC_SIGNS]
    non_string = [
        sign
        for sign in _ZODIAC_SIGNS
        if sign in table and not isinstance(table[sign], str)
    ]
    if missing or unexpected or non_string:
        problems = []
        if missing:
            problems.append(f"missing sign(s) {', '.join(missing)}")
        if unexpected:
            problems.append(f"unexpected key(s) {', '.join(unexpected)}")
        if non_string:
            problems.append(f"non-string value(s) for {', '.join(non_string)}")
        return None, f"{path} is invalid: {'; '.join(problems)}."
    return MappingProxyType({sign: table[sign] for sign in _ZODIAC_SIGNS}), None


_RULERS_KEYS = frozenset({"traditional", "modern"})


def _read_rulers(data: dict[str, Any]) -> tuple[Rulers | None, list[str]]:
    table, table_error = _read_table(data, "rulers")
    if table_error is not None:
        return None, [table_error]
    errors: list[str] = []
    if (unexpected := _check_unexpected_keys(table, "rulers", _RULERS_KEYS)) is not None:
        errors.append(unexpected)
    traditional_table = table.get("traditional")
    modern_table = table.get("modern")
    traditional, traditional_error = _read_ruler_table(
        traditional_table if isinstance(traditional_table, dict) else None,
        "rulers.traditional",
    )
    modern, modern_error = _read_ruler_table(
        modern_table if isinstance(modern_table, dict) else None,
        "rulers.modern",
    )
    errors.extend(error for error in (traditional_error, modern_error) if error is not None)
    if errors:
        return None, errors
    assert traditional is not None and modern is not None
    return Rulers(traditional=traditional, modern=modern), []


_HARMONIC_FIELDS = (
    "harmonic_aspects",
    "disharmonic_aspects",
    "harmonic_conjunction_bodies",
    "disharmonic_conjunction_bodies",
)
_HARMONIC_KEYS = frozenset(_HARMONIC_FIELDS)


def _read_harmonic(data: dict[str, Any]) -> tuple[HarmonicRule | None, list[str]]:
    table, table_error = _read_table(data, "harmonic")
    if table_error is not None:
        return None, [table_error]
    values: dict[str, tuple[str, ...]] = {}
    errors: list[str] = []
    if (unexpected := _check_unexpected_keys(table, "harmonic", _HARMONIC_KEYS)) is not None:
        errors.append(unexpected)
    for field in _HARMONIC_FIELDS:
        value, error = _read_string_list(table, "harmonic", field)
        if error is not None:
            errors.append(error)
        else:
            assert value is not None
            values[field] = value
    if errors:
        return None, errors
    return (
        HarmonicRule(
            harmonic_aspects=values["harmonic_aspects"],
            disharmonic_aspects=values["disharmonic_aspects"],
            harmonic_conjunction_bodies=values["harmonic_conjunction_bodies"],
            disharmonic_conjunction_bodies=values["disharmonic_conjunction_bodies"],
        ),
        [],
    )


def load_computation_config(path: Path = DEFAULT_COMPUTATION_PATH) -> ComputationConfig:
    """Read, hash and validate ``path`` into a frozen :class:`ComputationConfig`.

    Every field is checked before anything is reported, so a malformed file
    names every offender at once rather than one per attempt -- mirroring
    ``shell/config.py``'s ``load_settings()``.

    Raises:
        ComputationConfigError: naming the missing file, the malformed TOML,
            or each offending field -- never a raw ``FileNotFoundError``,
            ``TOMLDecodeError`` or ``KeyError``.
    """
    raw = _read_bytes(path)
    data = _parse_toml(raw, path)

    version, version_error = _read_version(data)
    orbs, orbs_errors = _read_orbs(data)
    house_system, house_system_errors = _read_house_system_field(data)
    bodies, bodies_errors = _read_bodies(data)
    rulers, rulers_errors = _read_rulers(data)
    harmonic, harmonic_errors = _read_harmonic(data)

    problems = [
        problem
        for problem in (
            version_error,
            *orbs_errors,
            *house_system_errors,
            *bodies_errors,
            *rulers_errors,
            *harmonic_errors,
        )
        if problem is not None
    ]
    if problems:
        raise ComputationConfigError(
            f"Refusing to start: {path} is not a valid computation configuration.\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )

    assert (
        version is not None
        and orbs is not None
        and house_system is not None
        and bodies is not None
        and rulers is not None
        and harmonic is not None
    )
    return ComputationConfig(
        version=version,
        content_hash=hashlib.sha256(raw).hexdigest(),
        orbs=orbs,
        house_system=house_system,
        bodies=bodies,
        rulers=rulers,
        harmonic=harmonic,
    )
