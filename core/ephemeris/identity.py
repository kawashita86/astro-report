"""Verifies the vendored Swiss Ephemeris files before anything may compute against them.

This is the single declared exception to the purity boundary (AD-1): the rest
of ``core/`` touches nothing outside itself, but the ephemeris identity check
must read the vendored ``.se1`` files and their manifest from disk before
``swe.set_ephe_path()`` can be trusted. It exists so that a missing, swapped or
silently upgraded ephemeris file is caught before the application serves
anything, rather than the same code silently producing different numbers on
different deployments.

``verify_ephemeris_identity()`` has no side effect on import -- the shell
calls it eagerly, at import time, exactly the way ``shell/config.py`` calls
``load_settings()``. See ``shell/http/app.py``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import swisseph as swe

from core.errors import EphemerisIntegrityError

__all__ = [
    "DEFAULT_EPHEMERIS_DIR",
    "EphemerisFile",
    "EphemerisIdentity",
    "verify_ephemeris_identity",
]

#: The vendored ephemeris ships alongside the application code -- it is not a
#: deployment fact, so it is not a ``shell/config.py`` setting. Resolved from
#: this file's own location rather than the process's current directory, so
#: the check behaves the same regardless of where the process was started.
DEFAULT_EPHEMERIS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ephemeris"

_MANIFEST_FILENAME = "SHA256SUMS"

#: Bytes read per chunk while hashing: large enough to be fast, small enough
#: that hashing never holds a whole vendored file in memory at once.
_HASH_CHUNK_SIZE = 1024 * 1024

_SHA256_HEX_LENGTH = 64


@dataclass(frozen=True)
class EphemerisFile:
    """One vendored ephemeris file, identified by name and confirmed SHA-256."""

    filename: str
    sha256: str


@dataclass(frozen=True)
class EphemerisIdentity:
    """The verified identity of the ephemeris this process is computing against.

    Nothing persists this yet -- Epic 3's Report Payload does that. This is
    the value a later component reads in order to persist it.
    """

    files: tuple[EphemerisFile, ...]


def _parse_manifest(manifest_path: Path) -> dict[str, str]:
    """Parse a ``sha256sum``-format manifest into ``{filename: sha256}``.

    Accepts both the plain (``<hash>  <filename>``) and binary-mode
    (``<hash> *<filename>``) forms ``sha256sum`` itself produces. A filename
    recorded with a leading path (as ``sha256sum data/ephemeris/x`` writes it)
    is matched by its basename, since the manifest travels with the directory
    it describes.
    """
    if not manifest_path.is_file():
        raise EphemerisIntegrityError(
            f"Refusing to start: ephemeris manifest not found at {manifest_path}. "
            "The vendored ephemeris cannot be verified without it."
        )

    try:
        text = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise EphemerisIntegrityError(
            f"Refusing to start: ephemeris manifest {manifest_path} could not be read: "
            f"{error}."
        ) from error

    entries: dict[str, str] = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        digest = parts[0]
        is_valid_line = len(parts) == 2 and len(digest) == _SHA256_HEX_LENGTH and all(
            character in "0123456789abcdefABCDEF" for character in digest
        )
        if not is_valid_line:
            raise EphemerisIntegrityError(
                f"Refusing to start: ephemeris manifest {manifest_path} is malformed "
                f"at line {lineno}: expected `<sha256>  <filename>`, got {raw_line!r}."
            )
        filename = parts[1][1:] if parts[1].startswith("*") else parts[1]
        basename = Path(filename).name
        if basename in entries:
            raise EphemerisIntegrityError(
                f"Refusing to start: ephemeris manifest {manifest_path} names "
                f"{basename!r} more than once, at line {lineno}."
            )
        entries[basename] = digest.lower()

    if not entries:
        raise EphemerisIntegrityError(
            f"Refusing to start: ephemeris manifest {manifest_path} names no files."
        )
    return entries


def _sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        raise EphemerisIntegrityError(
            f"Refusing to start: ephemeris file {path} could not be read: {error}."
        ) from error


def _check_for_unlisted_files(ephemeris_dir: Path, manifest: dict[str, str]) -> None:
    """Anything in the directory that isn't the manifest or a manifest-listed
    file is unverified -- and ``swe.set_ephe_path()`` grants pyswisseph access
    to the whole directory, not just the files this check named."""
    allowed = set(manifest) | {_MANIFEST_FILENAME}
    unlisted = sorted(
        path.name
        for path in ephemeris_dir.iterdir()
        if path.is_file() and path.name not in allowed
    )
    if unlisted:
        raise EphemerisIntegrityError(
            f"Refusing to start: {ephemeris_dir} contains file(s) not named in "
            f"{_MANIFEST_FILENAME}: {', '.join(unlisted)}. Every file pyswisseph "
            "could read from this directory must be verified."
        )


def verify_ephemeris_identity(
    ephemeris_dir: Path = DEFAULT_EPHEMERIS_DIR,
) -> EphemerisIdentity:
    """Verify the vendored ephemeris and pin pyswisseph to it.

    Reads ``<ephemeris_dir>/SHA256SUMS``, confirms every file it names is
    present with a matching SHA-256, and only then calls
    ``swe.set_ephe_path()`` against ``ephemeris_dir`` -- so pyswisseph never
    has an ephemeris path set unless every file behind it has already been
    confirmed. There is no code path here that lets computation proceed on an
    unset or unverified path, so Moshier is never reached.

    Raises:
        EphemerisIntegrityError: naming the manifest problem, the missing
            file, or the mismatched file -- whichever is encountered first.
    """
    manifest_path = ephemeris_dir / _MANIFEST_FILENAME
    manifest = _parse_manifest(manifest_path)
    _check_for_unlisted_files(ephemeris_dir, manifest)

    verified: list[EphemerisFile] = []
    for filename, expected_sha256 in manifest.items():
        file_path = ephemeris_dir / filename
        if not file_path.is_file():
            raise EphemerisIntegrityError(
                f"Refusing to start: ephemeris file missing: {file_path} "
                f"(named in {manifest_path})."
            )
        actual_sha256 = _sha256(file_path)
        if actual_sha256 != expected_sha256:
            raise EphemerisIntegrityError(
                f"Refusing to start: ephemeris file {file_path} does not match its "
                f"pinned checksum. Expected {expected_sha256}, got {actual_sha256}."
            )
        verified.append(EphemerisFile(filename=filename, sha256=actual_sha256))

    try:
        swe.set_ephe_path(str(ephemeris_dir))
    except Exception as error:
        raise EphemerisIntegrityError(
            f"Refusing to start: pyswisseph rejected the ephemeris path {ephemeris_dir}: "
            f"{error}."
        ) from error
    return EphemerisIdentity(files=tuple(verified))
