---
title: 'Story 1.3 — An ephemeris whose identity is asserted before the application serves anything'
type: 'feature'
created: '2026-08-15'
status: 'done'
review_loop_iteration: 0
baseline_commit: '858082f10a0e28bf0de61f7851dd034c4455110a'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing pins which Swiss Ephemeris data the application computes against. If the vendored files are ever missing, swapped, or silently upgraded, pyswisseph can select a different ephemeris than the one the code was validated against — the same code then produces different numbers on different deployments, landing a station or cusp crossing on the wrong day.

**Approach:** Vendor `sepl_18.se1`/`semo_18.se1`, pin their SHA-256 in a manifest committed alongside them, and add a `core/ephemeris/` check that reads both files, verifies each hash, and calls `swe.set_ephe_path()` — called eagerly at shell import time (mirroring `shell/config.py`'s own pattern), so a missing file or a mismatch raises before the app can serve, non-zero exit, naming the offender. Moshier is never reached.

## Boundaries & Constraints

**Always:**
- `pyswisseph==2.10.3.2` is the only new runtime dependency this story adds (per the Structural Seed stack table); Kerykeion is Epic 2's concern, not this story's.
- The vendored files come from `https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/{sepl_18,semo_18}.se1` — the GitHub mirror Astrodienst's own `astro.com/ftp/swisseph/ephe/` page now points to. Compute the SHA-256 from the bytes you actually download; do not copy a checksum from anywhere without verifying it yourself against your own download.
- The Dockerfile's build stage installs `build-essential` (gcc/g++/make) and nothing else new — deliberately **not** `pkg-config` or `libsqlite3-dev`, so pyswisseph's setup.py falls back to its fully bundled `libswe`+`sqlite3` sources deterministically (validated in a clean `python:3.13-slim` container: without a compiler the build fails cleanly on a missing `gcc`; with only `build-essential` it builds and a real position `swe.calc_ut()` call succeeds against the vendored files).
- The Dockerfile must `COPY data/ ./data/` — it currently doesn't, so the vendored files never reach the image regardless of what's committed.
- Verification (read + SHA-256 + `swe.set_ephe_path()`) happens inside `core/ephemeris/` — the one declared exception to the purity boundary (AD-1) — and is invoked eagerly, at shell import time, exactly like `shell/config.py`'s `settings: Settings = load_settings()`. A missing/mismatched file raises a typed error from `core/errors.py`; letting it propagate uncaught is the non-zero exit, no explicit `sys.exit` needed (same mechanism as `ConfigError` today).
- The verified identity (filenames + their confirmed SHA-256) is returned as a frozen value core/ephemeris exposes — nothing persists it yet; Epic 3's Report Payload does that later.

**Ask First:** None anticipated — the download source and Docker fix are both validated below, not open questions.

**Never:**
- No fallback to Moshier under any configuration — that path must not exist, not even behind a flag.
- No Kerykeion, no chart computation, no `computation.toml` wiring — out of scope for this story.
- No persistence of the identity value (no table, no column) — Epic 3's job.
- No `pkg-config`/`libsqlite3-dev` in the image — see Always; adding them reintroduces exactly the fragile system-library-detection path this story avoids.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid vendored files | Both `.se1` files present, hashes match the manifest | `swe.set_ephe_path()` called; identity value returned; app serves | N/A |
| Missing file | One `.se1` file absent from `data/ephemeris/` | App refuses to start | Names the missing file, non-zero exit |
| Checksum mismatch | A `.se1` file present but its SHA-256 doesn't match the manifest | App refuses to start | Names the file and that its hash didn't match |
| Manifest missing/malformed | `data/ephemeris/SHA256SUMS` absent or unparsable | App refuses to start | Names the manifest problem, not a generic traceback |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `shell/config.py:181-212` -- the exact pattern to mirror: `load_settings()` raises `ConfigError` (a `RuntimeError` subclass), called once at module import (`settings: Settings = load_settings()`), uncaught → non-zero exit naming the offender.
- `shell/http/app.py` -- `create_app()` is where `config.settings` is already consumed at import time (`app = create_app(config.settings)`); the ephemeris check hooks in the same way.
- `core/errors.py`, `core/ephemeris/__init__.py` -- existing docstring-only stubs from Story 1.2 to fill in.
- `Dockerfile:19-29` -- single-stage build; needs `build-essential` added before `uv sync`, and a `COPY data/ ./data/` line alongside the existing `core/`/`shell/`/`migrations/` copies.
- `.dockerignore`, `.gitignore` -- neither excludes `data/` or `*.se1`; no changes needed there.
- `_bmad-output/planning-artifacts/epics.md:451-476` -- Story 1.3 acceptance criteria verbatim.

**To create:**
- `data/ephemeris/sepl_18.se1`, `data/ephemeris/semo_18.se1` -- vendored, downloaded fresh and verified per Boundaries
- `data/ephemeris/SHA256SUMS` -- standard `sha256sum`-format manifest, independently checkable with `sha256sum -c`
- `core/ephemeris/identity.py` (naming your call) -- reads the manifest and both files, verifies, calls `swe.set_ephe_path()`, returns the identity value
- `core/errors.py` -- add the typed error raised on a missing file or hash mismatch

**To modify:**
- `Dockerfile` -- add `build-essential`, add `COPY data/ ./data/`
- `pyproject.toml`, `uv.lock` -- add `pyswisseph==2.10.3.2`
- `shell/http/app.py` -- invoke the ephemeris check at import time, same shape as `config.settings`

## Tasks & Acceptance

**Execution:**
- [x] `data/ephemeris/sepl_18.se1`, `data/ephemeris/semo_18.se1`, `data/ephemeris/SHA256SUMS` -- vendor the files and pin their real, independently-recomputed checksums -- AC1
- [x] `pyproject.toml`, `uv.lock` -- add `pyswisseph==2.10.3.2` -- prerequisite for AC2
- [x] `Dockerfile` -- add `build-essential` before `uv sync`; add `COPY data/ ./data/` -- without both, the image either fails to build or ships without the files it needs to verify
- [x] `core/errors.py` -- typed error naming the offending file and reason (missing vs. mismatch) -- AC3
- [x] `core/ephemeris/identity.py` -- verify-then-`set_ephe_path()`, returning the identity value -- AC2, AC4
- [x] `shell/http/app.py` -- call the check eagerly at import time, mirroring `config.settings` -- AC2, AC3
- [x] Test the I/O matrix's four rows, including a deliberately corrupted/missing fixture case proving the refusal actually fires

**Acceptance Criteria:**
- Given the repository, when the ephemeris is vendored, then `data/ephemeris/sepl_18.se1` and `data/ephemeris/semo_18.se1` are committed with their SHA-256 pinned from the files actually downloaded.
- Given the application starting up, when the shell initializes the ephemeris, then it calls `swe.set_ephe_path()` against the vendored directory and verifies each file against its pinned SHA-256.
- Given a missing file or checksum mismatch, when the application starts, then it refuses to start, names the failing file, and never falls back to Moshier under any configuration.
- Given the running application, when the ephemeris identity is requested by a component that must record it, then it is available as a value later stories can persist.

## Spec Change Log

- **2026-08-15 (review round 1) — six patch findings applied to `core/ephemeris/identity.py`
  and the test suite.** All three parallel reviewers independently flagged the strongest
  finding: nothing in the diff proved a Dockerfile regression (a deleted `COPY data/ ./data/`
  or a removed/reordered `build-essential` install) would be caught before an actual deploy —
  `uv run pytest` stays green either way, since the repo checkout always has `data/ephemeris/`
  on disk regardless of what the Dockerfile does. Fixed with a new
  `tests/test_dockerfile_ephemeris_build.py`, mirroring `test_migrations_precede_traffic.py`'s
  structural, comment-stripped read of the Dockerfile. The remaining patches close real gaps
  in `verify_ephemeris_identity()` itself: `_sha256()` now wraps its file read in
  `try/except OSError`, matching `_parse_manifest`'s existing pattern, instead of letting a
  bare `OSError` escape untyped on a TOCTOU race; `swe.set_ephe_path()` is now wrapped the
  same way; a manifest naming the same file twice now raises instead of the second hash
  silently overwriting the first with no diagnostic; a file present in the ephemeris directory
  but *not* named in the manifest now refuses startup, since `swe.set_ephe_path()` grants
  pyswisseph access to the whole directory, not just the files this check named; and the
  binary-mode manifest parsing (`<hash> *<filename>`) the module already documented and
  implemented, but nothing exercised, now has a test. Applying the unlisted-file check also
  surfaced a latent bug in the story's own end-to-end subprocess test: it renamed the real
  vendored file to a `.displaced-by-test` sibling *inside* the same directory, which the new
  check correctly flagged as an unverified extra file — masking the "missing" failure the test
  meant to prove. Fixed by moving the file to `tmp_path` (outside `data/ephemeris/`) via
  `shutil.move` rather than `Path.rename`, since `tmp_path` and the repo checkout are not
  guaranteed to share a filesystem. **KEEP:** the manifest-driven, sha256sum-format design and
  the eager-at-import-time wiring mirroring `shell/config.py` — both proved to be exactly the
  right shape to extend without any structural rework. Not applied, and logged in
  `deferred-work.md` instead: date-range validation for future `swe.calc_ut()` calls (the most
  severe finding, but Epic 2's scope, not this boot-time check's), Docker image reproducibility
  (unpinned `build-essential`, still single-stage — escalates story 1.1's already-deferred
  item), the subprocess test's remaining real-file mutation and hardcoded environment
  (git-recoverable, low-probability, needs a small design call to fix properly), and the new
  local C-compiler requirement being undocumented in the README.

## Design Notes

The Docker fix was validated end-to-end in a clean `python:3.13-slim` container, not assumed: without a compiler, `pip install pyswisseph` fails on a missing `gcc`; with only `build-essential` added (no `pkg-config`, no `libsqlite3-dev`), it builds via pyswisseph's own bundled `libswe`+`sqlite3` fallback and a real `swe.calc_ut()` call against the vendored files returns correct planetary longitudes. Installing `pkg-config` would make the build's outcome depend on whatever system libraries happen to be present — strictly worse than the deterministic bundled path.

The two files were downloaded fresh from `raw.githubusercontent.com/aloistr/swisseph/master/ephe/` (484,061 and 1,304,771 bytes) and exercised against real `swe.calc_ut()` calls in the same clean container before being treated as trustworthy — do the same rather than trusting any checksum handed to you, including the one in this spec if a prior run recorded one.

## Verification

**Commands:**
- `sha256sum -c data/ephemeris/SHA256SUMS` -- the committed manifest matches the committed files
- `uv run pytest` -- full suite green, including the new ephemeris-identity tests
- `uv run ruff check .` -- clean
- `docker build -t astro-report .` -- succeeds with the new build dependency
- `docker run --rm astro-report python -c "import swisseph"` -- importable in the built image without the dev-only compiler being invoked at runtime
- Rename or corrupt one vendored file locally, attempt `python -c "from shell.http import app"` -- import raises, non-zero exit, names the file

## Suggested Review Order

**Boot-time verification — the entry point**

- Start here: read the manifest, verify every file, only then hand pyswisseph the path — no code path lets computation proceed unverified.
  [`identity.py:152`](../../core/ephemeris/identity.py#L152)

- Eager at import time, exactly like `shell/config.py`'s own `settings = load_settings()` — a bad ephemeris aborts before the app can serve.
  [`app.py:52`](../../shell/http/app.py#L52)

**Hardening added after review — closing gaps the reviewers found**

- A file in the directory but not in the manifest is unverified regardless of what else passes; `set_ephe_path()` grants access to the whole directory.
  [`identity.py:134`](../../core/ephemeris/identity.py#L134)

- Duplicate manifest entries used to overwrite silently; now the second one raises instead of masking the first.
  [`identity.py:105`](../../core/ephemeris/identity.py#L105)

- A TOCTOU race on the file read now surfaces as the typed error, matching the pattern `_parse_manifest` already used.
  [`identity.py:121`](../../core/ephemeris/identity.py#L121)

**The gap none of the tests would have caught — a silent Dockerfile regression**

- Deleting `COPY data/ ./data/` or the `build-essential` install stayed green in `uv run pytest`; this structural check (mirroring the migration-ordering test) closes that.
  [`test_dockerfile_ephemeris_build.py:49`](../../tests/test_dockerfile_ephemeris_build.py#L49)
  [`test_dockerfile_ephemeris_build.py:58`](../../tests/test_dockerfile_ephemeris_build.py#L58)

**Tests — the new offender-proofs, and the one that had a latent bug**

- Proves the two hardening checks above actually fire.
  [`test_ephemeris_identity.py:192`](../../tests/test_ephemeris_identity.py#L192)
  [`test_ephemeris_identity.py:224`](../../tests/test_ephemeris_identity.py#L224)
  [`test_ephemeris_identity.py:240`](../../tests/test_ephemeris_identity.py#L240)

- The end-to-end subprocess test itself had a bug the new unlisted-file check exposed: renaming in place left a stray file the check correctly flagged, masking the intended failure. Fixed to move the file outside the directory entirely.
  [`test_ephemeris_identity.py:280`](../../tests/test_ephemeris_identity.py#L280)

**The vendored data**

- The manifest the whole check is built around; independently recomputed and cross-checked, not copied from a prior run.
  [`SHA256SUMS`](../../data/ephemeris/SHA256SUMS)

- Where the compiler dependency comes from — validated in a clean container, not assumed.
  [`Dockerfile:21`](../../Dockerfile#L21)
