"""Unit tests for ``tests/conformance/runner.py`` (Story 1.6).

Mirrors the "prove the guard can fail" pattern of
``tests/test_import_boundary.py`` and ``tests/test_env_access_is_centralized.py``:
AC3 (a mismatch names the fixture, the field, the expected value and the
computed value) is proven here against synthetic fixtures with a
deliberately-wrong value -- without any real astronomy, since none exists
yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conformance.runner import (
    Fixture,
    FixtureFormatError,
    Mismatch,
    compare,
    discover_fixtures,
    load_fixture,
)

_VALID_FIXTURE_TOML = """
[metadata]
name = "synthetic"
adversarial_case = "unit test fixture, not a real chart"

[birth_data]
date = "2000-01-01"
time = "12:00:00"

[expected]
sun_sign = "capricorn"

[[expected.planets]]
name = "sun"
longitude = "280.5"

[[expected.planets]]
name = "moon"
longitude = "10.25"
"""


# --- discover_fixtures --------------------------------------------------------


def test_discover_fixtures_on_empty_directory_returns_empty_list(tmp_path: Path) -> None:
    fixtures = discover_fixtures(tmp_path)

    assert fixtures == []


def test_discover_fixtures_on_missing_directory_returns_empty_list(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    fixtures = discover_fixtures(missing)

    assert fixtures == []


def test_discover_fixtures_finds_toml_files_sorted(tmp_path: Path) -> None:
    (tmp_path / "b-fixture.toml").write_text(_VALID_FIXTURE_TOML, encoding="utf-8")
    (tmp_path / "a-fixture.toml").write_text(_VALID_FIXTURE_TOML, encoding="utf-8")

    fixtures = discover_fixtures(tmp_path)

    assert [path.name for path in fixtures] == ["a-fixture.toml", "b-fixture.toml"]


def test_discover_fixtures_ignores_non_toml_files(tmp_path: Path) -> None:
    (tmp_path / "fixture.toml").write_text(_VALID_FIXTURE_TOML, encoding="utf-8")
    (tmp_path / "README.md").write_text("# not a fixture\n", encoding="utf-8")

    fixtures = discover_fixtures(tmp_path)

    assert [path.name for path in fixtures] == ["fixture.toml"]


def test_the_default_fixtures_directory_reports_zero_fixtures() -> None:
    """The shipped, empty ``tests/conformance/fixtures/`` never raises."""
    fixtures = discover_fixtures()

    assert fixtures == []


# --- load_fixture ---------------------------------------------------------


def test_load_fixture_parses_metadata_birth_data_and_expected(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.toml"
    path.write_text(_VALID_FIXTURE_TOML, encoding="utf-8")

    fixture = load_fixture(path)

    assert isinstance(fixture, Fixture)
    assert fixture.name == "synthetic"
    assert fixture.path == path
    assert fixture.metadata == {
        "name": "synthetic",
        "adversarial_case": "unit test fixture, not a real chart",
    }
    assert fixture.birth_data == {"date": "2000-01-01", "time": "12:00:00"}
    assert fixture.expected["sun_sign"] == "capricorn"
    assert fixture.expected["planets"][0] == {"name": "sun", "longitude": "280.5"}


def test_load_fixture_rejects_a_missing_required_table(tmp_path: Path) -> None:
    path = tmp_path / "incomplete.toml"
    path.write_text('[metadata]\nname = "incomplete"\n', encoding="utf-8")

    with pytest.raises(FixtureFormatError, match="missing required table"):
        load_fixture(path)


def test_load_fixture_rejects_malformed_toml(tmp_path: Path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("this is not [ valid toml\n", encoding="utf-8")

    with pytest.raises(FixtureFormatError, match="not valid TOML"):
        load_fixture(path)


def test_load_fixture_reports_a_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.toml"

    with pytest.raises(FixtureFormatError, match="could not be read"):
        load_fixture(missing)


def test_load_fixture_reports_non_utf8_bytes_cleanly_rather_than_crashing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "not-utf8.toml"
    path.write_bytes(b"[metadata]\nname = \"\xff\xfe bad bytes\"\n")

    with pytest.raises(FixtureFormatError, match="could not be read"):
        load_fixture(path)


@pytest.mark.parametrize("table", ["metadata", "birth_data", "expected"])
def test_load_fixture_rejects_a_required_table_that_is_not_a_table(
    tmp_path: Path, table: str
) -> None:
    """A required key can be *present* while still being the wrong TOML type
    (e.g. ``expected = "oops"`` instead of a table) -- present-but-wrong must
    fail loudly and name the offender, same as absent."""
    tables = {
        "metadata": '[metadata]\nname = "x"',
        "birth_data": "[birth_data]",
        "expected": "[expected]",
    }
    del tables[table]
    # The plain `key = value` line must come before any `[table]` header --
    # TOML attributes a bare assignment after a header to that table, not
    # to the implicit root table.
    content = f'{table} = "not a table"\n' + "\n".join(tables.values()) + "\n"
    path = tmp_path / "wrong-type.toml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(FixtureFormatError, match=f"{table} is a str, not a table"):
        load_fixture(path)


# --- compare ----------------------------------------------------------------


def test_compare_reports_no_mismatches_when_everything_matches() -> None:
    expected = {"sun_sign": "capricorn", "planets": [{"name": "sun", "longitude": "280.5"}]}
    computed = {"sun_sign": "capricorn", "planets": [{"name": "sun", "longitude": "280.5"}]}

    mismatches = compare("synthetic", expected, computed)

    assert mismatches == []


def test_compare_detects_a_deliberately_wrong_scalar_value() -> None:
    """AC3: names the fixture, the field, the expected value and the computed value."""
    expected = {"sun_sign": "capricorn"}
    computed = {"sun_sign": "sagittarius"}  # deliberately wrong

    mismatches = compare("synthetic", expected, computed)

    assert mismatches == [Mismatch("synthetic", "expected.sun_sign", "capricorn", "sagittarius")]


def test_compare_builds_a_dotted_path_through_nested_lists() -> None:
    """Matches the story's own example: ``expected.planets[0].longitude``."""
    expected = {"planets": [{"name": "sun", "longitude": "280.5"}]}
    computed = {"planets": [{"name": "sun", "longitude": "999.9"}]}  # deliberately wrong

    mismatches = compare("synthetic", expected, computed)

    assert mismatches == [
        Mismatch("synthetic", "expected.planets[0].longitude", "280.5", "999.9")
    ]


