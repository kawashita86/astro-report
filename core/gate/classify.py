"""``is_claim()``: whether a sentence is a Claim under the closed Italian
vocabulary (Story 5.1, AD-8).

Pure (AD-1): no I/O, receives an already-loaded ``GateVocabulary``, never a
path. This is the line the Groundedness Gate (Story 5.2) checks Claims
against; nothing here calls a model or a Payload.

**Stated limit (PRD Open Question 1):** a sentence that leans on a fact
without naming it -- e.g. "Il mese chiede pazienza" following a Saturn
passage -- asserts no vocabulary token and is therefore never a Claim, even
though it depends on one. This gap is intentional and stays unpoliced: it is
not verifiable against a Payload by any mechanism, and a heuristic to close
it would reintroduce exactly the judgment-call drift AD-8 exists to prevent.
It remains governed by the Style Guide instead.
"""

from __future__ import annotations

import re

from core.types.gate import GateVocabulary

__all__ = ["is_claim"]


def _contains_token(text: str, token: str) -> bool:
    """Whether ``token`` appears in ``text`` as a whole word, not merely a
    substring of a longer, unrelated word."""
    return re.search(rf"\b{re.escape(token)}\b", text) is not None


def is_claim(sentence: str, vocabulary: GateVocabulary) -> bool:
    """Whether ``sentence`` contains at least one closed-vocabulary token.

    A sentence is a Claim iff it names a planet, a sign, ``casa`` paired with
    an ordinal in the same sentence, a day-of-month numeral, or
    ``retrogrado``/``stazionario`` (AD-8). Zero tokens means interpretation --
    never a Claim, governed by the Style Guide instead.
    """
    lowered = sentence.lower()

    if any(_contains_token(lowered, planet) for planet in vocabulary.planets):
        return True
    if any(_contains_token(lowered, sign) for sign in vocabulary.signs):
        return True
    if _contains_token(lowered, "casa") and any(
        _contains_token(lowered, ordinal) for ordinal in vocabulary.casa_ordinals
    ):
        return True
    if re.search(vocabulary.day_of_month_pattern, lowered) is not None:
        return True
    if _contains_token(lowered, vocabulary.retrogrado):
        return True
    return _contains_token(lowered, vocabulary.stazionario)
