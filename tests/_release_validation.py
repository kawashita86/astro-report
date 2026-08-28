"""Shared scaffolding for the ``docs/release-validation/*.md`` record-guard
suites (epic-8-retro-item-62).

``test_data_terms_record.py`` / ``test_latency_record.py`` /
``test_storage_growth_record.py`` / ``test_restore.py`` each carried a
byte-identical copy of ``REPO_ROOT``, the ```` ```toml ```` block regex, its
extractor, and the module-scoped ``meta`` fixture body. They live here once
now. Each record test module keeps its own ``RECORD_FILE`` path and a thin
``meta`` fixture that delegates to :func:`load_record_meta`.

:func:`assert_not_stale` is the one genuinely new thing the retro asks for --
a shared "``checked`` is not more than ``max_age_days`` old" assertion, wired
into each module's always-on guard block.
"""

from __future__ import annotations

import datetime
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The fenced ```` ```toml ```` block every release-validation record carries
#: its machine-readable fields in -- parsed with ``tomllib`` (stdlib); no YAML
#: parser is a dependency in this repo.
TOML_BLOCK = re.compile(r"^```toml\n(.*?)\n```", re.DOTALL | re.MULTILINE)


def extract_toml_block(text: str, *, record_label: str) -> str:
    """The body of ``text``'s first ```` ```toml ```` fenced block."""
    match = TOML_BLOCK.search(text)
    assert match is not None, (
        f"the {record_label} record has no ```toml fenced block -- the "
        "machine-readable record is missing or malformed"
    )
    return match.group(1)


def load_record_meta(record_file: Path, *, record_label: str) -> dict[str, object]:
    """Parse ``record_file``'s ```` ```toml ```` block into a dict -- the body
    every record module's module-scoped ``meta`` fixture shared verbatim."""
    assert record_file.exists(), f"{record_label} record missing: {record_file}"
    return tomllib.loads(
        extract_toml_block(record_file.read_text(encoding="utf-8"), record_label=record_label)
    )


def assert_not_stale(
    checked: datetime.date,
    *,
    max_age_days: int,
    record_label: str,
    today: datetime.date | None = None,
) -> None:
    """Fail if ``checked`` is more than ``max_age_days`` before ``today``, or
    is itself in the future -- a year-plus-stale release-validation record
    should surface, and a future ``checked`` (negative age) must not sneak
    past the age bound. ``today`` defaults to the UTC calendar date, matching
    this codebase's UTC discipline."""
    today = today or datetime.datetime.now(datetime.UTC).date()
    age = (today - checked).days
    assert checked <= today, (
        f"{record_label} record `checked` = {checked.isoformat()} is in the future "
        f"(today is {today.isoformat()}) -- a measurement/verification cannot have "
        "happened yet"
    )
    assert age <= max_age_days, (
        f"{record_label} record `checked` = {checked.isoformat()} is {age} days old "
        f"(> {max_age_days}) -- re-run the measurement/verification and update the record"
    )


def assert_record_not_stale(
    meta: dict[str, object], *, max_age_days: int, record_label: str
) -> None:
    """The two-line guard every record module's ``test_record_is_not_stale``
    shares: ``meta["checked"]`` parses to a ``datetime.date``, and it is
    within ``max_age_days`` of today (:func:`assert_not_stale`)."""
    checked = meta["checked"]
    assert isinstance(checked, datetime.date), (
        f"{record_label} record `checked` must be a bare ISO date "
        f"(parses to datetime.date), got {checked!r}"
    )
    assert_not_stale(checked, max_age_days=max_age_days, record_label=record_label)
