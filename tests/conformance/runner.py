"""Fixture-walking conformance runner.

Generic on purpose: no Epic 2/3 domain type (``NatalChart``, ``TransitEvent``,
...) is invented here. A fixture is TOML with three tables -- ``metadata``,
``birth_data`` and ``expected`` -- and :func:`compare` walks ``expected``
against computed output as plain nested dicts/lists, building a dotted field
path (e.g. ``expected.planets[0].longitude``) for any mismatch. When Epic
2/3 land, wiring in real computation means writing one function that
produces a matching dict, not redesigning this module (see the story's
Design Notes).

This lives under ``tests/`` rather than ``shell/`` or ``core/``: it is test
support code, not application code, and so is exempt from the purity
boundary and single-environment-reader guards the way the rest of ``tests/``
already is (``SOURCE_ROOTS`` in ``tests/test_env_access_is_centralized.py``
covers only ``core``, ``shell`` and ``migrations``).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Where real fixtures live once Story 1.7 adds them. Ships empty.
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: The three tables every fixture must declare, even if a table is empty.
_REQUIRED_TABLES = ("metadata", "birth_data", "expected")


class FixtureFormatError(ValueError):
    """A fixture file is not well-formed TOML, or is missing a required table."""


class _Missing:
    """Sentinel reported as the computed side when an expected key is absent."""

    def __repr__(self) -> str:
        return "<missing>"


#: A single instance is enough -- it is only ever compared by identity/repr.
_MISSING = _Missing()


@dataclass(frozen=True)
class Fixture:
    """A single parsed conformance fixture.

    ``name`` is the file stem (e.g. ``"leap-day-birth"``) -- stable and
    always present, unlike anything inside ``metadata`` -- so it is what
    mismatch reports and parametrized test IDs use to name the fixture.
    """

    name: str
    path: Path
    metadata: dict[str, Any]
    birth_data: dict[str, Any]
    expected: dict[str, Any]


@dataclass(frozen=True)
class Mismatch:
    """One field where ``expected`` and computed output disagree.

    ``field`` is the dotted path from the fixture's ``expected`` table, e.g.
    ``"expected.planets[0].longitude"`` -- AC3's four required facts are the
    four fields of this dataclass.
    """

    fixture: str
    field: str
    expected: Any
    computed: Any


def discover_fixtures(directory: Path | None = None) -> list[Path]:
    """Every ``*.toml`` fixture under ``directory``, sorted for determinism.

    Never raises on an empty or missing directory: CI runs against an empty
    fixture set until Story 1.7, and that must report zero fixtures, not
    fail (AC2).
    """
    target = directory if directory is not None else FIXTURES_DIR
    if not target.is_dir():
        return []
    return sorted(target.glob("*.toml"))


def load_fixture(path: Path) -> Fixture:
    """Parse one fixture file into a :class:`Fixture`.

    Raises :class:`FixtureFormatError` naming the file and the problem for
    malformed TOML or a missing required table -- the same "fail loudly,
    name the offender" convention as ``shell/computation.py``.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise FixtureFormatError(f"{path}: could not be read: {error}") from error

    try:
        document = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as error:
        raise FixtureFormatError(f"{path}: not valid TOML: {error}") from error

    missing = [table for table in _REQUIRED_TABLES if table not in document]
    if missing:
        raise FixtureFormatError(f"{path}: missing required table(s): {', '.join(missing)}")

    not_tables = [
        table for table in _REQUIRED_TABLES if not isinstance(document.get(table), dict)
    ]
    if not_tables:
        problems = ", ".join(
            f"{table} is a {type(document[table]).__name__}, not a table" for table in not_tables
        )
        raise FixtureFormatError(f"{path}: {problems}")

    return Fixture(
        name=path.stem,
        path=path,
        metadata=document["metadata"],
        birth_data=document["birth_data"],
        expected=document["expected"],
    )


def compare(fixture_name: str, expected: Any, computed: Any) -> list[Mismatch]:
    """Recursively diff ``expected`` against ``computed``.

    A plain dict/list walk, not a schema-typed comparison (Design Notes):
    dicts are compared key by key over ``expected``'s keys -- an extra key
    present only in ``computed`` is not reported, since conformance means
    computed output *contains* the expected values, not that it contains
    nothing else -- lists are compared element by element, and anything
    else is compared with ``==``. Every mismatch is collected; this never
    stops at the first one.
    """
    mismatches: list[Mismatch] = []
    _walk(fixture_name, "expected", expected, computed, mismatches)
    return mismatches


def _walk(
    fixture_name: str,
    field: str,
    expected: Any,
    computed: Any,
    mismatches: list[Mismatch],
) -> None:
    if isinstance(expected, dict):
        if not isinstance(computed, dict):
            mismatches.append(Mismatch(fixture_name, field, expected, computed))
            return
        for key, expected_value in expected.items():
            child_field = f"{field}.{key}"
            if key not in computed:
                mismatches.append(Mismatch(fixture_name, child_field, expected_value, _MISSING))
                continue
            _walk(fixture_name, child_field, expected_value, computed[key], mismatches)
        return

    if isinstance(expected, list):
        if not isinstance(computed, list) or len(expected) != len(computed):
            mismatches.append(Mismatch(fixture_name, field, expected, computed))
            return
        for index, (expected_item, computed_item) in enumerate(
            zip(expected, computed, strict=True)
        ):
            _walk(fixture_name, f"{field}[{index}]", expected_item, computed_item, mismatches)
        return

    if expected != computed:
        mismatches.append(Mismatch(fixture_name, field, expected, computed))
