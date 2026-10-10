"""The one place the Italian words the system speaks are gathered.

The operator UI shows aspect and direction names, and the chart data API hands
the same words to the alerenzi plugin so its text says "Quadratura" exactly as
this application does. Keeping the tables here, imported by both, means the two
surfaces cannot drift apart; the Gate words come from ``load_gate_vocabulary``
and the body and sign labels from ``core.gate.run.body_sign_label``, so nothing
is copied a second time.
"""

from __future__ import annotations

from typing import Any

from core.gate.run import body_sign_label
from core.types.gate import GateVocabulary

__all__ = [
    "ASPECT_LABELS_IT",
    "BODY_IDS",
    "DIRECTION_LABELS_IT",
    "SIGN_IDS",
    "vocabulary_body",
]

#: The five Aspect names ``core/ephemeris/chart.py``'s ``_ASPECTS`` table can
#: assign a transit aspect event's ``aspect`` field.
ASPECT_LABELS_IT: dict[str, str] = {
    "conjunction": "Congiunzione",
    "sextile": "Sestile",
    "square": "Quadratura",
    "trine": "Trigono",
    "opposition": "Opposizione",
}

#: The two directions a station's ``direction`` field can carry.
DIRECTION_LABELS_IT: dict[str, str] = {
    "retrograde": "Retrogrado",
    "direct": "Diretto",
}

#: Every body id the API can name: the glossary ids, verbatim.
BODY_IDS: tuple[str, ...] = (
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
    "true_node",
    "south_node",
    "ascendant",
    "midheaven",
)

#: The twelve sign ids, in zodiac order.
SIGN_IDS: tuple[str, ...] = (
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
)


def vocabulary_body(gate: GateVocabulary) -> dict[str, Any]:
    """The ``GET /api/v1/vocabulary/it`` body for a loaded Gate vocabulary."""
    return {
        "vocabulary_version": gate.version,
        "content_hash": gate.content_hash,
        "gate": {
            "planets": sorted(gate.planets),
            "signs": sorted(gate.signs),
            "casa_ordinals": sorted(gate.casa_ordinals),
            "retrogrado": gate.retrogrado,
            "stazionario": gate.stazionario,
        },
        "bodies": {body_id: body_sign_label(body_id) for body_id in BODY_IDS},
        "signs": {sign_id: body_sign_label(sign_id) for sign_id in SIGN_IDS},
        "aspects": dict(ASPECT_LABELS_IT),
        "directions": dict(DIRECTION_LABELS_IT),
    }
