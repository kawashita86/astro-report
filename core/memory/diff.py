"""Diff two consecutive months' ``ReportTheme``s (Story 4.4, AD-14).

Pure and model-free (AD-1): reads only the passed arguments, no I/O, clock,
network, randomness or Generator call -- identical inputs produce a
byte-identical (``==``) ``ThemeDiff`` every call, which is what makes
"nothing significant has changed" a computed fact rather than a model's
guess.

Matching is by identity, not full equality: two ``ThemeAspect``s are the same
element iff ``(transiting_body, natal_point, aspect)`` match; two
``StandingRetrograde``s iff ``body`` matches. Each side is reduced to a
``dict`` keyed on that identity before classification -- a straightforward
``dict[key] = item`` loop over a tuple in order both dedupes same-identity
repeats (a rare same-month retrograde-loop re-entry, per
``TransitAspectEvent``'s own docs) down to one representative per identity
*and* preserves each identity's first-occurrence position, since reassigning
an existing key updates its value without moving its position in the dict's
iteration order. This is a deliberate, accepted limitation (Never): no
special-casing, raising or pairwise-matching of same-identity duplicates
within a single ``ReportTheme``.

``ThemeLunation`` is excluded from the diff entirely: every current-month
Lunation is new by construction (it occurs within that specific month, never
carried over), so classifying it would always yield ``"new"`` with no
informational value (Ask First).
"""

from __future__ import annotations

from core.types.memory import (
    AspectChange,
    ReportTheme,
    RetrogradeChange,
    ThemeAspect,
    ThemeDiff,
)
from core.types.transits import StandingRetrograde

__all__ = ["diff_themes"]

_AspectIdentity = tuple[str, str, str]


def _aspect_identity(aspect: ThemeAspect) -> _AspectIdentity:
    return (aspect.transiting_body, aspect.natal_point, aspect.aspect)


def _by_aspect_identity(aspects: tuple[ThemeAspect, ...]) -> dict[_AspectIdentity, ThemeAspect]:
    by_identity: dict[_AspectIdentity, ThemeAspect] = {}
    for aspect in aspects:
        by_identity[_aspect_identity(aspect)] = aspect
    return by_identity


def _by_retrograde_body(
    retrogrades: tuple[StandingRetrograde, ...],
) -> dict[str, StandingRetrograde]:
    by_body: dict[str, StandingRetrograde] = {}
    for retrograde in retrogrades:
        by_body[retrograde.body] = retrograde
    return by_body


def _classify_matched_aspect(previous: ThemeAspect, current: ThemeAspect) -> str:
    """Classification priority (Design Notes): a fresh pass following a full
    prior separation is always ``"new"``, regardless of ``current``'s own
    state; then a current-month separation is ``"resolved"`` (checked ahead
    of tightening, since separating is the more decisive signal); then a
    current-month first perfection is ``"tightened"``; else ``"still_active"``.
    """
    if previous.orb_exit_at is not None:
        return "new"
    if current.orb_exit_at is not None:
        return "resolved"
    if previous.never_perfected and not current.never_perfected:
        return "tightened"
    return "still_active"


def _aspect_changes(
    previous_aspects: tuple[ThemeAspect, ...], current_aspects: tuple[ThemeAspect, ...]
) -> tuple[AspectChange, ...]:
    previous_by_identity = _by_aspect_identity(previous_aspects)
    current_by_identity = _by_aspect_identity(current_aspects)

    changes: list[AspectChange] = []
    for identity, current_aspect in current_by_identity.items():
        previous_aspect = previous_by_identity.get(identity)
        status = (
            "new"
            if previous_aspect is None
            else _classify_matched_aspect(previous_aspect, current_aspect)
        )
        changes.append(AspectChange(aspect=current_aspect, status=status))

    for identity, previous_aspect in previous_by_identity.items():
        if identity not in current_by_identity:
            changes.append(AspectChange(aspect=previous_aspect, status="resolved"))

    return tuple(changes)


def _retrograde_changes(
    previous_retrogrades: tuple[StandingRetrograde, ...],
    current_retrogrades: tuple[StandingRetrograde, ...],
) -> tuple[RetrogradeChange, ...]:
    previous_by_body = _by_retrograde_body(previous_retrogrades)
    current_by_body = _by_retrograde_body(current_retrogrades)

    changes: list[RetrogradeChange] = []
    for body, current_retrograde in current_by_body.items():
        status = "still_active" if body in previous_by_body else "new"
        changes.append(RetrogradeChange(retrograde=current_retrograde, status=status))

    for body, previous_retrograde in previous_by_body.items():
        if body not in current_by_body:
            changes.append(RetrogradeChange(retrograde=previous_retrograde, status="resolved"))

    return tuple(changes)


def diff_themes(previous: ReportTheme | None, current: ReportTheme) -> ThemeDiff | None:
    """Classify every ``dominant_aspects``/``standing_retrogrades`` element
    across ``previous`` and ``current`` into ``"new"``, ``"still_active"``,
    ``"tightened"`` (Aspects only) or ``"resolved"``, and compute
    ``nothing_significant_changed``.

    Returns ``None`` when ``previous`` is ``None`` (a Client's first month):
    no comparison is attempted, since there is nothing to compare against.
    """
    if previous is None:
        return None

    aspect_changes = _aspect_changes(previous.dominant_aspects, current.dominant_aspects)
    retrograde_changes = _retrograde_changes(
        previous.standing_retrogrades, current.standing_retrogrades
    )

    nothing_significant_changed = all(
        change.status == "still_active" for change in aspect_changes
    ) and all(change.status == "still_active" for change in retrograde_changes)

    return ThemeDiff(
        aspect_changes=aspect_changes,
        retrograde_changes=retrograde_changes,
        nothing_significant_changed=nothing_significant_changed,
    )
