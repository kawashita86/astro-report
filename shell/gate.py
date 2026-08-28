"""Loads ``core/gate/vocabulary.it.json`` into a frozen :class:`GateVocabulary`.

File I/O is shell's job (AD-1): this is the only module that reads
``vocabulary.it.json``, hashes its bytes and validates its contents.
``core/types/gate.py`` holds the pure, frozen shape the file loads into;
``core/gate/classify.py::is_claim()`` receives that value explicitly, never
the file path or a module global.

Mirrors ``shell/sections.py``'s validate-and-hash shape, swapping ``tomllib``
for ``json``. JSON has no comments, so the hand-bumped-``version`` convention
``data/sections.toml`` states in its own header comment is restated here
instead: ``version`` in ``vocabulary.it.json`` is bumped by hand on every
edit; the file's ``content_hash`` is computed by this loader from the raw
bytes and is never itself a field in the file.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from core.errors import GateVocabularyError
from core.gate.run import TRANSLATABLE_VOCABULARY
from core.types.gate import GateVocabulary

__all__ = ["DEFAULT_VOCABULARY_PATH", "load_gate_vocabulary"]

#: The gate vocabulary ships alongside the application code -- it is not a
#: deployment fact, so it is not a ``shell/config.py`` setting. Resolved from
#: this file's own location, mirroring ``shell/sections.py``'s
#: ``DEFAULT_SECTIONS_PATH``.
DEFAULT_VOCABULARY_PATH = (
    Path(__file__).resolve().parent.parent / "core" / "gate" / "vocabulary.it.json"
)

#: The exact six categories `vocabulary.it.json` must define (AD-8), no more,
#: no fewer -- three closed word lists and three single-token/pattern fields.
_STRING_LIST_FIELDS: tuple[str, ...] = ("planets", "signs", "casa_ordinals")
_STRING_FIELDS: tuple[str, ...] = ("day_of_month_pattern", "retrogrado", "stazionario")
_REQUIRED_FIELDS = frozenset({"version", *_STRING_LIST_FIELDS, *_STRING_FIELDS})


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise GateVocabularyError(
            f"Refusing to start: gate vocabulary not found at {path}: {error}."
        ) from error


def _parse_json(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GateVocabularyError(
            f"Refusing to start: gate vocabulary {path} could not be decoded as UTF-8: "
            f"{error}."
        ) from error
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as error:
        raise GateVocabularyError(
            f"Refusing to start: gate vocabulary {path} is not valid JSON: {error}."
        ) from error
    if not isinstance(data, dict):
        raise GateVocabularyError(
            f"Refusing to start: gate vocabulary {path} must be a JSON object, got "
            f"{type(data).__name__}."
        )
    return data


def _check_missing_keys(data: dict[str, Any]) -> str | None:
    missing = sorted(field for field in _REQUIRED_FIELDS if field not in data)
    if missing:
        return f"vocabulary is missing required key(s): {', '.join(missing)}."
    return None


def _check_unexpected_keys(data: dict[str, Any]) -> str | None:
    unexpected = sorted(key for key in data if key not in _REQUIRED_FIELDS)
    if unexpected:
        return f"vocabulary has unexpected key(s): {', '.join(unexpected)}."
    return None


def _read_version(data: dict[str, Any]) -> tuple[int | None, str | None]:
    if "version" not in data:
        return None, None  # already reported by _check_missing_keys
    raw = data["version"]
    if not isinstance(raw, int) or isinstance(raw, bool):
        return None, f"version is required and must be an integer, got {raw!r}."
    return raw, None


def _read_string_list(
    data: dict[str, Any], field: str
) -> tuple[frozenset[str] | None, str | None]:
    if field not in data:
        return None, None  # already reported by _check_missing_keys
    raw = data[field]
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
        return None, f"{field} must be a non-empty list of strings, got {raw!r}."
    return frozenset(raw), None


def _read_string(data: dict[str, Any], field: str) -> tuple[str | None, str | None]:
    if field not in data:
        return None, None  # already reported by _check_missing_keys
    raw = data[field]
    if not isinstance(raw, str) or not raw:
        return None, f"{field} must be a non-empty string, got {raw!r}."
    return raw, None


def _check_translation_coverage(
    parsed_lists: tuple[frozenset[str] | None, ...],
) -> list[str]:
    """Cross-check the three closed word lists against ``core/gate/run.py``'s
    hardcoded translation maps (``TRANSLATABLE_VOCABULARY``), both directions
    (epic-5-retro-item-41).

    A ``planets``/``signs``/``casa_ordinals`` word with no matching map entry
    is the dangerous case: ``is_claim()`` flags it as a Claim while
    ``run_gate()`` has no translation, so that category is checked as an
    empty asserted set and can pass ungrounded. A map key with no matching
    vocabulary word is only latent drift. Both are reported so the two
    artifacts stay provably in lockstep.

    ``parsed_lists`` is the ``planets``/``signs``/``casa_ordinals`` frozensets
    in ``_STRING_LIST_FIELDS`` order; a list that failed to parse comes
    through as ``None`` and only *that* category is skipped (its shape error
    is already reported) -- every list that did parse is still checked, so
    one load attempt names every offender at once.
    """
    problems: list[str] = []
    for field, words in zip(_STRING_LIST_FIELDS, parsed_lists, strict=True):
        if words is None:
            continue
        translatable = TRANSLATABLE_VOCABULARY[field]
        untranslated = sorted(words - translatable)
        if untranslated:
            problems.append(
                f"{field} has word(s) with no translation-map entry in core/gate/run.py: "
                f"{', '.join(untranslated)}."
            )
        orphan_keys = sorted(translatable - words)
        if orphan_keys:
            problems.append(
                f"core/gate/run.py's translation map for {field} has key(s) with no matching "
                f"vocabulary word: {', '.join(orphan_keys)}."
            )
    return problems


def _read_day_of_month_pattern(data: dict[str, Any]) -> tuple[str | None, str | None]:
    value, error = _read_string(data, "day_of_month_pattern")
    if error is not None or value is None:
        return value, error
    try:
        re.compile(value)
    except re.error as compile_error:
        return None, f"day_of_month_pattern is not a valid regular expression: {compile_error}."
    return value, None


def load_gate_vocabulary(path: Path = DEFAULT_VOCABULARY_PATH) -> GateVocabulary:
    """Read, hash and validate ``path`` into a frozen :class:`GateVocabulary`.

    Every field is checked before anything is reported, so a malformed file
    names every offender at once rather than one per attempt -- mirroring
    ``shell/sections.py``'s ``load_sections_config()``.

    Raises:
        GateVocabularyError: naming the missing file, the malformed JSON,
            each missing/unexpected key, or each offending field -- never a
            raw ``FileNotFoundError``, ``JSONDecodeError`` or ``KeyError``.
    """
    raw = _read_bytes(path)
    data = _parse_json(raw, path)

    missing_error = _check_missing_keys(data)
    unexpected_error = _check_unexpected_keys(data)

    version, version_error = _read_version(data)
    planets, planets_error = _read_string_list(data, "planets")
    signs, signs_error = _read_string_list(data, "signs")
    casa_ordinals, casa_ordinals_error = _read_string_list(data, "casa_ordinals")
    day_of_month_pattern, day_of_month_pattern_error = _read_day_of_month_pattern(data)
    retrogrado, retrogrado_error = _read_string(data, "retrogrado")
    stazionario, stazionario_error = _read_string(data, "stazionario")

    problems = [
        problem
        for problem in (
            missing_error,
            unexpected_error,
            version_error,
            planets_error,
            signs_error,
            casa_ordinals_error,
            day_of_month_pattern_error,
            retrogrado_error,
            stazionario_error,
        )
        if problem is not None
    ]
    problems += _check_translation_coverage((planets, signs, casa_ordinals))
    if problems:
        raise GateVocabularyError(
            f"Refusing to start: {path} is not a valid gate vocabulary.\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )

    assert (
        version is not None
        and planets is not None
        and signs is not None
        and casa_ordinals is not None
        and day_of_month_pattern is not None
        and retrogrado is not None
        and stazionario is not None
    )
    return GateVocabulary(
        version=version,
        content_hash=hashlib.sha256(raw).hexdigest(),
        planets=planets,
        signs=signs,
        casa_ordinals=casa_ordinals,
        day_of_month_pattern=day_of_month_pattern,
        retrogrado=retrogrado,
        stazionario=stazionario,
    )
