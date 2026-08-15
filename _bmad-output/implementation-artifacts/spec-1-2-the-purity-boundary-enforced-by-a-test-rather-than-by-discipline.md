---
title: 'Story 1.2 — The purity boundary, enforced by a test rather than by discipline'
type: 'feature'
created: '2026-08-15'
status: 'done'
review_loop_iteration: 0
baseline_commit: '2bf6c275f57d9012452a98a1c60bc60b9d469223'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `core/` and `shell/` exist only as two `__init__.py` files with docstring promises. Nothing stops a future change from importing `shell/` into `core/`, or reading the clock, network, filesystem or environment from inside `core/` — and by the time that happens once, the byte-identical-Payload guarantee is already broken, possibly silently.

**Approach:** Create the full `core/` and `shell/` subpackage layout from the architecture spine, then add `tests/test_import_boundary.py`: a syntactic (AST-based, not import-based) guard mirroring `tests/test_env_access_is_centralized.py`'s pattern — parses every source file under `core/` and fails the build if any imports from `shell/`, or imports a network, clock, filesystem or environment facility, except inside the single declared exception `core/ephemeris/`.

## Boundaries & Constraints

**Always:**
- The guard parses source with `ast`, never imports it — a module the app never happens to import at test time must still be caught.
- `core/` may never import anything from `shell/`, anywhere, no exceptions.
- Outside `core/ephemeris/`, no module under `core/` may import a network (`socket`, `urllib*`, `requests`, `httpx`, `aiohttp`), clock-reading (`time.time`/`time.monotonic`, `datetime.datetime.now`/`utcnow`), filesystem (`open`, `pathlib.Path.open`/`read_text`/`write_text`, `os.open`), or environment (`os.environ`/`os.getenv`, `dotenv`, etc. — reuse the denylist already proven in `test_env_access_is_centralized.py`) facility. Using `datetime`/`Decimal`/etc. as **types** on values passed in is not a violation; reading the clock or a file is.
- `core/ephemeris/` may read its vendored `.se1` files from disk; nothing else in `core/` may.
- The guard runs on every `pytest` invocation (already covered: `testpaths = ["tests"]` in `pyproject.toml`), and must itself be proven able to fail (a `tmp_path`-based offender test, per the env-access test's own pattern).
- No module anywhere in the tree is named `utils.py`, `helpers.py` or `common.py` (file or package).
- Every new package directory gets an `__init__.py` with a one-line docstring stating its role — no placeholder logic, no `pass`-only bodies beyond what a docstring-only module already is.

**Ask First:** None anticipated — this story only adds structure and a test, no runtime behavior change.

**Never:**
- No logic inside the new `core/` subpackages (`types/`, `ephemeris/`, `transits/`, `domains/`, `payload/`, `memory/`, `gate/`) or `core/errors.py` beyond a docstring — later stories populate them.
- No logic inside the new `shell/` subpackages (`ports/`, `adapters/`, `runner/`) beyond a docstring.
- Do not touch `shell/config.py`, `shell/http/`, or `tests/test_env_access_is_centralized.py` — that boundary is already enforced and out of scope here.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Clean tree | No `core/` → `shell/` imports, no forbidden facility use outside `core/ephemeris/` | Guard passes | N/A |
| Forbidden cross-import | A file under `core/` adds `from shell.config import Settings` | Guard fails | Names the offending file, line, and import |
| Forbidden facility, general `core/` | A file under `core/domains/` adds `import requests` or `time.time()` | Guard fails | Names the file, line, and facility category |
| Declared exception | `core/ephemeris/loader.py` calls `Path(...).read_bytes()` | Guard passes | N/A |
| Same call outside the exception | `core/transits/foo.py` calls `Path(...).read_bytes()` | Guard fails | Names the file, line, and facility category |
| Forbidden module name | A file named `core/utils.py` or `shell/adapters/common/` exists | Guard fails | Names the offending path |

</frozen-after-approval>

## Code Map

**Read-only references (pattern to mirror):**
- `tests/test_env_access_is_centralized.py` -- structural template: `ast.NodeVisitor` subclass collecting findings, `pytest.mark.parametrize` per source file, a `test_every_source_root_is_actually_covered` guard, and a `tmp_path`-based `test_the_guard_detects_a_new_reader` proof. Reuse this shape and its `_OS_ENVIRONMENT_MEMBERS`/`_ENVIRONMENT_MODULES` denylists rather than re-deriving them.
- `core/__init__.py`, `shell/__init__.py` -- already state the purity rule in prose; the new test makes it mechanical.
- `_bmad-output/implementation-artifacts/epic-1-context.md` §Technical Decisions -- source tree list and the single declared ephemeris exception.
- `_bmad-output/planning-artifacts/epics.md:427-450` -- Story 1.2 acceptance criteria verbatim.

**To create:**
- `core/types/__init__.py`, `core/errors.py`, `core/ephemeris/__init__.py`, `core/transits/__init__.py`, `core/domains/__init__.py`, `core/payload/__init__.py`, `core/memory/__init__.py`, `core/gate/__init__.py` -- docstring-only package roots per the architecture tree
- `shell/ports/__init__.py`, `shell/adapters/__init__.py`, `shell/runner/__init__.py` -- docstring-only package roots
- `tests/test_import_boundary.py` -- the AST-based guard described above

## Tasks & Acceptance

**Execution:**
- [x] `core/types/`, `core/errors.py`, `core/ephemeris/`, `core/transits/`, `core/domains/`, `core/payload/`, `core/memory/`, `core/gate/` -- create as docstring-only package roots (except `errors.py`, a single module) -- AC1
- [x] `shell/ports/`, `shell/adapters/`, `shell/runner/` -- create as docstring-only package roots -- AC1
- [x] `tests/test_import_boundary.py` -- AST visitor detecting `core/`→`shell/` imports and forbidden-facility imports outside `core/ephemeris/`; parametrized per file under `core/`; include a `test_the_guard_detects_a_new_reader`-style proof test using `tmp_path` fixtures for each denylisted category and the ephemeris exception -- AC2, AC3
- [x] `tests/test_import_boundary.py` -- guard asserting no module anywhere in the tree is named `utils`, `helpers` or `common` (file or package) -- AC1's last clause

**Acceptance Criteria:**
- Given the source tree, when it is created, then `core/` contains `types/`, `errors.py`, `ephemeris/`, `transits/`, `domains/`, `payload/`, `memory/` and `gate/`, `shell/` contains `config.py`, `ports/`, `adapters/`, `runner/` and `http/`, and no module anywhere is named `utils`, `helpers` or `common`.
- Given `tests/test_import_boundary.py`, when it runs under `pytest`, then it fails on any `core/`→`shell/` import and on any forbidden-facility import under `core/` outside `core/ephemeris/`.
- Given a deliberately introduced `core/`→`shell/` import, when `pytest` runs, then it fails and names the offending module and line.

## Spec Change Log

- **2026-08-15 (review round 1) — six patch findings applied to `tests/test_import_boundary.py`.**
  All three parallel reviewers (blind-hunter, edge-case-hunter, verification-gap) independently
  flagged that the clock-facility check matched only the literal names `time`/`datetime`, so an
  aliased import (`import time as t`, `import datetime as dt`) or `from time import time` bypassed
  it entirely — the verification-gap reviewer confirmed this by running the visitor against those
  exact snippets and getting an empty findings list. Fixed by tracking `time`/`datetime` module
  aliases the same way `os` aliases already were, plus a bound-name tracker for `from time import
  ...` mirroring the existing `_bound_env_names` pattern. Also folded in, as the same mechanical
  sweep: `.today()` on both `datetime.datetime` and `datetime.date` (was undetected), more `time`
  members (`perf_counter`, `perf_counter_ns`, `monotonic_ns`, `time_ns`, `gmtime`, `localtime`),
  more `os`/`Path` filesystem members (`listdir`, `scandir`, `stat`, `remove`, `mkdir`, `rmdir`,
  `rename`, `walk`, `exists`, `is_file`, `is_dir`, `unlink`, `iterdir`, `glob`, `rglob`), more
  network-reaching modules (`ssl`, `http`, `ftplib`, `smtplib`, `urllib3`, `websockets`, `grpc`,
  `subprocess` — the last folded into `_NETWORK_MODULES` rather than given its own category, since
  it defeats the whole boundary in one import), `environs` alongside the existing `environ` in the
  environment denylist, and `vendor`/`dist`/`build`/`.mypy_cache`/`htmlcov` in the module-name
  scan's excluded directories to prevent a future false positive. A new
  `test_core_outside_ephemeris_is_actually_covered` mirrors the existing
  `test_ephemeris_exception_is_exercised` so the facility parametrize can't silently go empty.
  Every new denylist entry got a corresponding offender case in the relevant
  `test_the_guard_detects_a_*` proof test. **KEEP:** the two-visitor split (Design Notes below) and
  the alias-tracking pattern borrowed from `test_env_access_is_centralized.py`'s `_os_aliases` — both
  proved to be exactly the right shape to extend. Not applied: a fifth "randomness" facility
  category and `ast.parse`/`read_text` exception handling, both out of this spec's frozen scope and
  logged in `deferred-work.md`; a handful of reviewer suggestions rejected as factually incorrect
  (relative-import bypass claim — not exploitable, since dotted relative imports cannot cross into a
  sibling top-level package; `sprint-status.yaml`/`core`+`shell` `__init__.py` claims about
  pre-existing state) or already correct as designed (the repo-wide, `tests/`-inclusive scope of
  `FORBIDDEN_MODULE_NAMES` matches the epic's own "anywhere in the tree" wording).

## Design Notes

Two independently-parametrized checks are cleaner than one combined visitor: one pass over every file under `core/` for `shell` imports (simple, no exceptions), a second pass restricted to `core/` files outside `core/ephemeris/` for the four facility denylists. Forcing both into a single `NodeVisitor` invites a missed branch when the ephemeris exception needs to apply to only one of the two rules.

## Verification

**Commands:**
- `uv run pytest tests/test_import_boundary.py -q` -- all pass, including the offender-detection proof tests
- `uv run pytest` -- full suite still green, no regression in `test_env_access_is_centralized.py` or the migration/config tests
- `uv run ruff check .` -- clean

## Suggested Review Order

**The two-visitor guard**

- Start here: `core/` may never import `shell/`, no exceptions, no aliasing to worry about.
  [`test_import_boundary.py:160`](../../tests/test_import_boundary.py#L160)

- The facility visitor: network/clock/filesystem/environment routes, tracked via aliases like `os` already was.
  [`test_import_boundary.py:179`](../../tests/test_import_boundary.py#L179)

- Alias-aware clock/filesystem checks -- the review-round fix for `import time as t` bypassing detection.
  [`test_import_boundary.py:264`](../../tests/test_import_boundary.py#L264)

- Two parametrized tests apply the visitors to the real tree: one with no exceptions, one carving out `core/ephemeris/`.
  [`test_import_boundary.py:344`](../../tests/test_import_boundary.py#L344)
  [`test_import_boundary.py:385`](../../tests/test_import_boundary.py#L385)

**Facility denylists (widened after review)**

- Network/process denylist folds `subprocess` in rather than giving it its own category -- it defeats the whole boundary in one import.
  [`test_import_boundary.py:58`](../../tests/test_import_boundary.py#L58)

- Clock member list, now covering `perf_counter`/`monotonic_ns`/etc alongside the original `time`/`monotonic`.
  [`test_import_boundary.py:89`](../../tests/test_import_boundary.py#L89)

- Module-name scan walks the whole tree for `utils`/`helpers`/`common`, with vendor/build dirs now excluded.
  [`test_import_boundary.py:145`](../../tests/test_import_boundary.py#L145)

**Proof the guard can fail**

- The clock offender-proof test, now exercising aliased imports -- this is what the verification-gap reviewer ran by hand to confirm the original bypass.
  [`test_import_boundary.py:447`](../../tests/test_import_boundary.py#L447)

- New meta-test guarding against the facility parametrize silently going empty, mirroring the existing ephemeris-side one.
  [`test_import_boundary.py:408`](../../tests/test_import_boundary.py#L408)

**Source tree**

- `core/` and `shell/` subpackage stubs -- docstring-only, per the architecture tree; no logic until later stories need it.
  [`core/errors.py`](../../core/errors.py#L1)