def test_compare_detects_a_missing_key() -> None:
    expected = {"sun_sign": "capricorn", "moon_sign": "aries"}
    computed = {"sun_sign": "capricorn"}  # moon_sign missing entirely

    mismatches = compare("synthetic", expected, computed)

    assert len(mismatches) == 1
    mismatch = mismatches[0]
    assert mismatch.fixture == "synthetic"
    assert mismatch.field == "expected.moon_sign"
    assert mismatch.expected == "aries"
    assert repr(mismatch.computed) == "<missing>"


def test_compare_detects_a_list_length_mismatch() -> None:
    expected = {"planets": [{"name": "sun"}, {"name": "moon"}]}
    computed = {"planets": [{"name": "sun"}]}  # one planet short

    mismatches = compare("synthetic", expected, computed)

    assert mismatches == [
        Mismatch("synthetic", "expected.planets", expected["planets"], computed["planets"])
    ]


def test_compare_reports_every_mismatch_not_just_the_first() -> None:
    expected = {"sun_sign": "capricorn", "moon_sign": "aries"}
    computed = {"sun_sign": "sagittarius", "moon_sign": "leo"}  # both wrong

    mismatches = compare("synthetic", expected, computed)

    assert {mismatch.field for mismatch in mismatches} == {
        "expected.sun_sign",
        "expected.moon_sign",
    }
    assert len(mismatches) == 2


def test_compare_does_not_report_extra_keys_present_only_in_computed() -> None:
    """Conformance means computed output *contains* expected values, not that
    it contains nothing else."""
    expected = {"sun_sign": "capricorn"}
    computed = {"sun_sign": "capricorn", "ascendant": "leo"}

    mismatches = compare("synthetic", expected, computed)

    assert mismatches == []
