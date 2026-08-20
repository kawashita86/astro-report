"""``load_style_guide_seed()`` -- marker/body parsing, plus every edge case
the marker line can fail on. Mirrors ``tests/test_computation_config.py``'s
own shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shell.style_guide_seed import (
    DEFAULT_STYLE_GUIDE_SEED_PATH,
    StyleGuideSeedError,
    load_style_guide_seed,
)


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "style-guide.seed.md"
    path.write_text(content, encoding="utf-8")
    return path


# --- Valid file -------------------------------------------------------------


def test_a_valid_file_returns_the_body_after_the_marker(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "# Style Guide (v1)\n\n> some administrative note\n\n"
        "version: 1\n\n## Purpose\n\nBody text.\n",
    )

    body = load_style_guide_seed(path)

    assert body == "## Purpose\n\nBody text."


def test_content_before_the_marker_is_discarded(tmp_path: Path) -> None:
    path = _write(tmp_path, "# Title\n\n> a note not meant for the database\n\nversion: 1\n\nKept.")

    body = load_style_guide_seed(path)

    assert "Title" not in body
    assert "a note not meant for the database" not in body
    assert body == "Kept."


def test_the_shipped_seed_file_loads_without_error() -> None:
    body = load_style_guide_seed(DEFAULT_STYLE_GUIDE_SEED_PATH)

    assert body.startswith("## Purpose and how to read this guide")
    assert "## 8. Consiglio astrologico finale" in body


# --- Missing / unreadable file -----------------------------------------------


def test_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(StyleGuideSeedError, match="not found"):
        load_style_guide_seed(tmp_path / "does-not-exist.md")


def test_a_non_utf8_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "style-guide.seed.md"
    path.write_bytes(b"version: 1\n\n\xff\xfe not valid utf-8")

    with pytest.raises(StyleGuideSeedError, match="UTF-8"):
        load_style_guide_seed(path)


# --- Marker missing / malformed / not 1 --------------------------------------


def test_no_marker_line_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "# Style Guide\n\nNo marker here at all.\n")

    with pytest.raises(StyleGuideSeedError, match="marker"):
        load_style_guide_seed(path)


def test_a_non_integer_version_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "version: one\n\nBody.")

    with pytest.raises(StyleGuideSeedError, match="marker"):
        load_style_guide_seed(path)


def test_version_2_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "version: 2\n\nBody.")

    with pytest.raises(StyleGuideSeedError, match="expected 1"):
        load_style_guide_seed(path)


def test_version_0_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "version: 0\n\nBody.")

    with pytest.raises(StyleGuideSeedError, match="expected 1"):
        load_style_guide_seed(path)


def test_an_empty_body_after_the_marker_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "version: 1\n\n   \n")

    with pytest.raises(StyleGuideSeedError, match="no body"):
        load_style_guide_seed(path)
