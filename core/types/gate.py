"""``GateVocabulary``: the frozen, in-memory shape of ``core/gate/vocabulary.it.json``
(Story 5.1, AD-8) -- the versioned closed Italian vocabulary that decides what
counts as a Claim. ``GateViolation``/``GateResult``: the Groundedness Gate's
own verdict shape (Story 5.2) -- ``core/gate/run.py::run_gate()``'s return
value.

Pure data, mirroring ``core/types/sections.py``: no I/O, no defaults invented
beyond what ``shell/gate.py`` already resolved at load time. Living in
``core/types/`` rather than ``core/gate/`` mirrors ``core/types/sections.py``:
``core/gate/classify.py::is_claim()``/``core/gate/run.py::run_gate()``
type-hint on these without importing anything from ``shell/`` (AD-1).

``version`` is independent of the Report Payload schema version and the
Section-composition (``sections.toml``) version -- three separate integers,
each recorded on every Report (see ARCHITECTURE-SPINE.md's schema-versions
row).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["GateResult", "GateVocabulary", "GateViolation"]


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


@dataclass(frozen=True)
class GateViolation:
    """One Groundedness Gate failure (Story 5.2): a single sentence that
    failed one check ``run_gate()`` performs against the Report Payload.

    ``kind`` is one of ``"empty_citation"``, ``"invented_fact"``,
    ``"contradicted_fact"`` or ``"date_token_in_day_list"``. ``section`` is
    the ``GeneratedDraft`` field name the sentence belongs to; ``sentence``
    is that ``Sentence``'s own ``text`` and ``entry_ids`` its own cited
    entry ids -- carried here rather than requiring a caller to re-look the
    sentence up in the draft (Story 5.5 surfaces this directly to Francesco).
    ``detail`` is a human-readable explanation of what was claimed and what
    the cited entries (if any) actually say.
    """

    kind: str
    section: str
    sentence: str
    entry_ids: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class GateResult:
    """The Groundedness Gate's full verdict on one ``GeneratedDraft`` against
    one Report Payload (Story 5.2).

    ``violations`` is empty iff ``passed`` is ``True``, in a fixed,
    deterministic order (Section field order, then sentence index, then
    check order) -- two calls on identical inputs always produce a
    byte-for-byte identical tuple. ``vocabulary_version`` carries
    ``GateVocabulary.version`` through, and ``vocabulary_content_hash``
    carries ``GateVocabulary.content_hash`` through, both unchanged, for
    later persistence on the Report row (Story 5.6).
    """

    passed: bool
    vocabulary_version: int
    vocabulary_content_hash: str
    violations: tuple[GateViolation, ...]
