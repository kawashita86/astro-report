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

__all__ = ["days_of_month_named", "house_ordinals_named", "is_claim"]


def _contains_token(text: str, token: str) -> bool:
    """Whether ``token`` appears in ``text`` as a whole word, not merely a
    substring of a longer, unrelated word."""
    return re.search(rf"\b{re.escape(token)}\b", text) is not None


#: What follows a bare number when it is a count or a measure rather than a day of the
#: month: "ogni 29 anni", "3 volte", "10 gradi", "per 5 giorni", "20%".
_NOT_A_DAY_FOLLOWER = re.compile(
    r"\s*(?:(?:anni|anno|volte|volta|gradi|grado|giorni|giorno|settimane|settimana|mesi|mese|"
    r"ore|ora|minuti|minuto)\b|%|°)"
)


def days_of_month_named(lowered: str, pattern: str) -> frozenset[int]:
    """The days of the month ``lowered`` names: ``pattern``'s matches minus any number
    that is plainly a count or a measure ("ogni 29 anni"). Reading those as days made
    a true sentence about a 29-year Saturn return fail the Gate (Story 10.7)."""
    days: set[int] = set()
    for match in re.finditer(pattern, lowered):
        if _NOT_A_DAY_FOLLOWER.match(lowered, match.end()) is None:
            days.add(int(match.group(1)))
    return frozenset(days)


def house_ordinals_named(
    lowered: str, ordinals: frozenset[str] | tuple[str, ...]
) -> frozenset[str]:
    """The ordinals ``lowered`` actually applies to a house: written right before
    ``casa`` ("la tua Quinta Casa", "la quinta e la settima casa") or right after it
    ("casa quinta"). An ordinal elsewhere in a sentence that mentions a house is a
    different word -- "dalla terza settimana", "la seconda metà del mese", "prima di
    tutto" -- and is not a house claim. Reading those as houses made Amore, which is
    full of houses and of time phrases, fail the Gate on most drafts (Story 10.7).
    """
    if not _contains_token(lowered, "casa"):
        return frozenset()
    options = "|".join(re.escape(ordinal) for ordinal in sorted(ordinals, key=len, reverse=True))
    if not options:
        return frozenset()
    named: set[str] = set()
    before = re.compile(
        rf"\b(?P<first>{options})\b(?:\s*(?:,|\be\b|\bed\b|\bo\b)\s*(?:la\s+|le\s+)?"
        rf"(?P<more>{options})\b)*\s+(?:casa|case)\b"
    )
    for match in before.finditer(lowered):
        named.update(re.findall(rf"\b(?:{options})\b", match.group(0)))
    after = re.compile(rf"\bcasa\s+(?P<ordinal>{options})\b")
    named.update(match.group("ordinal") for match in after.finditer(lowered))
    return frozenset(named)


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
    if house_ordinals_named(lowered, vocabulary.casa_ordinals):
        return True
    if days_of_month_named(lowered, vocabulary.day_of_month_pattern):
        return True
    if _contains_token(lowered, vocabulary.retrogrado):
        return True
    return _contains_token(lowered, vocabulary.stazionario)
