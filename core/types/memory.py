"""``ReportTheme``: a pure, deterministic summary of one month's ``Payload``
(Story 4.3, AD-14) -- what Story 4.4's continuity diffing and the Generator
port (AD-3) both need to know about "what this month already contained"
without a model ever judging it, and without prior Report prose ever
traveling anywhere.

Living in ``core/types/`` rather than ``core/memory/`` mirrors
``core/types/payload.py``: these are pure data, produced by
``core/memory/derive.py::derive_theme()`` from an already-assembled
``Payload``, with no logic beyond the dataclass machinery itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.types.transits import StandingRetrograde

__all__ = [
    "AspectChange",
    "ReportTheme",
    "RetrogradeChange",
    "ThemeAspect",
    "ThemeDiff",
    "ThemeLunation",
]


@dataclass(frozen=True)
class ThemeAspect:
    """One dominant slow-planet Aspect (Story 4.3): a
    :class:`core.types.transits.TransitAspectEvent` whose ``transiting_body``
    is one of ``ComputationConfig.bodies.slow``, carried through field-for-
    field unchanged.

    No event anywhere in this codebase carries a numeric orb-degree, so
    ``perfected_at``/``orb_exit_at`` (together with ``never_perfected``) are
    the only signals available for ordering "dominant" Aspects by tightness
    (this story's Ask First) and for Story 4.4's diffing to tell
    still-active, tightened, resolved and new apart.
    """

    transiting_body: str
    natal_point: str
    aspect: str
    perfected_at: datetime | None
    never_perfected: bool
    orb_entry_at: datetime
    orb_exit_at: datetime | None


@dataclass(frozen=True)
class ThemeLunation:
    """The natal house one of the month's Lunations fell in (Story 4.3):
    ``kind`` (``"new_moon"``/``"full_moon"``) plus ``natal_house``.

    ``occurred_at``/``longitude`` (:class:`core.types.transits.Lunation`'s
    other two fields) are deliberately not carried forward -- continuity
    across months is about which house a Lunation activated, not the exact
    instant or degree within the month it fell.
    """

    kind: str
    natal_house: int


@dataclass(frozen=True)
class ReportTheme:
    """One month's ``Payload`` reduced to what Story 4.4's diffing and the
    Generator port (AD-3) both need: dominant slow-planet Aspects ordered by
    tightness, this month's Lunation houses, and standing Retrogrades --
    each deduplicated across the six ``SectionPayload``s a slow Aspect,
    Lunation or StandingRetrograde may appear in more than one of.

    Persisted once per ``ReportRun``
    (``shell/adapters/postgres/report_theme.py``), immutable like
    ``ReportPayload`` -- the Generator's continuity input for a Client's next
    month must never change underneath an already-generated Report.
    """

    dominant_aspects: tuple[ThemeAspect, ...]
    lunations: tuple[ThemeLunation, ...]
    standing_retrogrades: tuple[StandingRetrograde, ...]


@dataclass(frozen=True)
class AspectChange:
    """One ``ThemeAspect``'s classification between two consecutive months'
    ``ReportTheme``s (Story 4.4, AD-14): ``"new"``, ``"still_active"``,
    ``"tightened"`` or ``"resolved"``, computed by
    ``core/memory/diff.py::diff_themes()`` rather than judged by a model.
    """

    aspect: ThemeAspect
    status: str


@dataclass(frozen=True)
class RetrogradeChange:
    """One ``StandingRetrograde``'s classification between two consecutive
    months' ``ReportTheme``s (Story 4.4, AD-14): ``"new"``,
    ``"still_active"`` or ``"resolved"`` -- no ``"tightened"`` state, since a
    StandingRetrograde carries no tightness signal to newly-perfect.
    """

    retrograde: StandingRetrograde
    status: str


@dataclass(frozen=True)
class ThemeDiff:
    """What changed between two consecutive months' ``ReportTheme``s (Story
    4.4, AD-14): every ``dominant_aspects``/``standing_retrogrades`` element
    across both, classified into exactly one status, plus a computed
    ``nothing_significant_changed`` flag -- what makes "nothing significant
    has changed" a computed fact rather than a model's guess.

    ``ReportTheme.lunations`` is not diffed -- every current-month Lunation
    is new by construction (it occurs within that specific month, never
    carried over), so classifying it would always yield ``"new"`` with no
    informational value.

    ``aspect_changes``/``retrograde_changes`` are ordered: matched-and-new
    entries in ``current``'s own order, followed by resolved-only entries
    (absent from ``current``) in ``previous``'s own order -- a guaranteed
    part of the contract, not an incidental detail of the implementation.

    Produced by ``core/memory/diff.py::diff_themes()``, pure and model-free
    like ``ReportTheme`` itself.
    """

    aspect_changes: tuple[AspectChange, ...]
    retrograde_changes: tuple[RetrogradeChange, ...]
    nothing_significant_changed: bool
