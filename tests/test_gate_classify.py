"""``is_claim()`` classification -- one test per row of Story 5.1's I/O
matrix, plus the design-note edge case that ``casa`` and an ordinal must
co-occur in the same sentence to count.
"""

from __future__ import annotations

from core.gate.classify import is_claim
from core.types.gate import GateVocabulary
from shell.gate import DEFAULT_VOCABULARY_PATH, load_gate_vocabulary

VOCABULARY: GateVocabulary = load_gate_vocabulary(DEFAULT_VOCABULARY_PATH)


# --- Matrix row: planet token --------------------------------------------------


def test_a_sentence_naming_a_planet_is_a_claim() -> None:
    assert is_claim("Marte è nella tua decima casa.", VOCABULARY) is True


# --- Matrix row: sign token -----------------------------------------------------


def test_a_sentence_naming_a_sign_is_a_claim() -> None:
    assert is_claim("Il Leone domina il tuo mese.", VOCABULARY) is True


# --- Matrix row: casa + ordinal -------------------------------------------------


def test_casa_paired_with_an_ordinal_is_a_claim() -> None:
    assert is_claim("La quinta casa si attiva.", VOCABULARY) is True


def test_an_ordinal_without_the_literal_word_casa_is_not_a_claim() -> None:
    """Design Notes: an ordinal alone (e.g. "la prima cosa") is not
    astronomical -- ``casa_ordinals`` only counts as a Claim token combined
    with the literal word ``casa`` in the same sentence."""
    assert is_claim("È la prima cosa che noti.", VOCABULARY) is False


def test_the_word_casa_without_an_ordinal_is_not_a_claim() -> None:
    assert is_claim("Torni a casa presto.", VOCABULARY) is False


# --- Matrix row: day-of-month numeral -------------------------------------------


def test_a_day_of_month_numeral_is_a_claim() -> None:
    assert is_claim("Il 15 porta un cambiamento.", VOCABULARY) is True


# --- Matrix row: retrogrado / stazionario ---------------------------------------


def test_retrogrado_is_a_claim() -> None:
    assert is_claim("Mercurio è retrogrado.", VOCABULARY) is True


def test_stazionario_is_a_claim() -> None:
    assert is_claim("Saturno è stazionario questa settimana.", VOCABULARY) is True


# --- Matrix row: zero vocabulary tokens -----------------------------------------


def test_a_sentence_with_no_vocabulary_token_is_not_a_claim() -> None:
    assert is_claim("Il mese chiede pazienza.", VOCABULARY) is False


# --- Matrix row: fact-leaning interpretation stays unpoliced (Open Question 1) --


def test_a_sentence_leaning_on_a_fact_without_naming_it_is_not_a_claim() -> None:
    """"The month asks patience of you" following a Saturn passage asserts
    no verifiable Claim, even though it depends on one (PRD Open Question
    1). This is the documented, intentional gap -- not a bug -- ``is_claim``
    has no way to see the Saturn passage this sentence leans on, and AD-8
    forbids building a heuristic to close that gap."""
    assert is_claim("Il mese ti chiede di rallentare, senza fretta.", VOCABULARY) is False


# --- Case-insensitivity ----------------------------------------------------------


def test_classification_is_case_insensitive() -> None:
    assert is_claim("MARTE è nella tua decima CASA.", VOCABULARY) is True
