"""Ephemeris identity verification — one test per row of the story's I/O matrix,
plus the properties the matrix implies: the identity value is frozen,
``swe.set_ephe_path()`` is only ever called once verification has fully
succeeded, and a real vendored file gets caught if it stops matching the
committed manifest.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest

import core.ephemeris.identity as identity_module
from core.ephemeris.identity import (
    DEFAULT_EPHEMERIS_DIR,
    EphemerisFile,
    EphemerisIdentity,
    bind_verified_ephemeris_path_to_current_thread,
    verify_ephemeris_identity,
)
from core.errors import EphemerisIntegrityError

REPO_ROOT = Path(__file__).resolve().parent.parent

_SEPL_BYTES = b"not a real ephemeris file, just fixture bytes for sepl_18.se1"
_SEMO_BYTES = b"not a real ephemeris file, just fixture bytes for semo_18.se1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_manifest(directory: Path, entries: dict[str, bytes]) -> None:
    lines = [f"{_sha256(data)}  {filename}" for filename, data in entries.items()]
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_valid_fixture(directory: Path) -> dict[str, bytes]:
    entries = {"sepl_18.se1": _SEPL_BYTES, "semo_18.se1": _SEMO_BYTES}
    for filename, data in entries.items():
        (directory / filename).write_bytes(data)
    _write_manifest(directory, entries)
    return entries


# --- Matrix row: valid vendored files, hashes match the manifest -------------


def test_valid_fixture_returns_the_verified_identity(tmp_path: Path) -> None:
    entries = _write_valid_fixture(tmp_path)

    identity = verify_ephemeris_identity(ephemeris_dir=tmp_path)

    assert isinstance(identity, EphemerisIdentity)
    assert set(identity.files) == {
        EphemerisFile(filename=name, sha256=_sha256(data)) for name, data in entries.items()
    }


def test_valid_fixture_calls_set_ephe_path_against_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_valid_fixture(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        "core.ephemeris.identity.swe.set_ephe_path", lambda path: calls.append(path)
    )

    verify_ephemeris_identity(ephemeris_dir=tmp_path)

    assert calls == [str(tmp_path)]


def test_the_real_vendored_files_verify_against_the_committed_manifest() -> None:
    """The manifest actually committed to the repo, checked against the actual
    committed files -- not a fixture. Regression coverage for `sha256sum -c`."""
    identity = verify_ephemeris_identity(ephemeris_dir=DEFAULT_EPHEMERIS_DIR)

    assert {f.filename for f in identity.files} == {"sepl_18.se1", "semo_18.se1"}
    for ephemeris_file in identity.files:
        on_disk = (DEFAULT_EPHEMERIS_DIR / ephemeris_file.filename).read_bytes()
        assert ephemeris_file.sha256 == hashlib.sha256(on_disk).hexdigest()


# --- Matrix row: missing file --------------------------------------------------


def test_a_missing_file_refuses_to_start_and_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_valid_fixture(tmp_path)
    (tmp_path / "semo_18.se1").unlink()
    calls: list[str] = []
    monkeypatch.setattr(
        "core.ephemeris.identity.swe.set_ephe_path", lambda path: calls.append(path)
    )

    with pytest.raises(EphemerisIntegrityError) as raised:
        verify_ephemeris_identity(ephemeris_dir=tmp_path)

    assert "semo_18.se1" in str(raised.value)
    assert "missing" in str(raised.value)
    assert calls == [], "the ephemeris path must never be set on a failed verification"


# --- Matrix row: checksum mismatch ---------------------------------------------


def test_a_checksum_mismatch_refuses_to_start_and_names_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_valid_fixture(tmp_path)
    (tmp_path / "sepl_18.se1").write_bytes(b"corrupted contents")
    calls: list[str] = []
    monkeypatch.setattr(
        "core.ephemeris.identity.swe.set_ephe_path", lambda path: calls.append(path)
    )

    with pytest.raises(EphemerisIntegrityError) as raised:
        verify_ephemeris_identity(ephemeris_dir=tmp_path)

    message = str(raised.value)
    assert "sepl_18.se1" in message
    assert "checksum" in message
    assert calls == []


def test_a_checksum_mismatch_names_expected_and_actual_hashes(tmp_path: Path) -> None:
    entries = _write_valid_fixture(tmp_path)
    corrupted = b"corrupted contents"
    (tmp_path / "sepl_18.se1").write_bytes(corrupted)

    with pytest.raises(EphemerisIntegrityError) as raised:
        verify_ephemeris_identity(ephemeris_dir=tmp_path)

    message = str(raised.value)
    assert _sha256(entries["sepl_18.se1"]) in message
    assert _sha256(corrupted) in message


# --- Matrix row: manifest missing or malformed ---------------------------------


def test_a_missing_manifest_refuses_to_start_and_names_the_problem(tmp_path: Path) -> None:
    (tmp_path / "sepl_18.se1").write_bytes(_SEPL_BYTES)
    (tmp_path / "semo_18.se1").write_bytes(_SEMO_BYTES)

    with pytest.raises(EphemerisIntegrityError) as raised:
        verify_ephemeris_identity(ephemeris_dir=tmp_path)

    message = str(raised.value)
    assert "SHA256SUMS" in message
    assert "not found" in message


@pytest.mark.parametrize(
    "malformed_content",
    [
        "this is not a checksum manifest at all\n",
        "deadbeef sepl_18.se1\n",  # too short to be a sha256
        "\n\n",  # blank -- no files named
        f"{'a' * 64}\n",  # hash with no filename
    ],
)
def test_a_malformed_manifest_refuses_to_start_and_names_the_problem(
    tmp_path: Path, malformed_content: str
) -> None:
    (tmp_path / "sepl_18.se1").write_bytes(_SEPL_BYTES)
    (tmp_path / "semo_18.se1").write_bytes(_SEMO_BYTES)
    (tmp_path / "SHA256SUMS").write_text(malformed_content, encoding="utf-8")

    with pytest.raises(EphemerisIntegrityError) as raised:
        verify_ephemeris_identity(ephemeris_dir=tmp_path)

    message = str(raised.value)
    assert "SHA256SUMS" in message
    assert "Refusing to start" in message


def test_a_malformed_manifest_error_is_not_a_generic_traceback(tmp_path: Path) -> None:
    """The failure must be the typed error, not a bare exception from deep inside
    parsing (e.g. a ValueError from an unpack)."""
    (tmp_path / "SHA256SUMS").write_text("garbage\n", encoding="utf-8")

    with pytest.raises(EphemerisIntegrityError):
        verify_ephemeris_identity(ephemeris_dir=tmp_path)


def test_a_duplicate_manifest_entry_refuses_to_start_and_names_it(tmp_path: Path) -> None:
    """Two lines naming the same file would otherwise silently overwrite each
    other -- the second (possibly swapped-in) hash winning with no diagnostic."""
    (tmp_path / "sepl_18.se1").write_bytes(_SEPL_BYTES)
    (tmp_path / "semo_18.se1").write_bytes(_SEMO_BYTES)
    (tmp_path / "SHA256SUMS").write_text(
        f"{_sha256(_SEPL_BYTES)}  sepl_18.se1\n{'a' * 64}  sepl_18.se1\n", encoding="utf-8"
    )

    with pytest.raises(EphemerisIntegrityError) as raised:
        verify_ephemeris_identity(ephemeris_dir=tmp_path)

    assert "sepl_18.se1" in str(raised.value)


def test_the_binary_mode_manifest_form_is_accepted(tmp_path: Path) -> None:
    """``sha256sum``'s binary-mode output (``<hash> *<filename>``) is documented
    as accepted by ``_parse_manifest`` but was previously exercised by nothing."""
    entries = {"sepl_18.se1": _SEPL_BYTES, "semo_18.se1": _SEMO_BYTES}
    for filename, data in entries.items():
        (tmp_path / filename).write_bytes(data)
    lines = [f"{_sha256(data)} *{filename}" for filename, data in entries.items()]
    (tmp_path / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    identity = verify_ephemeris_identity(ephemeris_dir=tmp_path)

    assert {f.filename for f in identity.files} == set(entries)


# --- Matrix-adjacent: the directory carries nothing beyond what's verified -----


def test_an_unlisted_extra_file_refuses_to_start_and_names_it(tmp_path: Path) -> None:
    """``swe.set_ephe_path()`` grants pyswisseph access to the whole directory --
    a file that isn't in the manifest is unverified regardless of what else
    passes, so its mere presence must refuse startup."""
    _write_valid_fixture(tmp_path)
    (tmp_path / "sepl_19.se1").write_bytes(b"an ephemeris file nobody vendored on purpose")

    with pytest.raises(EphemerisIntegrityError) as raised:
        verify_ephemeris_identity(ephemeris_dir=tmp_path)

    assert "sepl_19.se1" in str(raised.value)


# --- set_ephe_path failure surfaces as the typed error, not a raw exception -----


def test_set_ephe_path_failure_is_wrapped_as_the_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_valid_fixture(tmp_path)
    monkeypatch.setattr(
        "core.ephemeris.identity.swe.set_ephe_path",
        lambda path: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(EphemerisIntegrityError) as raised:
        verify_ephemeris_identity(ephemeris_dir=tmp_path)

    assert "boom" in str(raised.value)


# --- Identity value shape -------------------------------------------------------


def test_identity_and_file_are_frozen_dataclasses() -> None:
    import dataclasses

    assert dataclasses.is_dataclass(EphemerisIdentity)
    assert EphemerisIdentity.__dataclass_params__.frozen is True
    assert dataclasses.is_dataclass(EphemerisFile)
    assert EphemerisFile.__dataclass_params__.frozen is True


def test_identity_rejects_mutation(tmp_path: Path) -> None:
    import dataclasses

    _write_valid_fixture(tmp_path)
    identity = verify_ephemeris_identity(ephemeris_dir=tmp_path)

    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.files = ()  # type: ignore[misc]


# --- Startup behavior: the shell asserts this eagerly, at import time ----------


def test_importing_the_app_with_a_renamed_vendored_file_exits_non_zero(tmp_path: Path) -> None:
    """The verification command from the story, run as its own process: remove a
    committed vendored file, attempt `from shell.http import app`, and confirm the
    import raises -- non-zero exit, naming the offender -- rather than serving.
    The file is moved *outside* `data/ephemeris/`, not merely renamed in place:
    a displaced file left inside the directory would itself be flagged as an
    unlisted extra file, masking the "missing" failure this test means to prove.
    Restored in `finally` regardless of outcome.
    """
    target = DEFAULT_EPHEMERIS_DIR / "sepl_18.se1"
    displaced = tmp_path / "sepl_18.se1.displaced-by-test"
    assert target.is_file(), "the vendored file must exist before this test can mean anything"

    shutil.move(str(target), str(displaced))
    try:
        completed = subprocess.run(
            [sys.executable, "-c", "from shell.http import app"],
            cwd=REPO_ROOT,
            env={
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": str(REPO_ROOT),
                "ENVIRONMENT": "local",
                "DATABASE_URL": "postgresql://astro:astro@localhost:5432/astro_report",
                "PORT": "8000",
                "AUTH_PASSWORD_HASH": (
                    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
                    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
                ),
                "SESSION_SECRET_KEY": "test-session-secret-key-at-least-32-chars-long",
                "GEMINI_API_KEY": "test-gemini-api-key",
                "GEMINI_DATA_TERMS_VERIFIED_AT": "2026-01-15",
            },
            capture_output=True,
            text=True,
        )
    finally:
        shutil.move(str(displaced), str(target))

    assert completed.returncode != 0
    assert "sepl_18.se1" in completed.stderr
    assert "missing" in completed.stderr


# --- Per-thread path binding (epic-3-retro item 22) ---------------------------
#
# pyswisseph's `swed` state -- the ephemeris path included -- is thread-local in
# the vendored build. `verify_ephemeris_identity()` runs on the shell's import
# thread, but a computation dispatched to a FastAPI worker thread would start
# with no path and fall back to Moshier. Every `swe.calc_ut` / `swe.houses`
# entry point in `core/ephemeris/` re-binds the verified path to its own thread
# first, via `bind_verified_ephemeris_path_to_current_thread()`.


@pytest.fixture
def _restore_thread_bind_state() -> object:
    """Snapshot and restore the module-level verified dir and this thread's
    bind marker, for tests that mutate them directly."""
    saved_dir = identity_module._verified_ephemeris_dir
    saved_bound = getattr(identity_module._thread_state, "bound_dir", None)
    yield
    identity_module._verified_ephemeris_dir = saved_dir
    identity_module._thread_state.bound_dir = saved_bound


def test_bind_is_a_noop_once_the_current_thread_holds_the_verified_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # conftest's autouse fixture just ran verify_ephemeris_identity() on this
    # (main) thread, so it is already bound to the real vendored directory.
    calls: list[str] = []
    monkeypatch.setattr(
        "core.ephemeris.identity.swe.set_ephe_path", lambda path: calls.append(path)
    )

    bind_verified_ephemeris_path_to_current_thread()
    bind_verified_ephemeris_path_to_current_thread()

    assert calls == []


def test_bind_sets_the_path_exactly_once_on_a_fresh_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "core.ephemeris.identity.swe.set_ephe_path", lambda path: calls.append(path)
    )

    def worker() -> None:
        for _ in range(5):
            bind_verified_ephemeris_path_to_current_thread()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert calls == [str(DEFAULT_EPHEMERIS_DIR)]


def test_bind_refuses_when_verification_has_not_run_in_this_process(
    _restore_thread_bind_state: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(identity_module, "_verified_ephemeris_dir", None)

    def worker() -> None:
        # a fresh thread has no cached bind, so the None branch is reached
        bind_verified_ephemeris_path_to_current_thread()

    errors: list[BaseException] = []

    def run() -> None:
        try:
            worker()
        except EphemerisIntegrityError as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert len(errors) == 1
    assert isinstance(errors[0], EphemerisIntegrityError)
    assert "verify_ephemeris_identity" in str(errors[0])


def test_bind_rebinds_when_the_verified_dir_changes(
    _restore_thread_bind_state: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "core.ephemeris.identity.swe.set_ephe_path", lambda path: calls.append(path)
    )
    # The main thread is currently bound to the real vendored dir (conftest).
    identity_module._verified_ephemeris_dir = "/some/other/verified/dir"

    bind_verified_ephemeris_path_to_current_thread()

    assert calls == ["/some/other/verified/dir"]


def test_calc_body_computes_the_same_value_on_a_worker_thread_as_on_the_main_thread() -> None:
    """The regression test for the shipped bug: `_calc_body` on a worker thread
    must not fall back to Moshier (which `_calc_body` itself would then reject)."""
    from core.ephemeris.positions import _calc_body, _julian_day_ut

    jd_ut = _julian_day_ut(datetime(2026, 9, 15, 0, 0, 0))

    main_thread_result = _calc_body(jd_ut, 0)
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker_thread_result = pool.submit(_calc_body, jd_ut, 0).result()

    assert worker_thread_result == main_thread_result
