"""``core/gate/run.py::run_gate()`` -- one test per row of Story 5.2's I/O &
Edge-Case Matrix, plus the properties those rows imply: purity/determinism
and the check-order the Boundaries fix.

Payload fixtures go through the real ``freeze_payload()`` (Code Map's
explicit precedent) rather than a hand-rolled stand-in shape, mirroring
``tests/test_payload_freeze.py``/``tests/test_gemini_generator.py``'s own
``test_citation_validation_finds_ids_in_a_real_freeze_payload_shaped_payload``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from core.ephemeris.identity import verify_ephemeris_identity
from core.gate.run import _DATE_TOKEN_PATTERN as _GATE_DATE_TOKEN_PATTERN
from core.gate.run import _index_entries, run_gate
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.gate import GateResult, GateViolation
from core.types.generation import GeneratedDraft, Sentence
from core.types.payload import Payload, SectionPayload
from core.types.transits import (
    Ingress,
    Lunation,
    StandingRetrograde,
    Station,
    TransitAspectEvent,
)
from shell.adapters.generation.validation import (
    _DATE_TOKEN_PATTERN as _GENERATOR_DATE_TOKEN_PATTERN,
)
from shell.computation import load_computation_config
from shell.gate import DEFAULT_VOCABULARY_PATH, load_gate_vocabulary
from shell.sections import load_sections_config

_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()
_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_VOCABULARY = load_gate_vocabulary(DEFAULT_VOCABULARY_PATH)

_SECTION_NAMES: tuple[str, ...] = (
    "energia_generale",
    "amore",
    "lavoro",
    "denaro",
    "benessere",
    "giorni_favorevoli",
    "giorni_di_attenzione",
    "consiglio_finale",
)


def _empty_section() -> SectionPayload:
    return SectionPayload(
        profile=None, aspects=(), stations=(), standing_retrogrades=(), ingresses=(), lunations=()
    )


def _freeze(
    *,
    aspects: tuple[TransitAspectEvent, ...] = (),
    stations: tuple[Station, ...] = (),
    ingresses: tuple[Ingress, ...] = (),
    lunations: tuple[Lunation, ...] = (),
) -> dict[str, Any]:
    """One populated ``SectionPayload`` (parked under ``energia_generale`` --
    ``run_gate()`` looks entries up by id everywhere in ``payload``, never by
    which Section they sit under) holding whichever event kinds a test
    needs, frozen through the real ``freeze_payload()``."""
    populated = SectionPayload(
        profile=None,
        aspects=aspects,
        stations=stations,
        standing_retrogrades=(),
        ingresses=ingresses,
        lunations=lunations,
    )
    payload = Payload(
        energia_generale=populated,
        amore=_empty_section(),
        lavoro=_empty_section(),
        denaro=_empty_section(),
        benessere=_empty_section(),
        consiglio_finale=_empty_section(),
    )
    return freeze_payload(
        payload,
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
        config=_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


def _find_id(entries: list[dict[str, Any]], **match: Any) -> str:
    for entry in entries:
        if all(entry.get(key) == value for key, value in match.items()):
            entry_id = entry["id"]
            assert isinstance(entry_id, str)
            return entry_id
    raise AssertionError(f"no entry in {entries!r} matches {match!r}")


def _draft(**sentences: tuple[Sentence, ...]) -> GeneratedDraft:
    fields = {name: sentences.get(name, ()) for name in _SECTION_NAMES}
    return GeneratedDraft(**fields)


def _kinds(result: GateResult) -> list[str]:
    return [violation.kind for violation in result.violations]


# --- Matrix row: invented body -------------------------------------------------


def test_a_claimed_planet_not_matching_the_cited_lunations_moon_fact_is_contradicted() -> None:
    """Since the Story 5.2 amendment, a cited Lunation always asserts
    ``"moon"`` -- a real, non-empty fact -- so a Claim naming a different
    planet (Saturn) against it is a mismatch against a known fact
    (``"contradicted_fact"``), not an absence of any fact at all."""
    lunation = Lunation(
        kind="new_moon",
        occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        longitude=Decimal("10.0"),
        natal_house=7,
    )
    frozen = _freeze(lunations=(lunation,))
    lunation_id = _find_id(frozen["sections"]["energia_generale"]["lunations"], kind="lunation")

    draft = _draft(
        energia_generale=(
            Sentence(text="Saturno domina il transito.", entry_ids=(lunation_id,)),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["contradicted_fact"]
    assert result.violations[0].section == "energia_generale"
    assert result.violations[0].entry_ids == (lunation_id,)
    assert result.violations[0].detail == (
        "claims body/sign saturn, but the cited entries assert moon."
    )


def test_a_claimed_planet_whose_cited_id_resolves_to_no_entry_is_invented() -> None:
    """Every real Payload entry kind ``_body_sign_facts`` recognizes now
    asserts some body fact (the Story 5.2 amendment folded ``lunation`` in
    too), so the ``"invented_fact"`` branch for this category is only
    reachable when none of a Claim's cited ids resolve to any indexed
    entry at all -- exercised directly here, since no real entry kind can
    demonstrate it anymore."""
    draft = _draft(
        energia_generale=(
            Sentence(text="Saturno domina il transito.", entry_ids=("does-not-exist",)),
        )
    )

    result = run_gate(draft, _freeze(), _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["invented_fact"]
    assert result.violations[0].section == "energia_generale"
    assert result.violations[0].entry_ids == ("does-not-exist",)


# --- Matrix row: wrong date -----------------------------------------------------


def test_a_claimed_day_not_matching_the_cited_aspects_perfected_at_day_is_contradicted() -> None:
    aspect = TransitAspectEvent(
        transiting_body="venus",
        natal_point="sun",
        aspect="trine",
        perfected_at=datetime(2026, 1, 5, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    frozen = _freeze(aspects=(aspect,))
    aspect_id = _find_id(frozen["sections"]["energia_generale"]["aspects"], kind="aspect")

    draft = _draft(
        amore=(Sentence(text="Il 20 porta una svolta.", entry_ids=(aspect_id,)),)
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["contradicted_fact"]
    assert result.violations[0].section == "amore"


# --- Matrix row: wrong house -----------------------------------------------------


def test_a_claimed_house_not_matching_the_cited_lunations_natal_house_is_contradicted() -> None:
    lunation = Lunation(
        kind="full_moon",
        occurred_at=datetime(2026, 1, 12, tzinfo=UTC),
        longitude=Decimal("100.0"),
        natal_house=7,
    )
    frozen = _freeze(lunations=(lunation,))
    lunation_id = _find_id(frozen["sections"]["energia_generale"]["lunations"], kind="lunation")

    draft = _draft(
        amore=(
            Sentence(
                text="Una svolta importante nella tua quinta casa.", entry_ids=(lunation_id,)
            ),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["contradicted_fact"]


def test_golden_example_wrong_house_from_the_design_notes() -> None:
    """Design Notes' literal example. ``"luna"`` is itself a planet token
    (the Moon), and the cited Lunation asserts exactly that body (Story 5.2
    amendment) -- so this sentence is grounded on body/sign and fails only
    on the house it also names, not on "luna" itself."""
    lunation = Lunation(
        kind="full_moon",
        occurred_at=datetime(2026, 1, 12, tzinfo=UTC),
        longitude=Decimal("100.0"),
        natal_house=7,
    )
    frozen = _freeze(lunations=(lunation,))
    lunation_id = _find_id(frozen["sections"]["energia_generale"]["lunations"], kind="lunation")

    draft = _draft(
        amore=(
            Sentence(
                text="La luna piena illumina la tua quinta casa.", entry_ids=(lunation_id,)
            ),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["contradicted_fact"]
    house_violations = [v for v in result.violations if v.kind == "contradicted_fact"]
    assert len(house_violations) == 1
    assert house_violations[0].section == "amore"
    assert house_violations[0].entry_ids == (lunation_id,)


def test_a_lunation_grounds_a_luna_claim_with_no_other_violation() -> None:
    """Story 5.2 amendment's own positive case: a well-formed "Luna
    Nuova"/"Luna Piena" sentence whose only checkable category is body/sign,
    citing a matching Lunation, now passes -- the false-positive this
    amendment exists to fix."""
    lunation = Lunation(
        kind="new_moon",
        occurred_at=datetime(2026, 1, 10, tzinfo=UTC),
        longitude=Decimal("197.0"),
        natal_house=9,
    )
    frozen = _freeze(lunations=(lunation,))
    lunation_id = _find_id(frozen["sections"]["energia_generale"]["lunations"], kind="lunation")

    draft = _draft(
        consiglio_finale=(
            Sentence(
                text="La Luna Nuova apre un portale di nuove intenzioni.",
                entry_ids=(lunation_id,),
            ),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is True
    assert result.violations == ()


# --- Regression: partial match within one multi-value category (code-review #1) ---


def test_a_second_unmatched_house_in_the_same_sentence_still_fails() -> None:
    """A Claim naming two houses in one sentence, where the cited entry
    grounds only one of them, must still fail on the ungrounded one --
    ``isdisjoint()`` alone would pass this because *some* asserted value
    (5) matches, silently letting the invented 7 through."""
    lunation = Lunation(
        kind="full_moon",
        occurred_at=datetime(2026, 1, 12, tzinfo=UTC),
        longitude=Decimal("100.0"),
        natal_house=5,
    )
    frozen = _freeze(lunations=(lunation,))
    lunation_id = _find_id(frozen["sections"]["energia_generale"]["lunations"], kind="lunation")

    draft = _draft(
        amore=(
            Sentence(
                text="La quinta casa e la settima casa si attivano insieme.",
                entry_ids=(lunation_id,),
            ),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["contradicted_fact"]
    detail = result.violations[0].detail
    assert "7" in detail
    assert detail == "claims house 7, but the cited entries assert 5."


# --- Matrix row: invented body, sign variant --------------------------------------


def test_a_claimed_sign_is_contradicted_by_a_cited_lunations_moon_fact() -> None:
    """No entry kind this story checks ever exposes a sign value (Design
    Notes category table; only body names like ``"mars"`` appear in
    ``transiting_body``/``natal_point``/``body``, and the Story 5.2
    amendment's Lunation->``"moon"`` fact is body-only, never a sign). Since
    the cited Lunation now asserts a real body/sign-category fact
    (``"moon"``), a sign-only Claim it cannot match is ``contradicted_fact``,
    not ``invented_fact`` -- the entry does assert something here, just
    never a sign."""
    lunation = Lunation(
        kind="new_moon",
        occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        longitude=Decimal("10.0"),
        natal_house=7,
    )
    frozen = _freeze(lunations=(lunation,))
    lunation_id = _find_id(frozen["sections"]["energia_generale"]["lunations"], kind="lunation")

    draft = _draft(
        energia_generale=(
            Sentence(text="Il Leone domina il tuo mese.", entry_ids=(lunation_id,)),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["contradicted_fact"]
    assert result.violations[0].detail == "claims body/sign leo, but the cited entries assert moon."


# --- Matrix row: false retrograde -------------------------------------------------


def test_a_claimed_retrograde_contradicted_by_the_cited_stations_direction() -> None:
    station = Station(
        body="mercury",
        direction="direct",
        station_at=datetime(2026, 1, 8, tzinfo=UTC),
        longitude=Decimal("50.0"),
    )
    frozen = _freeze(stations=(station,))
    station_id = _find_id(frozen["sections"]["energia_generale"]["stations"], kind="station")

    draft = _draft(
        lavoro=(
            Sentence(text="Mercurio è retrogrado questa settimana.", entry_ids=(station_id,)),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["contradicted_fact"]
    assert result.violations[0].section == "lavoro"


def test_a_claimed_retrograde_grounded_by_the_cited_stations_direction_has_no_violation() -> None:
    """The "well-grounded Claim" matrix row's own fixture only exercises
    body/house/date via an Ingress citation; this covers the retrograde
    category's grounded path, which nothing else does."""
    station = Station(
        body="saturn",
        direction="retrograde",
        station_at=datetime(2026, 1, 8, tzinfo=UTC),
        longitude=Decimal("50.0"),
    )
    frozen = _freeze(stations=(station,))
    station_id = _find_id(frozen["sections"]["energia_generale"]["stations"], kind="station")

    draft = _draft(
        lavoro=(
            Sentence(text="Saturno è retrogrado questa settimana.", entry_ids=(station_id,)),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is True
    assert result.violations == ()


# --- Matrix row: empty citation ---------------------------------------------------


def test_a_claim_with_no_cited_entries_is_an_empty_citation_violation() -> None:
    draft = _draft(energia_generale=(Sentence(text="Marte porta energia.", entry_ids=()),))

    result = run_gate(draft, _freeze(), _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["empty_citation"]
    assert result.violations[0].entry_ids == ()


# --- Matrix row: date token in day list --------------------------------------------


def test_a_date_token_in_giorni_favorevoli_fails_even_when_correctly_cited() -> None:
    aspect = TransitAspectEvent(
        transiting_body="jupiter",
        natal_point="moon",
        aspect="sextile",
        perfected_at=datetime(2026, 1, 15, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 10, tzinfo=UTC),
        orb_exit_at=None,
    )
    frozen = _freeze(aspects=(aspect,))
    aspect_id = _find_id(frozen["sections"]["energia_generale"]["aspects"], kind="aspect")

    draft = _draft(
        giorni_favorevoli=(
            Sentence(text="Il 15 gennaio porta chiarezza.", entry_ids=(aspect_id,)),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["date_token_in_day_list"]
    assert result.violations[0].section == "giorni_favorevoli"


def test_a_date_token_in_giorni_di_attenzione_fails_too() -> None:
    draft = _draft(
        giorni_di_attenzione=(
            Sentence(text="Il 3 marzo richiede prudenza.", entry_ids=()),
        )
    )

    result = run_gate(draft, _freeze(), _VOCABULARY)

    kinds = _kinds(result)
    assert "date_token_in_day_list" in kinds


def test_an_uncited_date_token_sentence_fails_both_empty_citation_and_date_token() -> None:
    """The date-token check is unconditional (AD-5), independent of citation
    status -- a Section 6/7 sentence that is *both* an uncited Claim (day-
    of-month numeral, no citation) *and* contains a date-shaped token fails
    both checks, not just one."""
    draft = _draft(
        giorni_favorevoli=(
            Sentence(text="Il 15 gennaio porta chiarezza.", entry_ids=()),
        )
    )

    result = run_gate(draft, _freeze(), _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["empty_citation", "date_token_in_day_list"]
    assert all(violation.entry_ids == () for violation in result.violations)


@pytest.mark.parametrize(
    "sentence_text",
    [
        "Occasione il 15.01 di prima mattina.",
        "Occasione il 15.01.2026 di prima mattina.",
        "Occasione il 15 gen di prima mattina.",
        "Occasione il 15 gen. di prima mattina.",
        "Occasione il 1° feb di prima mattina.",
    ],
)
def test_abbreviated_and_dotted_date_tokens_fail_in_a_day_list(sentence_text: str) -> None:
    draft = _draft(giorni_favorevoli=(Sentence(text=sentence_text, entry_ids=()),))

    result = run_gate(draft, _freeze(), _VOCABULARY)

    assert "date_token_in_day_list" in _kinds(result)


@pytest.mark.parametrize(
    "sentence_text",
    [
        "Ci sono 3 mare da attraversare.",
        "Analizziamo 3 set di dati distinti.",
        "Buon momento soprattutto verso le 15.30.",
        "Buon momento alle 9.45 del mattino.",
        "Le probabilità aumentano di 1.5 volte.",
    ],
)
def test_a_non_date_lookalike_is_not_a_date_token_in_a_day_list(sentence_text: str) -> None:
    draft = _draft(giorni_favorevoli=(Sentence(text=sentence_text, entry_ids=()),))

    result = run_gate(draft, _freeze(), _VOCABULARY)

    assert "date_token_in_day_list" not in _kinds(result)


@pytest.mark.parametrize("malformed", ["not-a-date", ""])
def test_a_cited_entry_with_a_malformed_date_field_contributes_no_day_fact(
    malformed: str,
) -> None:
    """Item 42: a malformed ISO date on a cited Payload entry is skipped by
    ``_date_facts`` rather than raising out of ``run_gate``."""
    aspect = TransitAspectEvent(
        transiting_body="jupiter",
        natal_point="moon",
        aspect="sextile",
        perfected_at=datetime(2026, 1, 15, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 10, tzinfo=UTC),
        orb_exit_at=None,
    )
    frozen = _freeze(aspects=(aspect,))
    frozen_aspects = frozen["sections"]["energia_generale"]["aspects"]
    aspect_id = _find_id(frozen_aspects, kind="aspect")
    for entry in frozen_aspects:
        if entry["id"] == aspect_id:
            entry["perfected_at"] = malformed

    draft = _draft(
        amore=(Sentence(text="Il 15 porta una svolta.", entry_ids=(aspect_id,)),),
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert isinstance(result, GateResult)
    # The day-15 claim cannot be grounded once the date field is unparseable.
    assert _kinds(result) == ["invented_fact"]


def test_a_malformed_cited_entry_does_not_suppress_a_well_formed_ones_day_fact() -> None:
    """Item 42: when a sentence cites one entry with a malformed date field
    and one with a valid one, ``_date_facts`` skips only the malformed entry
    -- the valid entry's day still grounds a claim for that day."""
    valid = TransitAspectEvent(
        transiting_body="jupiter",
        natal_point="moon",
        aspect="sextile",
        perfected_at=datetime(2026, 1, 15, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 10, tzinfo=UTC),
        orb_exit_at=None,
    )
    broken = TransitAspectEvent(
        transiting_body="saturn",
        natal_point="sun",
        aspect="square",
        perfected_at=datetime(2026, 1, 20, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 10, tzinfo=UTC),
        orb_exit_at=None,
    )
    frozen = _freeze(aspects=(valid, broken))
    frozen_aspects = frozen["sections"]["energia_generale"]["aspects"]
    valid_id = _find_id(frozen_aspects, transiting_body="jupiter")
    broken_id = _find_id(frozen_aspects, transiting_body="saturn")
    for entry in frozen_aspects:
        if entry["id"] == broken_id:
            entry["perfected_at"] = "not-a-date"

    draft = _draft(
        amore=(
            Sentence(text="Il 15 porta una svolta.", entry_ids=(broken_id, valid_id)),
        ),
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert isinstance(result, GateResult)
    assert result.passed is True
    assert _kinds(result) == []


# --- Matrix row: well-grounded Claim -----------------------------------------------


def test_a_claim_grounded_in_every_checkable_category_produces_no_violation() -> None:
    ingress = Ingress(
        body="mars",
        house_departed=4,
        house_entered=5,
        crossed_at=datetime(2026, 1, 10, tzinfo=UTC),
    )
    frozen = _freeze(ingresses=(ingress,))
    ingress_id = _find_id(frozen["sections"]["energia_generale"]["ingresses"], kind="ingress")

    draft = _draft(
        amore=(
            Sentence(
                text="Marte entra nella tua quinta casa il 10.", entry_ids=(ingress_id,)
            ),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is True
    assert result.violations == ()


# --- Matrix row: non-Claim sentence -------------------------------------------------


def test_a_non_claim_sentence_with_no_citation_is_never_policed() -> None:
    draft = _draft(amore=(Sentence(text="Il mese chiede pazienza.", entry_ids=()),))

    result = run_gate(draft, _freeze(), _VOCABULARY)

    assert result.passed is True
    assert result.violations == ()


# --- Matrix row: deliberately corrupted draft ---------------------------------------


def test_a_draft_with_all_four_violation_classes_injected_fails_once_per_class() -> None:
    wrong_date_aspect = TransitAspectEvent(
        transiting_body="venus",
        natal_point="sun",
        aspect="trine",
        perfected_at=datetime(2026, 1, 5, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    correctly_dated_aspect = TransitAspectEvent(
        transiting_body="jupiter",
        natal_point="moon",
        aspect="sextile",
        perfected_at=datetime(2026, 1, 15, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 10, tzinfo=UTC),
        orb_exit_at=None,
    )
    frozen = _freeze(aspects=(wrong_date_aspect, correctly_dated_aspect))
    frozen_aspects = frozen["sections"]["energia_generale"]["aspects"]
    wrong_date_id = _find_id(frozen_aspects, transiting_body="venus")
    correctly_dated_id = _find_id(frozen_aspects, transiting_body="jupiter")

    draft = _draft(
        energia_generale=(
            # No real Payload entry kind is body/sign-silent anymore (Story
            # 5.2 amendment folded "lunation" into the category too) -- an
            # unresolvable id is the only way left to exercise the
            # "invented_fact" branch.
            Sentence(text="Saturno domina il transito.", entry_ids=("does-not-exist",)),
        ),
        amore=(Sentence(text="Il 20 porta una svolta.", entry_ids=(wrong_date_id,)),),
        lavoro=(Sentence(text="Venere illumina il tuo lavoro.", entry_ids=()),),
        giorni_favorevoli=(
            Sentence(text="Il 15 gennaio porta chiarezza.", entry_ids=(correctly_dated_id,)),
        ),
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert sorted(_kinds(result)) == sorted(
        ["invented_fact", "contradicted_fact", "empty_citation", "date_token_in_day_list"]
    )
    assert len(result.violations) == 4


# --- Matrix row: same inputs, run twice ---------------------------------------------


def test_running_the_gate_twice_on_identical_inputs_is_byte_for_byte_identical() -> None:
    ingress = Ingress(
        body="mars",
        house_departed=4,
        house_entered=5,
        crossed_at=datetime(2026, 1, 10, tzinfo=UTC),
    )
    frozen = _freeze(ingresses=(ingress,))
    ingress_id = _find_id(frozen["sections"]["energia_generale"]["ingresses"], kind="ingress")
    draft = _draft(
        amore=(
            Sentence(text="Marte entra nella tua quinta casa il 10.", entry_ids=(ingress_id,)),
        ),
        lavoro=(Sentence(text="Venere illumina il tuo lavoro.", entry_ids=()),),
    )

    first = run_gate(draft, frozen, _VOCABULARY)
    second = run_gate(draft, frozen, _VOCABULARY)

    assert first == second
    assert first.violations == second.violations


# --- GateResult shape ------------------------------------------------------------


def test_gate_result_passed_is_true_iff_violations_is_empty() -> None:
    passing = run_gate(_draft(), _freeze(), _VOCABULARY)
    assert passing.passed is True
    assert passing.violations == ()

    failing = run_gate(
        _draft(energia_generale=(Sentence(text="Marte porta energia.", entry_ids=()),)),
        _freeze(),
        _VOCABULARY,
    )
    assert failing.passed is False
    assert failing.violations != ()


def test_gate_result_carries_the_vocabulary_version_through() -> None:
    result = run_gate(_draft(), _freeze(), _VOCABULARY)

    assert result.vocabulary_version == _VOCABULARY.version


def test_gate_result_carries_the_vocabulary_content_hash_through() -> None:
    """``run_gate()`` copies ``GateVocabulary.content_hash`` onto the result
    verbatim, exactly as it already does for ``version`` -- so a later
    persistence write-site can record the digest the Gate checked against
    (epic-5-retro item 45)."""
    result = run_gate(_draft(), _freeze(), _VOCABULARY)

    assert result.vocabulary_content_hash == _VOCABULARY.content_hash


def test_violations_are_gate_violation_instances() -> None:
    result = run_gate(
        _draft(energia_generale=(Sentence(text="Marte porta energia.", entry_ids=()),)),
        _freeze(),
        _VOCABULARY,
    )

    assert all(isinstance(violation, GateViolation) for violation in result.violations)


# --- Check order within one sentence: body/sign, house, date, retrograde ----------


def test_a_sentence_failing_all_four_categories_reports_them_in_the_fixed_order() -> None:
    """``run_gate()``'s own docstring claims a fixed per-sentence check order
    (body/sign, house, date, retrograde); nothing else exercises more than
    one failing category in a single sentence."""
    lunation = Lunation(
        kind="full_moon",
        occurred_at=datetime(2026, 1, 10, tzinfo=UTC),
        longitude=Decimal("100.0"),
        natal_house=3,
    )
    frozen = _freeze(lunations=(lunation,))
    lunation_id = _find_id(frozen["sections"]["energia_generale"]["lunations"], kind="lunation")

    draft = _draft(
        amore=(
            Sentence(
                text="Marte è retrogrado nella tua settima casa il 25.",
                entry_ids=(lunation_id,),
            ),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == [
        "contradicted_fact",  # body/sign: Lunation asserts "moon", claimed "marte"
        "contradicted_fact",  # house: cited natal_house=3, claimed 7
        "contradicted_fact",  # date: cited day=10, claimed 25
        "invented_fact",  # retrograde: Lunation exposes neither
    ]
    assert all(violation.section == "amore" for violation in result.violations)
    assert all(violation.entry_ids == (lunation_id,) for violation in result.violations)


# --- _index_entries(): an id recurring under two Sections' slices (code-review #7) --


def test_index_entries_finds_an_id_that_recurs_under_two_sections() -> None:
    """The same content-derived id can legitimately appear under more than
    one Section's own slice (``core/payload/freeze.py``'s own docstring);
    ``_index_entries()`` must resolve it regardless of where it was found."""
    aspect = TransitAspectEvent(
        transiting_body="mars",
        natal_point="venus",
        aspect="trine",
        perfected_at=datetime(2026, 1, 5, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    populated = SectionPayload(
        profile=None, aspects=(aspect,), stations=(), standing_retrogrades=(), ingresses=(),
        lunations=(),
    )
    payload = Payload(
        energia_generale=populated,
        amore=populated,
        lavoro=_empty_section(),
        denaro=_empty_section(),
        benessere=_empty_section(),
        consiglio_finale=_empty_section(),
    )
    frozen = freeze_payload(
        payload,
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
        config=_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    energia_id = frozen["sections"]["energia_generale"]["aspects"][0]["id"]
    amore_id = frozen["sections"]["amore"]["aspects"][0]["id"]
    assert energia_id == amore_id  # same content -> same content-derived id (AD-4)

    index = _index_entries(frozen)

    assert index[energia_id]["kind"] == "aspect"
    assert index[energia_id]["transiting_body"] == "mars"


# --- Local date-token pattern stays in lockstep with the generator's own copy -----


def test_gate_date_token_pattern_matches_the_generators_hand_duplicated_copy() -> None:
    """AD-1 forbids ``core/`` importing ``shell/``, so
    ``shell/adapters/generation/validation.py``'s ``_DATE_TOKEN_PATTERN`` is
    hand-duplicated in ``core/gate/run.py`` rather than imported; this catches
    silent drift between the two copies (code-review finding #9)."""
    assert _GATE_DATE_TOKEN_PATTERN.pattern == _GENERATOR_DATE_TOKEN_PATTERN.pattern
    assert _GATE_DATE_TOKEN_PATTERN.flags == _GENERATOR_DATE_TOKEN_PATTERN.flags


# --- epic-5-retro-item-40: an accepted classify false positive reaching run_gate --


def test_a_mundane_casa_ordinal_sentence_citing_a_house_free_entry_is_an_invented_fact() -> (
    None
):
    """epic-5-retro-item-40 / epic-5-retro Finding 3: a mundane "seconda
    casa" sentence ("la mia seconda casa al mare") is classified as a house
    Claim (``casa`` + an ordinal co-occur) and, citing an Aspect -- a kind
    that exposes no house fact -- ``run_gate()`` returns an ``invented_fact``
    violation. The practical cost is an unnecessary regeneration / bound
    failure (Story 5.4) for prose that made no astronomical claim. This
    characterizes the accepted false-positive cost; AD-8 forbids fixing it
    with a narrower heuristic."""
    aspect = TransitAspectEvent(
        transiting_body="venus",
        natal_point="sun",
        aspect="trine",
        perfected_at=datetime(2026, 1, 5, tzinfo=UTC),
        never_perfected=False,
        orb_entry_at=datetime(2026, 1, 1, tzinfo=UTC),
        orb_exit_at=None,
    )
    frozen = _freeze(aspects=(aspect,))
    aspect_id = _find_id(frozen["sections"]["energia_generale"]["aspects"], kind="aspect")

    draft = _draft(
        amore=(Sentence(text="Ho preso la mia seconda casa al mare.", entry_ids=(aspect_id,)),)
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["invented_fact"]


def test_a_bare_duration_number_citing_a_date_free_entry_is_an_invented_fact() -> None:
    """epic-5-retro-item-40: "per i prossimi 3 giorni" is classified as a
    day-of-month Claim (the trigger fires on any bare 1-31). Citing a
    ``StandingRetrograde`` -- a kind that exposes no date fact -- ``run_gate()``
    returns an ``invented_fact`` violation for a sentence that asserts no
    date at all. Characterizes the accepted false-positive cost (AD-8), does
    not fix it."""
    retrograde = StandingRetrograde(
        body="mercury",
        retrograde_start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        retrograde_end_utc=datetime(2026, 1, 31, tzinfo=UTC),
    )
    populated = SectionPayload(
        profile=None,
        aspects=(),
        stations=(),
        standing_retrogrades=(retrograde,),
        ingresses=(),
        lunations=(),
    )
    payload = Payload(
        energia_generale=populated,
        amore=_empty_section(),
        lavoro=_empty_section(),
        denaro=_empty_section(),
        benessere=_empty_section(),
        consiglio_finale=_empty_section(),
    )
    frozen = freeze_payload(
        payload,
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
        config=_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    retrograde_id = _find_id(
        frozen["sections"]["energia_generale"]["standing_retrogrades"],
        kind="standing_retrograde",
    )

    draft = _draft(
        amore=(
            Sentence(text="Per i prossimi 3 giorni rallenta.", entry_ids=(retrograde_id,)),
        )
    )

    result = run_gate(draft, frozen, _VOCABULARY)

    assert result.passed is False
    assert _kinds(result) == ["invented_fact"]
