"""``GateVocabulary``: the frozen, in-memory shape of ``core/gate/vocabulary.it.json``
(Story 5.1, AD-8) -- the versioned closed Italian vocabulary that decides what
counts as a Claim.

Pure data, mirroring ``core/types/sections.py``: no I/O, no defaults invented
beyond what ``shell/gate.py`` already resolved at load time. Living in
``core/types/`` rather than ``core/gate/`` mirrors ``core/types/sections.py``:
``core/gate/classify.py::is_claim()`` type-hints on ``GateVocabulary`` without
importing anything from ``shell/`` (AD-1).

``version`` is independent of the Report Payload schema version and the
Section-composition (``sections.toml``) version -- three separate integers,
each recorded on every Report (see ARCHITECTURE-SPINE.md's schema-versions
row).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["GateVocabulary"]


@dataclass(frozen=True)
class GateVocabulary:
    """The full, validated contents of ``vocabulary.it.json``: the six
    closed categories a sentence is checked against to decide whether it is
    a Claim (AD-8).

    ``planets`` and ``signs`` are the ten Italian planet names and twelve
    Italian sign names, each a direct substring match. ``casa_ordinals`` is
    the set of ordinal words (``prima``..``dodicesima``) that only count as
    a Claim token when the literal word ``casa`` also appears in the same
    sentence -- an ordinal alone (e.g. "la prima cosa") is not astronomical.
    ``day_of_month_pattern`` is a regex matching a bare day-of-month numeral.
    ``retrogrado``/``stazionario`` are single literal tokens.
    """

    version: int
    content_hash: str
    planets: frozenset[str]
    signs: frozenset[str]
    casa_ordinals: frozenset[str]
    day_of_month_pattern: str
    retrogrado: str
    stazionario: str
