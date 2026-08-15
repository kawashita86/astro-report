---
title: 'Story 1.6 — A conformance harness that runs before there is anything to conform'
type: 'feature'
created: '2026-08-15'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'd0eab09090c1f0ee2da58d8646925fc6c589a499'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing checks computed output against Astro.com, and — a real, pre-existing gap this story's own AC4 makes unavoidable — nothing runs this codebase's tests automatically at all. `render.yaml` auto-deploys every commit; every guard built since story 1.1 ("this is a rule only while this test exists") is opt-in, run only if someone remembers to run `pytest` by hand.

**Approach:** A fixture-walking runner in `tests/conformance/`, generic enough to need no Epic 2/3 data types yet (fixtures are TOML; comparison is a recursive dict diff), plus the GitHub Actions workflow that makes AC4 ("conformance is not an on-demand check") literally true — which incidentally starts running the other ~260 existing tests automatically too, closing the gap flagged since story 1.1's review and never picked up. Ships with zero fixtures; Story 1.7 (Francesco's job, not a developer's — BUILD-ORDER.md is explicit) adds the first ones.

## Boundaries & Constraints

**Always:**
- `.github/workflows/ci.yml` runs on push to `main` and on pull requests: `uv sync --locked`, `uv run ruff check .`, `uv run pytest`. No extra `apt-get install` step — GitHub's actual `ubuntu-latest` runner image ships `build-essential` by default (a materially different, far more complete image than the bare `ubuntu:latest` Docker base — verified by testing the bare image, which does *not* have `gcc`, to confirm this isn't something to take on faith either way).
- No Postgres service container needed: `tests/test_migration_chain.py` already runs Alembic in offline mode against a fake host (`db.example.eu`) that nothing connects to — confirmed by reading it, not assumed.
- The fixture format is generic TOML (`metadata` + `birth_data` + `expected` tables) with no dependency on Epic 2/3 types that don't exist yet — comparison walks `expected` vs. computed output as plain nested dicts/lists, building a dotted field path (e.g. `expected.planets[0].longitude`) for any mismatch. This is deliberate: when Epic 2 lands, wiring in real computation means writing one function, not redesigning the harness.
- `tests/conformance/fixtures/` ships with a `README.md` documenting the format (not a bare `.gitkeep`) — the directory's only content until Story 1.7, and Story 1.7's actual audience.
- The call site where real computation will eventually plug in is a single, clearly-named function that raises `NotImplementedError` until Epic 2/3 exist. It is never reached while the fixture set is empty — a parametrized pytest test over zero fixtures contributes zero cases, never executing the body.
- AC3 (mismatch reporting names fixture/field/expected/computed) is proven now, without real astronomy, by unit-testing the comparator directly against synthetic fixtures with a deliberately-wrong value — mirroring every prior story's "prove the guard can fail" pattern (`tests/test_import_boundary.py`, `tests/test_env_access_is_centralized.py`).
- AC2 ("reports zero fixtures... rather than failing") gets one explicit, always-passing, distinctly-named test asserting the discovered count is a list (never raises) — not left to an empty parametrize's silent absence of test cases, which satisfies the letter of "doesn't fail" but not "reports."

**Ask First:** None anticipated — the CI recipe and the "no Postgres needed" claim are both verified below, not assumed.

