"""Gate vocabulary loading -- one test per row of Story 5.1's I/O matrix,
plus the properties the matrix implies: the value is frozen and the shipped
``core/gate/vocabulary.it.json`` loads without error.

Mirrors ``tests/test_sections_config.py``'s own structure -- Story 5.1's Code
Map names it as this module's precedent.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from core.errors import GateVocabularyError
from core.types.gate import GateVocabulary
from shell.gate import DEFAULT_VOCABULARY_PATH, load_gate_vocabulary

_VALID_VOCABULARY: dict[str, object] = {
    "version": 1,
    "planets": [
        "sole",
        "luna",
        "mercurio",
        "venere",
        "marte",
        "giove",
        "saturno",
        "urano",
        "nettuno",
        "plutone",
    ],
    "signs": [
        "ariete",
        "toro",
        "gemelli",
        "cancro",
        "leone",
        "vergine",
        "bilancia",
        "scorpione",
        "sagittario",
        "capricorno",
        "acquario",
        "pesci",
    ],
    "casa_ordinals": [
        "prima",
        "seconda",
        "terza",
        "quarta",
        "quinta",
        "sesta",
        "settima",
        "ottava",
        "nona",
        "decima",
        "undicesima",
        "dodicesima",
    ],
    "day_of_month_pattern": r"\b([1-9]|[12][0-9]|3[01])\b",
    "retrogrado": "retrogrado",
    "stazionario": "stazionario",
}


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "vocabulary.it.json"
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- Matrix row: valid file --------------------------------------------------


def test_a_valid_file_returns_a_populated_frozen_vocabulary(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_VOCABULARY)

    vocabulary = load_gate_vocabulary(path)

    assert isinstance(vocabulary, GateVocabulary)
    assert vocabulary.version == 1
    assert vocabulary.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert vocabulary.planets == frozenset(_VALID_VOCABULARY["planets"])  # type: ignore[arg-type]
    assert vocabulary.signs == frozenset(_VALID_VOCABULARY["signs"])  # type: ignore[arg-type]
    assert vocabulary.casa_ordinals == frozenset(
        _VALID_VOCABULARY["casa_ordinals"]  # type: ignore[arg-type]
    )
    assert vocabulary.day_of_month_pattern == _VALID_VOCABULARY["day_of_month_pattern"]
    assert vocabulary.retrogrado == "retrogrado"
    assert vocabulary.stazionario == "stazionario"


def test_content_hash_is_the_sha256_of_the_raw_file_bytes_not_a_field_in_the_file(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, _VALID_VOCABULARY)

    vocabulary = load_gate_vocabulary(path)

    assert "content_hash" not in path.read_text(encoding="utf-8")
    assert vocabulary.content_hash == hashlib.sha256(path.read_bytes()).hexdigest()


# --- Matrix row: missing file -------------------------------------------------


def test_a_missing_file_fails_with_a_typed_error_naming_the_path(tmp_path: Path) -> None:
    path = tmp_path / "does-not-exist.json"

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    assert str(path) in str(raised.value)


# --- Matrix row: malformed JSON ------------------------------------------------


def test_malformed_json_fails_with_a_typed_error_naming_the_parse_failure(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "this is not { valid json")

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    message = str(raised.value)
    assert str(path) in message
    assert "JSON" in message


def test_a_top_level_json_value_that_is_not_an_object_fails_with_a_typed_error(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "[1, 2, 3]")

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    message = str(raised.value)
    assert str(path) in message
    assert "JSON object" in message


def test_invalid_utf8_bytes_fail_with_a_typed_error_naming_the_decode_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "vocabulary.it.json"
    path.write_bytes(b"\xff\xfe\x00\x01")

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    message = str(raised.value)
    assert str(path) in message
    assert "UTF-8" in message


# --- Matrix row: missing category key ------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["planets", "signs", "casa_ordinals", "day_of_month_pattern", "retrogrado", "stazionario"],
)
def test_a_missing_required_key_fails_and_names_the_key(tmp_path: Path, field: str) -> None:
    data = {key: value for key, value in _VALID_VOCABULARY.items() if key != field}
    path = _write(tmp_path, data)

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    message = str(raised.value)
    assert field in message


# --- Matrix row: wrong-shaped value, naming every offender at once ------------


def test_a_non_string_list_entry_and_a_non_integer_version_are_both_named_at_once(
    tmp_path: Path,
) -> None:
    data = dict(_VALID_VOCABULARY)
    data["version"] = "1"
    data["planets"] = ["sole", 42]
    path = _write(tmp_path, data)

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    message = str(raised.value)
    assert "version" in message
    assert "planets" in message


@pytest.mark.parametrize("field", ["planets", "signs", "casa_ordinals"])
def test_an_empty_list_value_is_rejected(tmp_path: Path, field: str) -> None:
    data = dict(_VALID_VOCABULARY)
    data[field] = []
    path = _write(tmp_path, data)

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    message = str(raised.value)
    assert field in message


def test_an_unexpected_top_level_key_is_flagged(tmp_path: Path) -> None:
    data = dict(_VALID_VOCABULARY)
    data["bogus"] = "value"
    path = _write(tmp_path, data)

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    message = str(raised.value)
    assert "bogus" in message


def test_an_invalid_day_of_month_regex_is_flagged(tmp_path: Path) -> None:
    data = dict(_VALID_VOCABULARY)
    data["day_of_month_pattern"] = "[unclosed"
    path = _write(tmp_path, data)

    with pytest.raises(GateVocabularyError) as raised:
        load_gate_vocabulary(path)

    message = str(raised.value)
    assert "day_of_month_pattern" in message


# --- Matrix row: vocabulary revised --------------------------------------------


def test_revising_the_vocabulary_bumps_version_and_changes_content_hash(
    tmp_path: Path,
) -> None:
    original = load_gate_vocabulary(_write(tmp_path, _VALID_VOCABULARY))

    revised_data = dict(_VALID_VOCABULARY)
    revised_data["version"] = 2
    revised_data["planets"] = [*_VALID_VOCABULARY["planets"], "chirone"]  # type: ignore[misc]
    revised = load_gate_vocabulary(_write(tmp_path, revised_data))

    assert revised.version == 2
    assert revised.version != original.version
    assert revised.content_hash != original.content_hash


# --- Frozen -------------------------------------------------------------------


def test_gate_vocabulary_is_frozen(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_VOCABULARY)
    vocabulary = load_gate_vocabulary(path)

    assert dataclasses.is_dataclass(vocabulary)
    assert type(vocabulary).__dataclass_params__.frozen is True

    with pytest.raises(dataclasses.FrozenInstanceError):
        vocabulary.version = 2  # type: ignore[misc]


# --- The shipped file itself ---------------------------------------------------


def test_the_shipped_file_loads_without_error() -> None:
    vocabulary = load_gate_vocabulary(DEFAULT_VOCABULARY_PATH)

    assert vocabulary.version == 1
    assert len(vocabulary.planets) == 10
    assert len(vocabulary.signs) == 12
    assert len(vocabulary.casa_ordinals) == 12
    assert vocabulary.retrogrado == "retrogrado"
    assert vocabulary.stazionario == "stazionario"


def test_load_gate_vocabulary_defaults_to_the_shipped_file() -> None:
    assert load_gate_vocabulary().content_hash == load_gate_vocabulary(
        DEFAULT_VOCABULARY_PATH
    ).content_hash
