"""Loads ``data/sections.toml`` into a frozen :class:`SectionsConfig`.

File I/O is shell's job (AD-1): this is the only module that reads
``data/sections.toml``, hashes its bytes and validates its contents.
``core/types/sections.py`` holds the pure, frozen shape the file loads into;
``core/payload/assemble.py`` receives that value explicitly, never the file
path or a module global.

Mirrors ``shell/computation.py``'s validate-and-hash shape: every field is
read and checked before anything is reported, so a malformed file names
every offender at once (``_read_table``/``_check_unexpected_keys``/
error-collection pattern), not one per attempt.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path
from types import MappingProxyType
from typing import Any

from core.errors import SectionsConfigError
from core.types.sections import SectionsConfig, SectionSpec

__all__ = ["DEFAULT_SECTIONS_PATH", "load_sections_config"]

#: The sections config ships alongside the application code -- it is not a
#: deployment fact, so it is not a ``shell/config.py`` setting. Resolved from
#: this file's own location, mirroring ``shell/computation.py``'s
#: ``DEFAULT_COMPUTATION_PATH``.
DEFAULT_SECTIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "sections.toml"

#: The exact six Sections `sections.toml` must define, no more, no fewer.
_SECTION_NAMES: tuple[str, ...] = (
    "energia_generale",
    "amore",
    "lavoro",
    "denaro",
    "benessere",
    "consiglio_finale",
)

_SECTION_KEYS = frozenset(
    {
        "domain_profile",
        "houses",
        "house_bodies",
        "aspect_natal_points",
        "aspect_bodies",
        "retrogrades",
        "include_all_events",
    }
)

#: The only Domain Profiles a Section can name (``core/types/domains.py``'s
#: ``DomainProfiles`` attributes) -- ``assemble_payload()`` resolves this via
#: ``getattr(profiles, name)``, so an unsupported value here would fail
#: obscurely, deep inside assembly, rather than at load time.
_DOMAIN_PROFILE_VALUES = frozenset({"amore", "lavoro", "denaro", "benessere"})

#: The four Section names that must declare their own name as
#: ``domain_profile`` -- every other Section name (``energia_generale``,
#: ``consiglio_finale``) must leave ``domain_profile`` unset. Without this
#: cross-check, nothing would stop e.g. ``[sections.denaro]`` from setting
#: ``domain_profile = "amore"``, silently producing a ``SectionPayload``
#: whose ``profile`` contradicts the Section's own identity.
_DOMAIN_SECTION_NAMES = frozenset({"amore", "lavoro", "denaro", "benessere"})

#: The only ``ComputationConfig.bodies`` selectors a Section can name --
#: ``None`` (absent from the file) means "either", not a third string value.
_BODIES_SELECTOR_VALUES = frozenset({"fast", "slow"})

_MIN_HOUSE = 1
_MAX_HOUSE = 12


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise SectionsConfigError(
            f"Refusing to start: sections config not found at {path}: {error}."
        ) from error


def _parse_toml(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise SectionsConfigError(
            f"Refusing to start: sections config {path} could not be decoded as UTF-8: "
            f"{error}."
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise SectionsConfigError(
            f"Refusing to start: sections config {path} is not valid TOML: {error}."
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
    unexpected = sorted(key for key in table if key not in expected)
    if unexpected:
        return f"[{table_name}] has unexpected key(s): {', '.join(unexpected)}."
    return None


def _read_optional_bool(
    table: dict[str, Any], table_name: str, field: str, default: bool
) -> tuple[bool, str | None]:
    if field not in table:
        return default, None
    raw = table[field]
    if not isinstance(raw, bool):
        return default, f"{table_name}.{field} must be a boolean, got {raw!r}."
    return raw, None


def _read_optional_enum(
    table: dict[str, Any], table_name: str, field: str, allowed: frozenset[str]
) -> tuple[str | None, str | None]:
    if field not in table:
        return None, None
    raw = table[field]
    if not isinstance(raw, str) or raw not in allowed:
        return None, (
            f"{table_name}.{field} is invalid: {raw!r} (must be one of "
            f"{', '.join(sorted(allowed))})."
        )
    return raw, None


def _read_optional_string_tuple(
    table: dict[str, Any], table_name: str, field: str
) -> tuple[tuple[str, ...], str | None]:
    if field not in table:
        return (), None
    raw = table[field]
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return (), f"{table_name}.{field} must be a list of strings, got {raw!r}."
    return tuple(raw), None


def _read_optional_house_tuple(
    table: dict[str, Any], table_name: str, field: str
) -> tuple[tuple[int, ...], str | None]:
    if field not in table:
        return (), None
    raw = table[field]
    if not isinstance(raw, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in raw
    ):
        return (), f"{table_name}.{field} must be a list of integers, got {raw!r}."
    out_of_range = [item for item in raw if not (_MIN_HOUSE <= item <= _MAX_HOUSE)]
    if out_of_range:
        return (), f"{table_name}.{field} has house number(s) outside 1-12: {out_of_range!r}."
    return tuple(raw), None


def _read_section_spec(
    table: dict[str, Any], table_name: str, name: str
) -> tuple[SectionSpec | None, list[str]]:
    errors: list[str] = []
    unexpected = _check_unexpected_keys(table, table_name, _SECTION_KEYS)
    if unexpected is not None:
        errors.append(unexpected)

    domain_profile, domain_profile_error = _read_optional_enum(
        table, table_name, "domain_profile", _DOMAIN_PROFILE_VALUES
    )
    if domain_profile_error is None:
        if name in _DOMAIN_SECTION_NAMES and domain_profile != name:
            errors.append(
                f"{table_name}.domain_profile must equal {name!r} (its own Section "
                f"name), got {domain_profile!r}."
            )
        elif name not in _DOMAIN_SECTION_NAMES and domain_profile is not None:
            errors.append(
                f"{table_name}.domain_profile must be absent for {name!r} (no single "
                f"Domain Profile), got {domain_profile!r}."
            )
    houses, houses_error = _read_optional_house_tuple(table, table_name, "houses")
    house_bodies, house_bodies_error = _read_optional_enum(
        table, table_name, "house_bodies", _BODIES_SELECTOR_VALUES
    )
    aspect_natal_points, aspect_natal_points_error = _read_optional_string_tuple(
        table, table_name, "aspect_natal_points"
    )
    aspect_bodies, aspect_bodies_error = _read_optional_enum(
        table, table_name, "aspect_bodies", _BODIES_SELECTOR_VALUES
    )
    retrogrades, retrogrades_error = _read_optional_bool(table, table_name, "retrogrades", False)
    include_all_events, include_all_events_error = _read_optional_bool(
        table, table_name, "include_all_events", False
    )

    errors.extend(
        error
        for error in (
            domain_profile_error,
            houses_error,
            house_bodies_error,
            aspect_natal_points_error,
            aspect_bodies_error,
            retrogrades_error,
            include_all_events_error,
        )
        if error is not None
    )
    if errors:
        return None, errors

    return (
        SectionSpec(
            domain_profile=domain_profile,
            houses=houses,
            house_bodies=house_bodies,
            aspect_natal_points=aspect_natal_points,
            aspect_bodies=aspect_bodies,
            retrogrades=retrogrades,
            include_all_events=include_all_events,
        ),
        [],
    )


def _read_sections(
    data: dict[str, Any],
) -> tuple[MappingProxyType[str, SectionSpec] | None, list[str]]:
    table, table_error = _read_table(data, "sections")
    if table_error is not None:
        return None, [table_error]

    errors: list[str] = []
    unexpected = _check_unexpected_keys(table, "sections", frozenset(_SECTION_NAMES))
    if unexpected is not None:
        errors.append(unexpected)

    missing = [name for name in _SECTION_NAMES if name not in table]
    if missing:
        errors.append(f"[sections] is missing required section(s): {', '.join(missing)}.")

    sections: dict[str, SectionSpec] = {}
    for name in _SECTION_NAMES:
        if name not in table:
            continue
        raw = table[name]
        if not isinstance(raw, dict):
            errors.append(f"[sections.{name}] is required and must be a table, got {raw!r}.")
            continue
        spec, spec_errors = _read_section_spec(raw, f"sections.{name}", name)
        if spec_errors:
            errors.extend(spec_errors)
            continue
        assert spec is not None
        sections[name] = spec

    if errors:
        return None, errors

    return MappingProxyType(sections), []


def load_sections_config(path: Path = DEFAULT_SECTIONS_PATH) -> SectionsConfig:
    """Read, hash and validate ``path`` into a frozen :class:`SectionsConfig`.

    Every field is checked before anything is reported, so a malformed file
    names every offender at once rather than one per attempt -- mirroring
    ``shell/computation.py``'s ``load_computation_config()``.

    Raises:
        SectionsConfigError: naming the missing file, the malformed TOML,
            each missing/unexpected Section key, or each offending field --
            never a raw ``FileNotFoundError``, ``TOMLDecodeError`` or
            ``KeyError``.
    """
    raw = _read_bytes(path)
    data = _parse_toml(raw, path)

    version, version_error = _read_version(data)
    sections, sections_errors = _read_sections(data)

    problems = [problem for problem in (version_error, *sections_errors) if problem is not None]
    if problems:
        raise SectionsConfigError(
            f"Refusing to start: {path} is not a valid sections configuration.\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )

    assert version is not None and sections is not None
    return SectionsConfig(
        version=version,
        content_hash=hashlib.sha256(raw).hexdigest(),
        sections=sections,
    )
