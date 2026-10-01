"""What the drafting view shows for each of the eight Sections, decided purely (Story 10.6).

The run view's Section rail is a reading of the latest draft attempt's rows, not a
second source of truth: this module turns frozen ``SectionRowState`` values and an
explicit ``now`` into one labelled state per Section, so the wording Francesco sees
("In scrittura" versus "Da rifare") can be tested without a database, a clock or a
request. It also owns the small contract between the poll and the browser -- the
``seen`` string the page reports back and the diff that lets a poll answer with only
the rail rows and Sections that changed -- so the server stays stateless (AD-20).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from core.draft_state import (
    CLOSING_ORDINAL,
    SECTION_NAMES,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PENDING,
    SectionRowState,
    is_lease_live,
)
from shell.http.draft_view import SECTION_TITLES

__all__ = [
    "STATE_COMPLETE",
    "STATE_FAILED",
    "STATE_PENDING",
    "STATE_REDO",
    "STATE_WAITING_OTHERS",
    "STATE_WRITING",
    "RailRow",
    "build_rail",
    "changed_ordinals",
    "format_seen",
    "parse_seen",
    "rail_summary",
]

STATE_PENDING = "pending"
STATE_WRITING = "writing"
STATE_COMPLETE = "complete"
STATE_REDO = "redo"
STATE_FAILED = "failed"
STATE_WAITING_OTHERS = "waiting_others"

_LABELS: dict[str, str] = {
    STATE_PENDING: "In attesa",
    STATE_WRITING: "In scrittura",
    STATE_COMPLETE: "Scritta",
    STATE_REDO: "Da rifare",
    STATE_FAILED: "Non riuscita",
    STATE_WAITING_OTHERS: "In attesa delle altre Sezioni",
}


@dataclass(frozen=True)
class RailRow:
    """One Section's place in the rail."""

    ordinal: int
    name: str
    title: str
    state: str
    label: str


def _state_of(
    row: SectionRowState | None,
    *,
    ordinal: int,
    others_complete: bool,
    prior_draft_exists: bool,
    now: datetime,
) -> str:
    if row is None:
        return STATE_PENDING
    if row.status == STATUS_COMPLETE:
        return STATE_COMPLETE
    if row.status == STATUS_FAILED:
        return STATE_FAILED
    if row.status != STATUS_PENDING:
        return STATE_PENDING
    if is_lease_live(row, now):
        return STATE_WRITING
    if ordinal == CLOSING_ORDINAL and row.attempts == 0 and not others_complete:
        return STATE_WAITING_OTHERS
    if row.attempts > 0:
        return STATE_WRITING
    if prior_draft_exists:
        return STATE_REDO
    return STATE_PENDING


def build_rail(
    rows: Sequence[SectionRowState], *, prior_draft_exists: bool, now: datetime
) -> tuple[RailRow, ...]:
    """The eight rail rows in Section order; a Section with no row reads as pending."""
    by_ordinal = {row.ordinal: row for row in rows}
    others_complete = all(
        (by_ordinal.get(ordinal) is not None and by_ordinal[ordinal].status == STATUS_COMPLETE)
        for ordinal in range(1, CLOSING_ORDINAL)
    )
    rail: list[RailRow] = []
    for ordinal, name in enumerate(SECTION_NAMES, start=1):
        state = _state_of(
            by_ordinal.get(ordinal),
            ordinal=ordinal,
            others_complete=others_complete,
            prior_draft_exists=prior_draft_exists,
            now=now,
        )
        rail.append(
            RailRow(
                ordinal=ordinal,
                name=name,
                title=SECTION_TITLES[name],
                state=state,
                label=_LABELS[state],
            )
        )
    return tuple(rail)


def rail_summary(rail: Iterable[RailRow]) -> str:
    """The one live-region line: how many Sections are written."""
    rows = tuple(rail)
    written = sum(1 for row in rows if row.state == STATE_COMPLETE)
    return f"{written} di {len(SECTION_NAMES)} Sezioni scritte"


def format_seen(rail: Iterable[RailRow]) -> str:
    """The ``seen`` query value describing ``rail`` (what the browser reports back)."""
    return ",".join(f"{row.ordinal}:{row.state}" for row in rail)


def parse_seen(raw: str | None) -> dict[int, str]:
    """``"1:complete,2:writing"`` -> ``{1: "complete", 2: "writing"}``; bad entries dropped."""
    seen: dict[int, str] = {}
    for part in (raw or "").split(","):
        ordinal_text, separator, state = part.strip().partition(":")
        if separator and ordinal_text.isdigit() and state:
            seen[int(ordinal_text)] = state
    return seen


def changed_ordinals(rail: Iterable[RailRow], seen: Mapping[int, str]) -> tuple[int, ...]:
    """Ordinals whose state differs from what the browser reports having on screen."""
    return tuple(row.ordinal for row in rail if seen.get(row.ordinal) != row.state)
