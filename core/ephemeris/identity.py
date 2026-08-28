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

``swe.set_ephe_path()`` pins the path per *thread* in the vendored pyswisseph
build, and ``verify_ephemeris_identity()`` runs on one thread (the shell's
import thread). ``bind_verified_ephemeris_path_to_current_thread()`` re-applies
the already-verified path to any other thread that computes -- e.g. a FastAPI
sync route handler on the anyio worker threadpool -- so the report pipeline
does not silently fall back to Moshier off the main thread.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

import swisseph as swe

from core.errors import EphemerisIntegrityError

__all__ = [
    "DEFAULT_EPHEMERIS_DIR",
    "EphemerisFile",
    "EphemerisIdentity",
    "bind_verified_ephemeris_path_to_current_thread",
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

#: The directory the most recent successful ``verify_ephemeris_identity()`` call
#: pinned pyswisseph to, as a string. ``None`` until that call has run in this
#: process. ``bind_verified_ephemeris_path_to_current_thread()`` re-applies it
#: to whatever thread is about to compute -- see that function's docstring for
#: why re-application is necessary at all.
_verified_ephemeris_dir: str | None = None

#: Per-thread record of which directory ``swe.set_ephe_path()`` has already been
#: called with *on this thread*. ``pyswisseph``'s ``swed`` state (the ephemeris
#: path included) is thread-local in this build, so this guard is keyed per
#: thread; keyed on the directory rather than a bare flag so a later
#: re-verification against a different directory forces every thread to re-bind.
_thread_state = threading.local()


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
    to the whole directory, not just the files this check named.

    ``ephemeris_dir.iterdir()`` is non-recursive and only ``path.is_file()``
    entries are considered, so a subdirectory is silently passed over. That is
    deliberate, not a gap: pyswisseph reads only files that sit directly in the
    ephe path it is handed, so a nested directory is not something it could load,
    and the vendored ephemeris is a flat directory by construction.
    ``path.is_file()`` follows symlinks, so a symlink pointing at a directory
    is skipped exactly like a real subdirectory -- the same non-recursion
    rationale covers it."""
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
    global _verified_ephemeris_dir

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

    resolved_dir = str(ephemeris_dir)
    try:
        swe.set_ephe_path(resolved_dir)
    except Exception as error:
        raise EphemerisIntegrityError(
            f"Refusing to start: pyswisseph rejected the ephemeris path {ephemeris_dir}: "
            f"{error}."
        ) from error

    # Record the verified directory so a computation running on another thread
    # can re-pin the same path (pyswisseph's path is thread-local in this
    # build). The line above already pinned it on *this* thread, so record that
    # too and skip a redundant re-set on the first `_calc_body` here.
    _verified_ephemeris_dir = resolved_dir
    _thread_state.bound_dir = resolved_dir

    return EphemerisIdentity(files=tuple(verified))


def bind_verified_ephemeris_path_to_current_thread() -> None:
    """Re-apply the already-verified ephemeris path to the calling thread.

    ``verify_ephemeris_identity()`` calls ``swe.set_ephe_path()`` once, on the
    thread that runs it (normally the shell's import thread). In the vendored
    ``pyswisseph`` build the ``swed`` struct -- ephemeris path included -- is
    thread-local, so a computation that runs on a *different* thread (a FastAPI
    sync route handler dispatched to the anyio worker threadpool, an
    ``anyio.to_thread`` call, a ``ThreadPoolExecutor`` worker) starts with no
    ephemeris path and ``swe.calc_ut`` silently falls back to Moshier.

    Every ``swe.calc_ut`` / ``swe.houses`` entry point in ``core/ephemeris/``
    calls this first. It re-sets the path on the current thread once and then
    becomes a no-op for that thread -- ``swe.set_ephe_path()`` closes the open
    ``.se1`` handles, so calling it per ``_calc_body`` would reopen the files
    on every position lookup of a month scan.

    The integrity guarantee is unchanged: if ``verify_ephemeris_identity()``
    has never run in this process there is no verified path to bind, and this
    raises rather than falling back to a default.

    Raises:
        EphemerisIntegrityError: ``verify_ephemeris_identity()`` has not run in
            this process.
    """
    verified_dir = _verified_ephemeris_dir
    if verified_dir is None:
        raise EphemerisIntegrityError(
            "Refusing to compute: verify_ephemeris_identity() has not run in this "
            "process, so there is no verified ephemeris path to bind to this "
            "thread. pyswisseph would fall back to Moshier."
        )
    if getattr(_thread_state, "bound_dir", None) == verified_dir:
        return
    swe.set_ephe_path(verified_dir)
    _thread_state.bound_dir = verified_dir
