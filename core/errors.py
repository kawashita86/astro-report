"""Typed domain errors: core never returns ``None`` to mean failure."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from core.types.gate import GateViolation

__all__ = [
    "ComputationConfigError",
    "EphemerisIntegrityError",
    "GateFailedError",
    "GateVocabularyError",
    "GenerationError",
    "GenerationStep",
    "PlaceResolutionError",
    "PlaceResolutionStep",
    "ReportNotFoundError",
    "SectionsConfigError",
]

#: The closed set of steps birthplace resolution can fail at -- a free-form
#: string would let a later call site introduce an inconsistent label (e.g.
#: "geocode" vs "geocoding") that error handling or tests key off of.
PlaceResolutionStep = Literal["geocoding", "timezone_resolution", "cache"]

#: The closed set of steps a ``Generator`` call can fail at (Story 4.5) -- a
#: free-form string would let a later call site introduce an inconsistent
#: label that error handling or tests key off of. ``"request"`` is the
#: Gemini call itself raising or timing out; ``"parsing"`` is a response that
#: is not the expected JSON structure; ``"citation_validation"`` is a
#: returned ``entry_id`` absent from the ``Payload``; ``"date_token_validation"``
#: is a date-shaped token inside ``giorni_favorevoli``/``giorni_di_attenzione``,
#: where dates are code-projected upstream (Story 3.7) and the model must
#: never write one.
GenerationStep = Literal["request", "parsing", "citation_validation", "date_token_validation"]


class EphemerisIntegrityError(RuntimeError):
    """The vendored Swiss Ephemeris cannot be trusted.

    Raised when the ephemeris manifest is missing or malformed, a vendored
    ``.se1`` file is absent, or a present file's SHA-256 does not match the
    pinned manifest. There is no degraded ephemeris to fall back to: pyswisseph
    would otherwise silently select Moshier, which must never be an accepted
    runtime state, so the process refuses to start rather than compute against
    data it cannot verify.

    Raised only at startup, from :mod:`core.ephemeris.identity` -- the single
    declared exception to the purity boundary (AD-1) that is permitted to
    touch the filesystem. Letting it propagate uncaught is the non-zero exit;
    no explicit ``sys.exit`` is needed, mirroring how ``ConfigError`` already
    aborts startup from ``shell/config.py``.
    """


class ComputationConfigError(RuntimeError):
    """``data/computation.toml`` -- the one home for every astronomical tuning
    value (AD-18) -- cannot be trusted.

    Raised when the file is missing, its TOML is malformed, or a value it
    holds falls outside its permitted range (e.g. an orb outside FR-9's
    bounds). There is no partial or best-guess ``ComputationConfig`` to
    proceed with: the process refuses to start rather than compute against a
    value it cannot verify.

    Raised only at load time, from :mod:`shell.computation` -- mirrors how
    ``ConfigError`` and ``EphemerisIntegrityError`` already abort startup.
    """


class SectionsConfigError(RuntimeError):
    """``data/sections.toml`` -- the declarative Section-to-Payload mapping
    (Story 3.6, AD-13) -- cannot be trusted.

    Raised when the file is missing, its TOML is malformed, it does not
    contain exactly the six required Section keys, or a value it holds is
    the wrong shape or names an unsupported ``house_bodies``/``aspect_bodies``
    selector. There is no partial or best-guess ``SectionsConfig`` to proceed
    with: the process refuses to start rather than assemble a Payload against
    a mapping it cannot verify.

    Raised only at load time, from :mod:`shell.sections` -- mirrors how
    ``ComputationConfigError`` already aborts startup.
    """


class GateVocabularyError(RuntimeError):
    """``core/gate/vocabulary.it.json`` -- the versioned closed Italian
    vocabulary that decides what counts as a Claim (Story 5.1, AD-8) --
    cannot be trusted.

    Raised when the file is missing, its JSON is malformed, one of the six
    required category keys is absent, or a value it holds is the wrong shape
    (a non-string list entry, or ``version`` not an integer). There is no
    partial or best-guess ``GateVocabulary`` to proceed with: the process
    refuses to start rather than classify Claims against a vocabulary it
    cannot verify.

    Raised only at load time, from :mod:`shell.gate` -- mirrors how
    ``SectionsConfigError`` already aborts startup.
    """


class PlaceResolutionError(RuntimeError):
    """A birthplace could not be resolved to coordinates and a historical
    UTC offset (FR-2).

    There is no degraded chart to fall back to -- houses, ascendant and
    midheaven are load-bearing on the resolved place, so a Client is never
    persisted from a partial resolution (AD-16). Raised from
    :mod:`shell.adapters.nominatim` or :mod:`shell.adapters.postgres.place_cache`,
    naming which step failed -- geocoding, historical offset/zone lookup, or
    the cache read -- rather than letting a raw network or database exception
    escape untyped. Never used to signal an ambiguous match: multiple
    candidates are a successful resolution, returned as a list, not an error.
    """

    def __init__(self, step: PlaceResolutionStep, message: str) -> None:
        self.step = step
        super().__init__(f"Refusing to resolve birthplace ({step}): {message}")


class GenerationError(RuntimeError):
    """A ``Generator`` call (Story 4.5, AD-3) could not be trusted enough to
    return a ``GeneratedDraft``.

    There is no partial or best-guess draft to fall back to -- an unknown
    cited ``entry_id`` or a date-shaped token in ``giorni_favorevoli``/
    ``giorni_di_attenzione`` means the model's response cannot be trusted,
    so nothing is returned rather than something unverifiable. Raised from
    :mod:`shell.adapters.gemini.generator`, naming which step failed --
    the request itself, parsing the response, citation validation, or
    date-token validation -- rather than letting a raw SDK or JSON exception
    escape untyped. Date-token validation is a best-effort regex heuristic
    (Design Notes), not a completeness guarantee -- Francesco's own review
    before export is the final backstop, same as register and non-fatalism.
    """

    def __init__(self, step: GenerationStep, message: str) -> None:
        self.step = step
        super().__init__(f"Refusing to return a generated draft ({step}): {message}")


class GateFailedError(RuntimeError):
    """The Groundedness Gate (Story 5.2, ``core/gate/run.py::run_gate()``)
    rejected a ``GeneratedDraft``: at least one Claim is ungrounded in, or
    contradicts, this run's Report Payload.

    There is no partial or best-guess ``Report`` to fall back to -- a
    ``Report`` row is written only on a passing ``GateResult``, never before
    (Story 5.3's Boundaries), so nothing is persisted rather than something
    unverifiable. Raised from :mod:`shell.runner.driver`'s ``gate_passed``
    stage function, where ``drive()`` catches it in a dedicated
    ``except GateFailedError`` branch, separate from every other stage's
    generic failure handling (Story 5.4): it increments
    ``run.regeneration_count`` (never ``run.stage_failure_count``, which is
    left untouched) and, while that count is at or below
    ``_MAX_REGENERATIONS``, rewinds ``run.stage`` to ``payload_ready`` so the
    next ``drive()`` call regenerates a whole new ``GeneratedDraft`` from the
    same stored Payload and re-checks it. Only once
    ``run.regeneration_count`` exceeds ``_MAX_REGENERATIONS`` is the run
    marked terminally failed (``failed_at``/``failure_reason`` set), with
    ``run.stage`` left at ``draft_ready`` so the last, still-failing draft
    stays reachable rather than discarded. Carries the failing
    ``GateResult``'s own violations, for a future story (5.5) to surface
    directly to Francesco.
    """

    def __init__(self, violations: tuple[GateViolation, ...]) -> None:
        self.violations = violations
        super().__init__(
            "Refusing to advance past the Groundedness Gate: "
            f"{len(violations)} violation(s) against the Payload."
        )


class ReportNotFoundError(RuntimeError):
    """No passed ``Report`` row exists for the id an export was attempted
    against (Story 5.3).

    There is no partial or best-guess export to fall back to -- a ``Report``
    row is written only on a passing Groundedness Gate result
    (``shell/runner/driver.py``'s ``gate_passed`` stage), so this is also how
    "the Gate has not passed" refuses export: there is no separate check for
    it, because the row's mere absence already encodes it. Raised from
    :mod:`shell.export`'s ``export_report()``, naming the ``report_id`` that
    was refused, rather than letting a bare ``session.get()`` return ``None``
    escape untyped.
    """

    def __init__(self, report_id: UUID) -> None:
        self.report_id = report_id
        super().__init__(f"Refusing to export: no passed Report exists for report_id={report_id}.")
