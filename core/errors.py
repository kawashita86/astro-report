"""Typed domain errors: core never returns ``None`` to mean failure."""

from __future__ import annotations

__all__ = ["ComputationConfigError", "EphemerisIntegrityError"]


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