**Never:**
- No wiring CI as a required check that blocks `render.yaml`'s auto-deploy — AC4 asks that the harness *runs*, not that it gates deployment. That's a real, separate decision (GitHub branch protection plus a Render-side integration) worth making deliberately, not as a side effect of this story.
- No real fixture data — that is Story 1.7's, and per BUILD-ORDER.md explicitly needs Francesco, not a developer.
- No Epic 2/3 domain types (`NatalChart`, `TransitEvent`, etc.) invented early to make the harness "feel" more real. The comparator stays generic.
- No caching optimization for the CI workflow — not asked for, and premature until the suite's runtime is actually a problem.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Empty fixture directory | `tests/conformance/fixtures/` has no `.toml` files | Harness runs, reports zero fixtures, suite passes | N/A |
| A fixture whose expected values mismatch computed output | Synthetic fixture + synthetic computed dict, deliberately differing on one field | Comparison fails | Names the fixture, the field (dotted path), the expected value, the computed value |
| A fixture with all matching values | Synthetic fixture + matching computed dict | Comparison succeeds, no mismatches | N/A |
| Any repository change | A commit pushed to `main`, or a pull request opened | GitHub Actions runs `ruff` + the full `pytest` suite (including this harness) automatically | A failing step fails the CI run |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `tests/test_import_boundary.py`, `tests/test_env_access_is_centralized.py` -- the "prove the guard can fail" pattern to mirror for the comparator's own tests.
- `tests/test_migration_chain.py:104-162` -- confirms offline-mode Alembic needs no real Postgres; the exact reason CI needs no service container.
- `Dockerfile:19` -- `pip install --no-cache-dir uv==0.10.0`; CI installs the same pinned version, the same way.
- `pyproject.toml` -- `testpaths = ["tests"]` already covers `tests/conformance/`; no pytest config change needed.
- `_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/BUILD-ORDER.md:80-96` (E1) -- "the harness ships empty and fills as E2 and E3 land"; "this chunk needs Francesco, not a developer" (Story 1.7).
- `_bmad-output/implementation-artifacts/deferred-work.md` (story 1.1 entry, "No CI pipeline runs the test suite...") -- the gap this story closes; do not add a second entry for it, update nothing there, just close it in fact.
- `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md:333-349` (FR-9) -- the eventual comparison targets (planetary positions, house cusps, natal Aspects, Transit Events) that inform, but don't constrain, the fixture format's flexibility.

**To create:**
- `.github/workflows/ci.yml` -- checkout, install `uv==0.10.0`, `uv sync --locked`, `uv run ruff check .`, `uv run pytest`
- `tests/conformance/__init__.py`
- `tests/conformance/runner.py` -- `Fixture`, `Mismatch`, `discover_fixtures()`, `load_fixture()`, `compare()`
- `tests/conformance/fixtures/README.md` -- the TOML format documented for Story 1.7
- `tests/test_conformance.py` -- the CI-visible entry point (zero-fixtures report test + parametrized-over-discovered-fixtures test with the `NotImplementedError` compute placeholder)
- `tests/test_conformance_runner.py` -- unit tests proving discover/load/compare, including the deliberate-mismatch case

## Tasks & Acceptance

**Execution:**
- [x] `.github/workflows/ci.yml` -- runs lint + full suite on push/PR -- AC4
- [x] `tests/conformance/runner.py` -- discover, load, compare -- AC1, AC3
- [x] `tests/conformance/fixtures/README.md` -- format documented, directory tracked empty -- AC1
- [x] `tests/test_conformance.py` -- zero-fixtures report test, parametrized comparison test -- AC2, AC3
- [x] `tests/test_conformance_runner.py` -- proves mismatch detection names fixture/field/expected/computed -- AC3

**Acceptance Criteria:**
- Given `tests/conformance/fixtures/`, when the harness is built, then a runner walks every fixture and the format records birth data, expected planetary positions, house cusps, natal Aspects, and — for month fixtures — expected Transit Events.
- Given an empty fixture set, when CI runs, then the runner executes successfully and reports zero fixtures rather than failing.
- Given a fixture whose expected values do not match computed output, when the runner executes, then it fails and names the fixture, the field, the expected value and the computed value.
- Given the harness, when any change is made to the repository, then it runs — conformance is not an on-demand check.

## Spec Change Log

