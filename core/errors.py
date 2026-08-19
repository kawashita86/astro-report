"""Typed domain errors: core never returns ``None`` to mean failure."""

from __future__ import annotations

from typing import Literal

__all__ = [
    "ComputationConfigError",
    "EphemerisIntegrityError",
    "PlaceResolutionError",
    "PlaceResolutionStep",
    "SectionsConfigError",
]

#: The closed set of steps birthplace resolution can fail at -- a free-form
#: string would let a later call site introduce an inconsistent label (e.g.
#: "geocode" vs "geocoding") that error handling or tests key off of.
PlaceResolutionStep = Literal["geocoding", "timezone_resolution", "cache"]


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
