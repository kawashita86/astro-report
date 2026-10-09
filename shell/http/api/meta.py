"""The ``meta`` block every chart response carries.

It exists so the plugin can store, next to each frozen result, exactly which
configuration and ephemeris produced it -- the same traceability a Report
Payload gives the operator UI (CAP-14). Pure of I/O: it only reads the
already-verified values handed in.
"""

from __future__ import annotations

import hashlib
from typing import Any

from core.ephemeris.identity import EphemerisIdentity
from core.payload.freeze import canonical_json_bytes
from core.types.computation import ComputationConfig

__all__ = ["API_VERSION", "build_meta", "ephemeris_manifest_sha256"]

#: Reported in every response; bumped only with the ``/api/v<N>`` prefix.
API_VERSION = "1"

#: All charts are tropical -- there is no sidereal option anywhere in the system.
ZODIAC = "tropical"


def ephemeris_manifest_sha256(identity: EphemerisIdentity) -> str:
    """SHA-256 over the sorted ``[filename, sha256]`` pairs of the verified files.

    Derived from data the startup identity check already confirmed, so no file
    is read per request and the value changes exactly when a vendored file does.
    """
    pairs = sorted([file.filename, file.sha256] for file in identity.files)
    return hashlib.sha256(canonical_json_bytes(pairs)).hexdigest()


def build_meta(config: ComputationConfig, identity: EphemerisIdentity) -> dict[str, Any]:
    """The ``meta`` block for a chart response."""
    return {
        "api_version": API_VERSION,
        "computation": {
            "version": config.version,
            "content_hash": config.content_hash,
            "house_system": config.house_system.name,
            "orbs": {"natal": str(config.orbs.natal), "transit": str(config.orbs.transit)},
        },
        "ephemeris": {"manifest_sha256": ephemeris_manifest_sha256(identity)},
        "zodiac": ZODIAC,
    }
