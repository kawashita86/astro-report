"""``SectionsConfig``: the frozen, in-memory shape of ``data/sections.toml``
(Story 3.6, AD-13) -- the declarative Section-to-Payload mapping every
Section's ``SectionPayload`` is assembled from.

These types are pure data: no I/O, no defaults invented beyond what
``shell/sections.py`` already resolved at load time, no logic beyond the
dataclass machinery itself. Living in ``core/types/`` rather than ``shell/``
mirrors ``core/types/computation.py``: a future ``core/`` function
(``core/payload/assemble.py::assemble_payload()``) type-hints on
``SectionSpec``/``SectionsConfig`` without importing anything from
``shell/`` (AD-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

__all__ = ["SectionSpec", "SectionsConfig"]


@dataclass(frozen=True)
class SectionSpec:
    """One Section's declarative filter over the month's computed facts.

    ``domain_profile`` names the ``DomainProfiles`` attribute (``amore``,
    ``lavoro``, ``denaro`` or ``benessere``) this Section's ``SectionPayload``
    carries, or ``None`` for a Section with no single Domain Profile
    (``energia_generale``, ``consiglio_finale``) -- ``shell/sections.py``
    cross-checks that a domain Section's own value always equals its own
    Section name, and that the other two never set one at all.
    ``house_bodies``/``aspect_bodies`` select ``ComputationConfig.bodies.fast``,
    ``.slow``, or -- when ``None`` -- the union of both,
    ``config.bodies.fast | config.bodies.slow``, not some third "any body
    whatsoever" set. In practice this union is not a behavioral gap: every
    upstream scan function (``find_transit_aspects``/``find_ingresses``)
    already restricts itself to exactly that same union when producing the
    events this filter ever sees, so ``None`` and an explicit "fast or slow"
    selector would only ever differ for a body no event can carry anyway.
    ``include_all_events`` short-circuits every other field to "match all"
    for that Section: it is the only source of a match for
    ``consiglio_finale``, whose Acceptance Criterion names no houses or
    natal points.
    """

    domain_profile: str | None
    houses: tuple[int, ...]
    house_bodies: str | None
    aspect_natal_points: tuple[str, ...]
    aspect_bodies: str | None
    retrogrades: bool
    include_all_events: bool


@dataclass(frozen=True)
class SectionsConfig:
    """The full, validated contents of ``data/sections.toml``: exactly the
    six Sections ``core/payload/assemble.py`` maps a ``Payload`` field to."""

    version: int
    content_hash: str
    sections: MappingProxyType[str, SectionSpec]
