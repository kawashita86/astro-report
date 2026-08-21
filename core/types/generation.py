"""``GeneratedDraft``: the ``Generator`` port's (Story 4.5, AD-3) return
shape -- each of the eight Report Sections as an ordered list of cited
sentences, never free prose (AD-6).

Living in ``core/types/`` mirrors ``core/types/payload.py``/
``core/types/memory.py``: pure data, with no logic beyond the dataclass
machinery itself. ``GeneratedDraft`` is produced by
``shell/adapters/gemini/generator.py::GeminiGenerator.generate()``, never by
``core/`` itself -- a model call is not pure (AD-1).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["GeneratedDraft", "Sentence"]


@dataclass(frozen=True)
class Sentence:
    """One sentence of generated prose, carrying the ``Payload`` entry ids
    it rests on (AD-6). ``entry_ids`` may be empty only where a Section's own
    content permits a closed-vocabulary sentence with nothing to cite --
    citation completeness itself is the Groundedness Gate's job (Epic 5),
    not this dataclass's."""

    text: str
    entry_ids: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedDraft:
    """The eight Report Sections, in AD-6's fixed order -- structural, not a
    runtime check, unlike a string-keyed dict a caller could iterate in any
    order or silently misspell a key of.

    Each field is a ``tuple[Sentence, ...]`` in the order the model produced
    them; ``giorni_favorevoli``/``giorni_di_attenzione`` are validated by
    ``GeminiGenerator`` to contain no date-shaped token in any ``Sentence``
    -- dates in those two Sections are code-projected upstream (Story 3.7).
    """

    energia_generale: tuple[Sentence, ...]
    amore: tuple[Sentence, ...]
    lavoro: tuple[Sentence, ...]
    denaro: tuple[Sentence, ...]
    benessere: tuple[Sentence, ...]
    giorni_favorevoli: tuple[Sentence, ...]
    giorni_di_attenzione: tuple[Sentence, ...]
    consiglio_finale: tuple[Sentence, ...]