- **2026-08-15 (review round 1) — six patch findings applied.** Two of three
  reviewers independently found the same real gap in `load_fixture()`: it checked that
  `metadata`/`birth_data`/`expected` *keys* were present, but never that their *values*
  were actually TOML tables — a fixture with `expected = "oops"` (valid TOML, wrong
  shape) would pass validation and fail confusingly later, breaking the module's own
  "fail loudly, name the offender" promise. Fixed with an explicit
  `isinstance(..., dict)` check per required table, naming the offending table and its
  actual type. The same reviewer pair separately caught that `load_fixture()` caught
  `OSError` but not `UnicodeDecodeError` on the read — a non-UTF-8 fixture file crashed
  instead of failing cleanly; fixed by catching both. Also added to `.github/workflows/ci.yml`:
  an explicit `permissions: contents: read` block (was running with the broader
  default `GITHUB_TOKEN` scope), a `timeout-minutes: 10` job limit (a hung test
  previously had no ceiling below GitHub's own default), and reworded the header
  comment's hardcoded "~260 existing tests" count, which would have silently gone
  stale as the suite grows. Closed the specific risk a reviewer named — nothing kept
  the CI workflow's pinned `uv==0.10.0` in sync with the Dockerfile's identical pin if
  one were bumped alone — with a new `tests/test_ci_workflow.py`, mirroring
  `tests/test_dockerfile_ephemeris_build.py`'s structural-read pattern, that also pins
  the workflow's triggers and the two new hygiene additions so a future edit can't
  quietly drop them either. **KEEP:** the "fail loudly, name the offender" convention
  already established by `shell/config.py`/`shell/computation.py`/`core/ephemeris/identity.py`
  — extending it to the fixture loader required no new pattern, just applying the
  existing one to a gap it hadn't yet covered. Not applied, and logged in
  `deferred-work.md` instead: wiring CI as a required check that gates `render.yaml`'s
  auto-deploy (a real, separate decision with real trade-offs); the `Decimal`-vs-TOML-string
  bridging convention `compare()` will need once Story 1.7/Epic 2 wire in real values
  (belongs with the function that produces them, not invented speculatively here);
  and `discover_fixtures()`'s non-recursive glob plus the lack of an
  xfail-style incomplete-fixture marker (both fine for the "at least three" fixtures
  Story 1.7 adds next, worth revisiting once the set actually grows). Reviewer claims
  not applied because they didn't hold up: dependency caching and `ruff format`
  contradict or exceed this story's own frozen Never-boundaries; an explicit
  `actions/setup-python` step is unnecessary since `.python-version` already pins
  `3.13` and `uv` manages that toolchain itself — verified directly, not assumed.

## Design Notes

The comparator is a plain recursive dict/list diff (`expected` vs. computed), not a schema-typed comparison — Epic 2/3 haven't defined `NatalChart`/`TransitEvent` shapes yet, and binding the harness to a guessed shape now would mean redesigning it later rather than just writing the one function that produces a matching dict. This costs a little type safety today in exchange for the harness never needing to change shape once real computation exists.

## Verification

**Commands:**
- `uv run pytest` -- full suite green, including the new conformance tests
- `uv run ruff check .` -- clean
- `uv run pytest tests/test_conformance.py -v` -- shows the zero-fixtures report test passing explicitly
- Push the branch (or open a PR) and confirm the GitHub Actions run actually executes and passes -- the one check that can't be proven locally

## Suggested Review Order

**The harness — the entry point**

- Start here: parse, validate, load. The "fail loudly, name the offender" convention this story extends.
  [`runner.py:92`](../../tests/conformance/runner.py#L92)

- CI's own trigger + command definitions — what makes AC4 literally true.
  [`ci.yml`](../../.github/workflows/ci.yml)

**Hardening added after review — closing the gap two reviewers found independently**

- A required table present but the wrong TOML type (`expected = "oops"`) used to pass validation silently; now it's named.
  [`test_conformance_runner.py:145`](../../tests/test_conformance_runner.py#L145)

- A non-UTF-8 fixture file used to crash instead of failing cleanly.
  [`test_conformance_runner.py:134`](../../tests/test_conformance_runner.py#L134)

**CI hygiene — closing the one risk with no existing regression test**

- Nothing kept the CI/Dockerfile `uv` pins in sync; this is what would have caught it.
  [`test_ci_workflow.py:53`](../../tests/test_ci_workflow.py#L53)
