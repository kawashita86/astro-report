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
    """ "The month asks patience of you" following a Saturn passage asserts
    no verifiable Claim, even though it depends on one (PRD Open Question
    1). This is the documented, intentional gap -- not a bug -- ``is_claim``
    has no way to see the Saturn passage this sentence leans on, and AD-8
    forbids building a heuristic to close that gap."""
    assert is_claim("Il mese ti chiede di rallentare, senza fretta.", VOCABULARY) is False


# --- Case-insensitivity ----------------------------------------------------------


def test_classification_is_case_insensitive() -> None:
    assert is_claim("MARTE è nella tua decima CASA.", VOCABULARY) is True


# --- epic-5-retro-item-40: measured false positives of the day-of-month and
#     casa+ordinal triggers on ordinary, non-astrological Italian --------------


def test_a_bare_1_to_31_number_used_as_a_duration_is_not_a_claim() -> None:
    """epic-5-retro-item-40 had locked this as an accepted false positive; Story 10.7
    reverses it: a number followed by a unit of time or measure ("3 giorni", "29 anni")
    is a count, not a day of the month, and failing the Gate on it cost whole
    regenerations. A bare numeral with no such unit is still a day-of-month Claim."""
    assert is_claim("Per i prossimi 3 giorni rallenta.", VOCABULARY) is False
    assert is_claim("Succede ogni 29 anni.", VOCABULARY) is False
    assert is_claim("Il 3 rallenta.", VOCABULARY) is True


def test_mundane_casa_plus_ordinal_is_a_false_positive_claim() -> None:
    """epic-5-retro-item-40: "casa" is ordinary Italian for "home"; paired
    with an ordinal in a mundane, non-astrological sentence ("la mia seconda
    casa al mare") it still trips the house-Claim trigger by lexical
    co-occurrence alone. Same accepted design cost as the day-of-month case
    above -- characterized here, not fixed."""
    assert is_claim("Ho preso la mia seconda casa al mare.", VOCABULARY) is True


# --- Story 10.7: the ordinal must sit next to "casa" ----------------------------------


def test_an_ordinal_in_a_time_phrase_next_to_a_house_word_is_not_a_claim() -> None:
    sentence = (
        "Dalla terza settimana la casa si riempie di prima luce, nella seconda metà del mese."
    )
    assert is_claim(sentence, VOCABULARY) is False


def test_the_guard_detects_an_ordinal_written_after_or_in_a_list_before_casa() -> None:
    assert is_claim("La casa quinta si accende.", VOCABULARY) is True
    assert is_claim("La quinta e la settima casa si accendono.", VOCABULARY) is True
