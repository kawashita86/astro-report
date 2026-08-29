# Deferred Work

Findings surfaced by review that are real but not this story's problem. Each names
the spec that surfaced it. Append only.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-4-browse-everything-i-have-produced-for-a-client.md`
  summary: `ReportRun.natal_chart_id`'s traceability claim can silently diverge from the chart a stalled run's later stages actually computed against.
  evidence: `_drive_run` (`shell/http/routes/report_runs.py`) re-resolves `_current_chart()` fresh on every `drive()` call, including a poll that resumes a run stalled or regenerating after `natal_ready` already recorded a chart id. If the Client's chart is corrected between such polls, `transits_ready`/`payload_ready`/`draft_ready` compute against the newly-current chart while `run.natal_chart_id` still names the original one -- narrow (requires a correction landing mid-flight of the same Client's stalled run), pre-existing in `_drive_run`'s chart-sourcing design, not introduced by Story 6.4's new column.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-4-browse-everything-i-have-produced-for-a-client.md`
  summary: No page in the app links to `GET /clients/{client_id}/reports` (or to any other Client-scoped page) -- every Client-related route, this new one included, is reachable only by typing its URL.
  evidence: `grep` across `shell/http/templates/*.html` finds no reference to `/clients/.../reports`, `/clients/.../edit`, or `/clients/.../delete` from any other template; `POST /clients` itself returns plain text ("Client {id} created.") with no link anywhere. Pre-existing across the whole app, not specific to this story -- FR-27's "browse" is technically satisfied but only for someone who already knows the URL.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-4-browse-everything-i-have-produced-for-a-client.md`
  summary: Nothing prevents two passed Reports from sharing the same `(ReportRun.client_id, month)`, and the new history listing has no secondary sort key to order them deterministically if that happens.
  evidence: `start_report_run` (`shell/http/routes/report_runs.py`) only validates month format and that the Client exists before creating a new `ReportRun` -- no uniqueness check against existing runs for that Client/month. `list_client_reports`'s query orders by `ReportRun.month.desc()` alone, so two same-month Reports would render with an undefined relative order and no way to tell them apart in the list.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-4-browse-everything-i-have-produced-for-a-client.md`
  summary: Only one test in the whole suite (`test_delete_client_and_derived_succeeds_with_a_report_run_referencing_a_natal_chart`, `tests/test_client_store.py`) enables real SQLite foreign-key enforcement; every other cascade/deletion test still runs against the default non-enforcing connection.
  evidence: That test's own docstring explains why this matters: an FK-ordering bug in `delete_client_and_derived` passed the entire suite once already (this story's Spec Change Log) because SQLite does not enforce foreign keys by default. The fix closes the gap only for the one new relationship it was written to guard, not for the rest of the cascade or the wider test suite going forward.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-4-browse-everything-i-have-produced-for-a-client.md`
  summary: `alembic upgrade head` fails against a genuinely fresh database at revision `0014_bound_client_and_chart_string_columns`, unrelated to this story.
  evidence: Alembic's default `alembic_version.version_num` column is `VARCHAR(32)`, but this repo's revision ids are long descriptive strings -- `0014_bound_client_and_chart_string_columns` is 43 characters -- so writing it throws `StringDataRightTruncation`. Confirmed independently twice (by both implementation passes of this story, against a real throwaway Postgres container) that every migration from `0014` onward, including this story's own `0017`, has never actually been exercised end-to-end from a clean database.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-a-deployable-application-skeleton.md`
  summary: No CI pipeline runs the test suite, so every mechanical guard in the repository is opt-in while Render auto-deploys each commit.
  evidence: `render.yaml` sets `autoDeployTrigger: commit`, and there is no `.github/workflows` or equivalent. The guard tests carry docstrings saying "this is a rule only while this test exists" — but nothing runs them between a commit and the deploy it triggers. BUILD-ORDER's E0 "done when" clause expects the import-boundary test green *in CI*, so a pipeline is owed by Epic 1; Story 1.2 is its natural home.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-a-deployable-application-skeleton.md`
  summary: Concurrent `alembic upgrade head` runs are unguarded by an advisory lock.
  evidence: Migrations run on every container start. Any moment where two containers overlap (a redeploy, a manual restart mid-deploy) runs the upgrade twice in parallel, risking duplicate DDL and an `alembic_version` conflict. The free single-instance plan makes this near-impossible today, which is why it is deferred rather than fixed — but the constraint is a plan detail, not a design guarantee, and it stops holding the moment the service scales.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-a-deployable-application-skeleton.md`
  summary: `/healthz` is liveness-only, so a database that becomes unreachable after boot is invisible to the platform health check.
  evidence: `render.yaml` gates deploy promotion on a route that never touches Postgres. A deploy can therefore be promoted, and stay green, while every real request fails. Sits oddly beside the effort spent guaranteeing migrations complete before traffic. Wants a separate readiness probe once there is a Store port to probe (Epic 2).

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-a-deployable-application-skeleton.md`
  summary: `DATABASE_URL` validation does not require TLS, nor that the URL names a database.
  evidence: `_read_database_url` checks scheme and netloc only. A production Neon URL missing `?sslmode=require` is accepted silently, and `postgresql://user@host` (no database name) passes config validation and fails later at connection time. Both are policy decisions worth making deliberately rather than patching in under a scaffolding story.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-a-deployable-application-skeleton.md`
  summary: The migration step has no connect timeout, so a database that accepts TCP but never completes the handshake hangs the deploy indefinitely.
  evidence: `engine_from_config`/`create_engine` is called without `connect_args={"connect_timeout": ...}`. The entrypoint would neither succeed nor fail, leaving the deploy in limbo rather than aborting cleanly — the one failure mode the before-traffic ordering does not cover.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-a-deployable-application-skeleton.md`
  summary: The runtime image is single-stage and ships `pip` and `uv` alongside the application.
  evidence: `FROM python:3.13-slim AS base` names a stage no later stage consumes, so the full build surface remains in the deployed image. A builder stage copying `/app/.venv` forward would shrink the image and its attack surface. Pure optimization; nothing is broken.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-a-deployable-application-skeleton.md`
  summary: No LICENSE file, although the intended dependency chain carries AGPL-3.0 obligations.
  evidence: The architecture notes that Kerykeion → pyswisseph → Swiss Ephemeris is AGPL-3.0, and that the single-principal design is what keeps the remote-interaction source-offer obligation from attaching. That reasoning deserves to be recorded in the repository once those dependencies actually land (Epic 1 story 1.3 / Epic 2).

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-a-deployable-application-skeleton.md`
  summary: The single-environment-reader guard is syntactic and can be bypassed by dynamic access.
  evidence: `tests/test_env_access_is_centralized.py` walks the AST for direct `os.environ`/`getenv` references and import forms. `getattr(os, "environ")`, `importlib`, or `os.popen("env")` would evade it. Closing this fully is diminishing returns against an accidental second reader, which is the threat the guard actually exists to stop.

- source_spec: `_bmad-output/implementation-artifacts/spec-reconcile-story-1-1-status.md`
  summary: `sprint-status.yaml` has no audit trail linking a story's status to the commit, spec, or code-review round that produced it.
  evidence: The workflow notes describe a dev-moves-to-review-then-code-review cycle, and the header comments reference an `action_items` mechanism, but the file has neither a populated `action_items:` section nor any per-story field pointing back to a commit hash or spec file. Reconciling story 1-1's status required cross-referencing the spec's own frontmatter and Spec Change Log by hand; the tracker itself gives no way to audit "what made this true."

- source_spec: none
  summary: Guard `shell/runner/driver.py`'s two-write stage functions (`_run_gate_passed`'s `store_report`+`store_gate_result`, and `drive()`'s unguarded `except GateFailedError` block's own `store_gate_result` call) against a partial-flush-poisoned SQLAlchemy session (`epic-5-retro-item-39`, re-prioritizing the still-open `epic-4-retro-item-23`).
  evidence: Split from the epic-5-retrospective batch (`_bmad-output/implementation-artifacts/epic-5-retro-2026-08-25.md`, Finding 2) at the user's choice to tackle `epic-5-retro-item-38` alone first; deferred for its own focused plan/review cycle rather than bundled in.

- source_spec: none
  summary: Expand `core/gate`'s test suite (`tests/test_gate_classify.py`, `tests/test_gate_run.py`) with adversarial non-astrological Italian sentences (a bare 1-31 number as a duration/count, "casa" + ordinal in a mundane sense) to measure the classifier's documented false-positive rate (`epic-5-retro-item-40`).
  evidence: Split from the epic-5-retrospective batch (`_bmad-output/implementation-artifacts/epic-5-retro-2026-08-25.md`, Finding 3) at the user's choice to tackle `epic-5-retro-item-38` alone first.

- source_spec: none
  summary: Validate `vocabulary.it.json`'s `planets`/`signs`/`casa_ordinals` word sets against `core/gate/run.py`'s hardcoded `_BODY_MAP`/`_SIGN_MAP`/`_CASA_ORDINAL_TO_HOUSE` translation maps at load time in `shell/gate.py`, so a future vocabulary revision that adds an untranslated word fails loudly instead of silently under-checking that category (`epic-5-retro-item-41`).
  evidence: Split from the epic-5-retrospective batch (`_bmad-output/implementation-artifacts/epic-5-retro-2026-08-25.md`, Finding 4) at the user's choice to tackle `epic-5-retro-item-38` alone first.

- source_spec: none
  summary: Add a defensive try/except around `core/gate/run.py::_date_facts`'s `datetime.fromisoformat()` call, mirroring the isinstance-guard pattern its sibling fact-extraction functions already use, so a malformed Payload date degrades to a skipped fact rather than crashing `run_gate()` (`epic-5-retro-item-42`).
  evidence: Split from the epic-5-retrospective batch (`_bmad-output/implementation-artifacts/epic-5-retro-2026-08-25.md`, Finding 5) at the user's choice to tackle `epic-5-retro-item-38` alone first.

- source_spec: none
  summary: Add `"gate_passed": {"max_attempts": 1}` to `shell/runner/driver.py::_STAGE_BACKOFF_OVERRIDES`, since `run_gate()` is deterministic and retrying an already-failed check gains nothing (`epic-5-retro-item-43`).
  evidence: Split from the epic-5-retrospective batch (`_bmad-output/implementation-artifacts/epic-5-retro-2026-08-25.md`, Finding 6) at the user's choice to tackle `epic-5-retro-item-38` alone first.

- source_spec: none
  summary: Guard `shell/runner/driver.py::_run_draft_ready`'s attempt-tagged `store_report_draft` write against a concurrent `drive()` race (start route + poll route, no locking), matching the still-open `epic-4-retro-item-26`'s intended fix for the sibling `ReportPayload` case (`epic-5-retro-item-44`).
  evidence: Split from the epic-5-retrospective batch (`_bmad-output/implementation-artifacts/epic-5-retro-2026-08-25.md`, Finding 7) at the user's choice to tackle `epic-5-retro-item-38` alone first.

- source_spec: `_bmad-output/implementation-artifacts/spec-epic-5-retro-item-38-wire-view-report-draft-to-stored-gate-result.md`
  summary: `StoredGateResult` has no DB-level composite uniqueness on `(report_run_id, regeneration_count)`, and the "regeneration_count strictly increases across a run's writes" invariant view_report_draft's latest-row query now depends on is enforced only by prose in `gate_result.py`'s module docstring, not the schema or type system.
  evidence: Surfaced by the Blind Hunter review layer during `epic-5-retro-item-38`'s implementation. A future `shell/runner/driver.py` refactor could silently violate the invariant (e.g. two rows sharing a `regeneration_count`, breaking the "highest wins" ordering determinism) with no DB constraint and no test to catch it. Out of this story's scope, which explicitly excluded touching `StoredGateResult`/`driver.py`.

- source_spec: `_bmad-output/implementation-artifacts/spec-epic-5-retro-item-38-wire-view-report-draft-to-stored-gate-result.md`
  summary: `StoredGateResult.vocabulary_version`/`.created_at` are persisted specifically to answer "which vocabulary produced this, and when" but neither is surfaced anywhere in `view_report_draft`'s context or `report_draft.html`.
  evidence: Surfaced by the Blind Hunter review layer during `epic-5-retro-item-38`'s implementation. Francesco still has no way to see, from the draft view itself, which vocabulary version or check time produced the violations he's looking at -- only that they're now guaranteed to be the ones that actually caused the failure. Out of this story's scope, which explicitly excluded changing `report_draft.html`.

- source_spec: `_bmad-output/implementation-artifacts/spec-reconcile-story-1-1-status.md`
  summary: The story-status enum doesn't distinguish "implementation complete" from "human-gated manual steps confirmed."
  evidence: Story 1.1's spec lists a "Manual checks (Francesco — requires account access)" section (Render/Neon provisioning, post-deploy HTTPS verification) that only a human can perform. `sprint-status.yaml` has a single flat `done` state with no field recording whether those out-of-band checks were actually completed, so a story can read `done` while deploy-time verification remains unconfirmed.

- source_spec: `_bmad-output/implementation-artifacts/spec-reconcile-story-1-1-status.md`
  summary: Date fields in `sprint-status.yaml` use an ambiguous `MM-DD-YYYY` format instead of ISO-8601, and `generated` carries a time component while `last_updated` doesn't.
  evidence: `generated: 08-14-2026 09:15` and `last_updated: 08-15-2026` mix formats. `MM-DD-YYYY` is silently ambiguous with `DD-MM-YYYY` and will produce a genuinely wrong date the first time day and month values disagree on which is which.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-the-purity-boundary-enforced-by-a-test-rather-than-by-discipline.md`
  summary: Randomness (`random`, `uuid.uuid4`) is not a checked facility in `tests/test_import_boundary.py`, though it threatens the same byte-identical-Payload guarantee as the clock does.
  evidence: The story's own AC and frozen Boundaries name exactly four facilities — network, clock, filesystem, environment — mirroring epics.md's Story 1.2 acceptance criteria verbatim. Unseeded randomness inside `core/` would break reproducibility just as reading the clock does, but it was never in scope here; adding a fifth denylist category is a spec-level decision (does core ever need seeded randomness? is `uuid.uuid4()` for a non-persisted, non-computed value acceptable?) for a future story to make deliberately.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-the-purity-boundary-enforced-by-a-test-rather-than-by-discipline.md`
  summary: Neither `tests/test_import_boundary.py` nor the sibling `tests/test_env_access_is_centralized.py` it mirrors handles a `SyntaxError`/`UnicodeDecodeError` from `ast.parse`/`read_text` on a malformed source file — the guard would crash with a raw traceback instead of a clear assertion.
  evidence: Both files call `ast.parse(path.read_text(encoding="utf-8"), ...)` unguarded. Fixing only the new file would leave the two guards inconsistent with each other; the spec for 1.2 explicitly forbids touching `test_env_access_is_centralized.py`, so this is a cross-cutting hardening pass for both files together, better done as its own small story.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-an-ephemeris-whose-identity-is-asserted-before-the-application-serves-anything.md`
  summary: `sepl_18.se1`/`semo_18.se1` cover a bounded historical date range (~1800-2399); nothing yet stops a future call from requesting a position outside it, which could make pyswisseph reach for a different, unverified ephemeris file or silently fall back toward Moshier depending on the flags the caller passes.
  evidence: Story 1.3's own check only verifies the two vendored files' identity at boot — it never computes a position, so it can't and shouldn't validate arbitrary future dates itself. The real risk lands wherever Epic 2 first calls `swe.calc_ut()` for a natal/transit date; that story must either pass flags that force a hard error rather than a Moshier fallback, validate the requested date against the vendored files' covered range, or both. Consider also exposing the covered range from `EphemerisIdentity` (Story 1.3) so later callers have something to check against instead of re-deriving it. Flagged during Story 1.3's review by all three review layers independently; the most severe finding of that round, but out of Story 1.3's own frozen scope (boot-time file identity, not runtime call validation).

- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-an-ephemeris-whose-identity-is-asserted-before-the-application-serves-anything.md`
  summary: The Docker build installs `build-essential` unpinned and stays single-stage, so a full C/C++ compiler toolchain now ships permanently in the production runtime image (not just `pip`/`uv`, as story 1.1's already-deferred single-stage item noted).
  evidence: `pyswisseph` has no prebuilt wheel and must compile from source at every `uv sync`; `build-essential` is required for that, but only at build time. A multi-stage build copying only `/app/.venv` (plus vendored data) into a slim final stage would remove the compiler toolchain from what actually ships, per the story 1.1 deferred item this escalates rather than duplicates.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-an-ephemeris-whose-identity-is-asserted-before-the-application-serves-anything.md`
  summary: `tests/test_ephemeris_identity.py::test_importing_the_app_with_a_renamed_vendored_file_exits_non_zero` mutates the real committed vendored file in place (rename, then rename back in `finally`) and replaces the subprocess's entire environment with a hardcoded minimal set rather than reusing `Settings`' actual defaults.
  evidence: A hard kill between the rename and the `finally` block would leave `data/ephemeris/sepl_18.se1` missing from the working tree (git-recoverable via `git checkout`, not data loss, but every other test importing `shell.http.app` would then fail confusingly until restored). The hardcoded `env={...}` also duplicates values that live elsewhere and strips locale/`HOME`/SSL-cert environment variables, a portability risk on some systems. Fixing properly means deciding how to make the ephemeris directory overridable for this one subprocess test without adding a test-only hook to production code — a small design call, not a blind patch.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-an-ephemeris-whose-identity-is-asserted-before-the-application-serves-anything.md`
  summary: Local development now requires a C/C++ compiler toolchain (for `uv sync` to build `pyswisseph` from source), and this is undocumented in the README.
  evidence: `pyswisseph==2.10.3.2` ships as an sdist only; every environment running `uv sync --locked` — not only the Docker image — needs `gcc`/`g++`/`make` present. A contributor without one installed gets an opaque build failure with no pointer to the fix.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-sign-in-as-the-only-person-who-can-reach-this-application.md`
  summary: No response anywhere in the application sets security headers — no CSP, no `X-Frame-Options`, nothing — and `/login` is the one page an anonymous caller can always reach.
  evidence: `create_app()` never adds a headers middleware. This is a broader decision than Story 1.4's own scope (it would apply to every response, not just login), and the story's own Boundaries already scoped CSRF out for the same reason — a single-form, single-operator login is low-risk without it, but the decision should be made deliberately once more pages exist, not bolted onto this story piecemeal.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-sign-in-as-the-only-person-who-can-reach-this-application.md`
  summary: `AuthMiddleware` matches `request.url.path` against `ALLOWLIST` by exact string equality, with no trailing-slash or path normalization.
  evidence: Currently safe — the only effect of a path variant like `/login/` is an extra, fail-closed 401 (never a bypass), and no route has a slash-variant today. Two independent reviewers flagged it as an undocumented assumption; revisit once real protected routes exist and a `/login/`-style typo becomes a plausible user-facing papercut rather than a hypothetical.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-sign-in-as-the-only-person-who-can-reach-this-application.md`
  summary: `log_failed_login_attempt()` is the only log line sign-in ever writes — there is no corresponding line for a successful sign-in, so the log can show that access was denied but never that it was granted.
  evidence: The story's own Boundaries only required a failure log line (AC5's literal wording), so this isn't a spec violation, but an audit trail that only ever shows failures can't answer "when did Francesco actually sign in" from logs alone.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-one-home-for-every-astronomical-tuning-value.md`
  summary: `shell/computation.py` validates each field in isolation but performs no cross-field/semantic checks: `bodies.fast`/`bodies.slow` could overlap, `harmonic.harmonic_aspects`/`disharmonic_aspects` could name the same aspect in both lists, and `harmonic_conjunction_bodies`/`disharmonic_conjunction_bodies` could overlap or name a body absent from `bodies.fast ∪ bodies.slow` — all syntactically valid, all silently accepted.
  evidence: Flagged independently by two of three reviewers. Real, but adding it means deciding exactly what "contradictory" means for each pair (e.g. is a body in both `bodies.fast` and `bodies.slow` an error, or is the union just informational?) — a design call beyond this story's frozen scope (orb-range validation only), better made once a real consumer (Epic 2+) defines what breaks if these are wrong.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-one-home-for-every-astronomical-tuning-value.md`
  summary: `house_system.name` accepts any non-empty string; nothing checks it against `"placidus"`, the only value defined anywhere in the planning artifacts.
  evidence: A typo (`"placidis"`) or garbage value loads successfully and would only surface when a future story tries to use it. Deliberately not locked to an enum of one value now, since that decision (is a second house system ever expected, or is this permanently fixed?) belongs to whoever actually adds a second consumer.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-one-home-for-every-astronomical-tuning-value.md`
  summary: `version` in `data/computation.toml` accepts zero or negative integers; nothing enforces it as a genuine, monotonically-meaningful edit counter.
  evidence: Minor — the file's own comment describes it as "bumped by hand on every data edit," but nothing currently reads or compares `version` across loads, so an invalid value has no observable effect yet.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-6-a-conformance-harness-that-runs-before-there-is-anything-to-conform.md`
  summary: CI now runs on every push/PR, but is deliberately not wired as a required check blocking `render.yaml`'s auto-deploy — a passing commit with a failing test still deploys.
  evidence: That wiring needs both GitHub branch protection (a required-status-check rule) and, since Render deploys straight from a git push rather than reacting to a GitHub Actions run, either a Render deploy hook gated on CI success or moving off `autoDeployTrigger: commit`. A real decision with real trade-offs (slower deploys, single-operator-project overhead), not a default to fall into as a side effect of adding CI.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-6-a-conformance-harness-that-runs-before-there-is-anything-to-conform.md`
  summary: `compare()`'s recursive dict diff uses strict `==` with no documented convention for bridging `Decimal`-typed computed output against the TOML-string-typed `expected` values the fixtures README specifies (e.g. `longitude = "312.83"`).
  evidence: Real fixtures don't exist yet, so this has never been exercised end-to-end. Whoever writes `compute_output_for()` for Story 1.7/Epic 2 needs to either format `Decimal` values into matching strings before returning them, or `compare()` needs a numeric-aware equality path — a decision that belongs with the function that actually produces the values, not invented speculatively here.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-6-a-conformance-harness-that-runs-before-there-is-anything-to-conform.md`
  summary: `discover_fixtures()` globs only the top level of `tests/conformance/fixtures/` (non-recursive), and nothing in the fixture format supports marking a fixture as known-failing/incomplete (no `xfail`-style flag).
  evidence: Fine for the "at least three transcribed charts" BUILD-ORDER.md expects from Story 1.7, but worth revisiting once the fixture set grows large enough to want subdirectories, or once fixtures start landing incrementally against partially-implemented Epic 2/3 computation and a full-red CI stops being useful signal.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-resolve-a-birthplace-to-coordinates-and-the-offset-in-force.md`
  summary: Story 2.3 (Create a Client) needs a way to turn a chosen `PlaceCandidate` back into a `ResolvedPlace` once Francesco picks one from an ambiguous match — no port method exists for "confirm this candidate," and `PlaceCandidate` carries no stable identifier (e.g. an OSM id), so two candidates sharing the same `display_name` cannot currently be told apart on re-resolution.
  evidence: `Geocoder.resolve()` (`shell/ports/geocoder.py`) returns `list[PlaceCandidate]` on an ambiguous match and stops there by this story's own scope boundary ("no HTTP route or form for candidate selection -- Story 2.3"). Surfaced by review (blind-hunter layer): the mechanism for completing that round trip was never designed, only the data shape for presenting candidates. Story 2.3's Client-creation flow needs to either add a `resolve_candidate()`-style port method or extend `PlaceCandidate` with something a repeat call can key on unambiguously.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-compute-a-natal-chart-as-a-pure-function.md`
  summary: Placidus house cusps are mathematically undefined/degenerate near the poles (roughly latitude >= 66.5 degrees), and `core/ephemeris/chart.py`'s `_house_for_longitude()` currently raises a bare `AssertionError` -- not a typed, user-facing error -- if a birthplace ever lands there.
  evidence: Flagged by two review layers (edge-case-hunter and blind-hunter). No planning artifact (PRD, epics, architecture) addresses extreme-latitude births, and the codebase's own convention elsewhere is to fail loudly with a typed domain error (`PlaceResolutionError`, `EphemerisIntegrityError`, `ComputationConfigError`), not a bare assertion. Whether to reject such birthplaces explicitly (likely at Story 2.3's Client-creation validation layer) or handle them some other way is a product decision beyond this story's scope.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-compute-a-natal-chart-as-a-pure-function.md`
  summary: The three Epic-3 month/transit fixtures (`two-lunations-month.toml`, `no-lunations-month.toml`, `retrograde-station-month.toml`, all anchored on `near-midnight-birth`'s chart) were not checked for a stray `chiron` entry inherited from the same anchor chart the way the four natal fixtures were.
  evidence: Flagged by blind-hunter. Harmless today -- `compute_output_for()` still raises `NotImplementedError` for all three, so their content is inert -- but whoever wires in Epic 3's transit computation should check these three for the same Chiron cleanup story 2.2 did on the natal fixtures.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-compute-a-natal-chart-as-a-pure-function.md`
  summary: Two conformance-fixture value corrections made during this story (`dst-fallback-before.toml`'s house 3/9 cusps, `near-midnight-birth.toml`'s Neptune retrograde flag) were validated using this story's own new computation rather than an independent Astro.com re-check, so those two specific data points currently only prove the implementation agrees with itself.
  evidence: Flagged independently by blind-hunter and verification-gap, and already noted inline in both fixtures' own `correction_2026_08_16` field at the time of correction (human-approved, not an oversight) -- a systematic bug that reproduces the same wrong value on every run would pass undetected at exactly these two points. Re-verify against a live Astro.com session when one is available.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-compute-a-natal-chart-as-a-pure-function.md`
  summary: `PlanetPosition.house`/`sign` and `Aspect.applying` are only checked for type/bounds validity in unit tests (any of the 12 signs, any of the 12 houses, any bool) -- their actual correctness against real reference data is unverified, since none of the four conformance fixtures' `expected` tables carry `sign`, `house`, or `applying` fields.
  evidence: Confirmed by verification-gap by grepping all four fixtures for these keys (no matches) and reading the relevant unit tests directly (`tests/test_natal_chart.py`'s assertions are membership/bounds checks, not known-correct-value checks). A sign-table transposition, a 0-degree-crossing house misassignment, or an inverted applying/separating sign would all currently ship undetected.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-create-a-client-or-fail-visibly.md`
  summary: The engine built in `create_app()` (shell/http/app.py) has no dispose()/shutdown hook and no pool_pre_ping tuning for the Render free-tier deployment.
  evidence: Story 2.3 introduces the app's first live SQLAlchemy engine; migrations/env.py's own engine is disposed after use, but the app's long-lived one has no equivalent teardown or connection-health tuning.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-create-a-client-or-fail-visibly.md`
  summary: Client.name, Client.iana_zone and StoredNatalChart.computation_config_content_hash are unbounded String/str columns with no length constraint beyond the new request body-size cap.
  evidence: Surfaced by blind-hunter review of Story 2.3's diff; no upper bound exists at the schema or form-validation level for these fields.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-create-a-client-or-fail-visibly.md`
  summary: Geocoder.resolve()'s Protocol docstring in shell/ports/geocoder.py omits the ValueError it raises for a tz-aware birth_local_time, the same gap patched on the new sibling resolve_candidate() in this story.
  evidence: Noticed while reviewing Story 2.3's new resolve_candidate() docstring against its implementation; the pre-existing resolve() method has the identical undocumented ValueError path.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-assemble-the-four-domain-profiles.md`
  summary: The twelve-sign zodiac tuple is now duplicated a fourth time across the test suite, with no shared constant.
  evidence: Surfaced by blind-hunter review of Story 2.5's diff. Independent copies already existed in core/domains/rulers.py (`_ZODIAC_SIGNS`), tests/test_house_rulers.py, and tests/test_natal_chart.py (as a frozenset); tests/test_domain_profiles.py adds a fourth. This story followed the exact pattern already established by Story 2.4's test file rather than introducing a new one, so fixing it means a cross-cutting extraction touching already-`done` test files — out of this story's scope.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-6-see-the-chart-wheel-and-check-it-against-astro-com.md`
  summary: `GET /clients/{client_id}/chart`'s `StoredNatalChart` lookup takes `.first()` with no ordering, which will become ambiguous once a Client can have more than one stored chart.
  evidence: Surfaced by edge-case-hunter and blind-hunter review of Story 2.6's diff. Today `create_client_with_chart()` is the only writer and runs exactly once per Client, so exactly one row ever exists and `.first()` is harmless. Story 2.7 ("Correct birth data, and know what it invalidates") introduces superseded charts retained alongside the current one for the same `client_id` — at that point this route must pick the non-superseded chart explicitly (or order by recency) rather than an arbitrary row.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-correct-birth-data-and-know-what-it-invalidates.md`
  summary: The "at most one current (`superseded_at IS NULL`) chart per Client" invariant is enforced only in application code, with no DB-level constraint and no handling if it's ever violated.
  evidence: Surfaced by blind-hunter, edge-case-hunter and verification-gap review of Story 2.7's diff. `correct_client_and_chart()`'s `select(...).where(superseded_at.is_(None)).one()` raises an unhandled `NoResultFound`/`MultipleResultsFound` (bare 500) if the invariant is ever broken, and `chart.py`'s `.first()` on the same predicate would silently serve an arbitrary chart instead. Two concurrent correction requests for the same Client (no `SELECT ... FOR UPDATE` or unique partial index on `natal_chart(client_id) WHERE superseded_at IS NULL`) could each read the same "current" row and both commit, leaving two current rows. Low real-world likelihood for this single-operator tool, and fixing it needs a Postgres-specific partial unique index that can't be verified against a real Postgres instance in this environment (no local Postgres was reachable during this story's implementation) — worth a deliberate follow-up rather than an unverified patch.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-correct-birth-data-and-know-what-it-invalidates.md`
  summary: A superseded `StoredNatalChart` row keeps no snapshot of the birth_date/birth_time/birthplace that produced it, since `correct_client_and_chart()` overwrites those fields on the `Client` row in place.
  evidence: Surfaced by blind-hunter review of Story 2.7's diff. The epic's AC only requires the superseded chart row itself to "remain readable and stay associated with" whatever was generated against it — satisfied here — but once a correction lands, there is no way to recover *what birth data* produced the superseded chart from the DB alone (only the current `Client` row's values are stored). Matters if this project ever needs to explain "why does this old chart differ from the current one."

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-correct-birth-data-and-know-what-it-invalidates.md`
  summary: A correction has no audit trail (who/when/why) beyond the new chart row's implicit `superseded_at` timestamp on the old one.
  evidence: Surfaced by blind-hunter review of Story 2.7's diff. Low value today (single-operator tool, "who" is always Francesco), but "why a correction was made" is unrecoverable, and would matter if this tool is ever used by more than one operator.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-correct-birth-data-and-know-what-it-invalidates.md`
  summary: The correction warning screen shows only the proposed new values, not a diff against the Client's current stored values.
  evidence: Surfaced by blind-hunter review of Story 2.7's diff. The AC requires warning that prior Reports were generated against the previous chart, which the warning text does — but a reviewer confirming a correction currently has no side-by-side to check exactly which fields are changing before applying it.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-correct-birth-data-and-know-what-it-invalidates.md`
  summary: No route or view lets Francesco see a Client's correction history; superseded chart rows are retained but only reachable via direct DB access.
  evidence: Surfaced by blind-hunter review of Story 2.7's diff. The epic AC only requires superseded charts to stay queryable, which they do — but nothing in the app currently queries or displays them.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-correct-birth-data-and-know-what-it-invalidates.md`
  summary: The correction's `confirmed=1` gate isn't bound to a specific prior warning response (no token/nonce), so a request could submit `confirmed=1` on its very first POST and skip ever seeing the rendered warning.
  evidence: Surfaced by blind-hunter review of Story 2.7's diff. Low risk today — this is a single-operator, authenticated-only tool, not a multi-party workflow — but worth hardening if this route is ever exposed to more than one trusted operator.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-correct-birth-data-and-know-what-it-invalidates.md`
  summary: `geocoder.resolve()`/`resolve_candidate()` or `compute_natal_chart()` raising an exception outside the explicitly caught types (`PlaceResolutionError`, `ValueError`, `EphemerisIntegrityError`) surfaces as a bare 500 rather than a rendered error.
  evidence: Surfaced by edge-case-hunter review of Story 2.7's diff. Not caused by this story: `shell/http/routes/clients.py`'s new `/clients/{id}/edit` POST handler is a field-for-field mirror of the pre-existing `POST /clients` create handler's exception handling, confirmed by verification-gap review — the same gap already exists in Story 2.3's create route.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-correct-birth-data-and-know-what-it-invalidates.md`
  summary: `POST /clients/{client_id}/edit` has no CSRF protection beyond cookie-based session auth.
  evidence: Surfaced by blind-hunter review of Story 2.7's diff. Not caused by this story: identical to the pre-existing `POST /clients` create route, which has never had CSRF protection either.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-8-delete-a-client-and-everything-derived-from-them.md`
  summary: No CSRF protection exists anywhere in this app, and the new delete route inherits that gap for an action that, unlike create/edit, is irreversible.
  evidence: The delete confirmation form's only payload is a static hidden `confirmed=1` field, and auth is a bare session cookie (`shell/http/auth.py`) with no CSRF token anywhere in the codebase. An attacker page can auto-submit the delete form from a logged-in operator's browser with no user interaction beyond a page visit, permanently deleting a Client. This predates Story 2.8 (create/edit share the same gap) but deletion's irreversibility raises the stakes.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-8-delete-a-client-and-everything-derived-from-them.md`
  summary: The cascade-invariant test (`tests/test_client_store.py::test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant`) only catches an uncovered Client-referencing table if that table's model module has already been imported into `SQLModel.metadata` when the test runs.
  evidence: `tests/conftest.py` does not import every model module, and `test_client_store.py` itself only imports `shell.adapters.postgres.client`. Running the full suite together reliably registers every model (each new feature's own HTTP test file transitively imports `shell.http.app`, which imports all routers/models), but running `tests/test_client_store.py` in isolation could miss a table defined in a module nothing else in that invocation imports -- the invariant would pass vacuously despite a real gap.

- source_spec: `_bmad-output/implementation-artifacts/spec-epic-2-retro-place-cache-warn-confirm-fix.md`
  summary: `create_client` (Story 2.3) has the same-shaped `PLACE_CACHE` rollback gap as `correct_client` had, but for a different trigger, and this fix's scope did not touch it.
  evidence: `create_client` (`shell/http/routes/clients.py`) resolves the birthplace, then calls `compute_natal_chart()`, then persists and commits once at the very end -- it has no warn/confirm split to bisect the way `correct_client` did. If a genuinely new place resolves successfully (writing through to `PLACE_CACHE`) but `compute_natal_chart()` then raises `ValueError`/`EphemerisIntegrityError`, the route returns a 422 without ever calling `session.commit()`; `get_session`'s per-request session closes uncommitted, rolling back that fresh place's cache write along with everything else pending on the session. A resubmission of the same birthplace therefore re-hits Nominatim live instead of getting a cache hit. Named explicitly out of scope by this fix's own Boundaries ("`create_client` ... is out of scope -- do not touch it") because the retro's action items 1-2 name only `correct_client` and its test fixture.

- source_spec: `_bmad-output/implementation-artifacts/spec-epic-2-retro-place-cache-warn-confirm-fix.md`
  summary: `tests/test_http_client_correction.py`'s `db_session` fixture and each simulated HTTP request's own fresh per-request session are distinct `Session` objects sharing one `StaticPool` SQLite connection with no explicit coordination between them.
  evidence: Surfaced by edge-case-hunter review of this fix's diff. Every current use in the file is sequential (seed-then-commit before any HTTP call; a read via `db_session` between two HTTP calls, never interleaved with an open write on the other session), so nothing in the current suite is actually affected -- verified directly: every place that reads a mutated object's attributes via `db_session` after an HTTP-driven write already calls `db_session.refresh(...)` first (3 occurrences), and the only other `db_session` usage is a fresh `select()` query, which is safe regardless of session identity. Worth a comment on the `engine` fixture (or a documented convention) if a future test ever needs genuinely concurrent/interleaved access across the two sessions, since SQLite's single-writer semantics on a shared connection could then produce order-dependent flakiness.

- source_spec: `_bmad-output/implementation-artifacts/spec-epic-2-retro-place-cache-warn-confirm-fix.md`
  summary: No test exercises two back-to-back unconfirmed warning-step submissions for the same not-yet-cached place (which would call `store_resolved_place()` twice for the same normalized query text).
  evidence: Surfaced by blind-hunter review of this fix's diff. `store_resolved_place()`'s own docstring states it "silently no-ops on a duplicate insert" via its nested `SAVEPOINT` + caught `IntegrityError` -- the underlying mechanism is already designed to be safe under this scenario -- but nothing exercises that path end-to-end through `correct_client`'s now-earlier commit point to confirm a second warning submission for the same new place doesn't raise or behave unexpectedly.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-find-every-transit-to-natal-aspect-and-the-exact-moment-it-perfects.md`
  summary: The coarse-grid-plus-bisection scan's "no orb window is ever hidden inside a grid step" correctness guarantee is asserted only in `core/transits/aspects.py`'s module docstring, not enforced or tested against future config changes (a tighter transit orb, or a faster body added to `config.bodies`).
  evidence: `_GRID_STEP` (6 hours) and `_BISECTION_ITERATIONS` (40) are hardcoded constants sized against today's fixed body set and orb range (Mercury's ~2.2 deg/day, orb 1.5-2.5 deg). Nothing recomputes or asserts this margin against `ComputationConfig` at call time, so a future data/computation.toml edit widening the permitted body/orb ranges could silently violate the assumption with no test catching it.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-find-every-transit-to-natal-aspect-and-the-exact-moment-it-perfects.md`
  summary: `TransitAspectEvent` carries no orb/degree-of-separation value, only timestamps, so any consumer wanting "how close is this aspect" (e.g. a future Report Payload or day-list renderer) must independently recompute it via the low-level position helpers.
  evidence: `tests/test_conformance.py`'s `_transit_events_for_month_fixture()` already has to do exactly this recomputation to check fixture conformance, duplicating logic that arguably belongs on the type -- unlike the natal `Aspect` type, which carries its own `orb` field.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-find-every-transit-to-natal-aspect-and-the-exact-moment-it-perfects.md`
  summary: The `correction_YYYY_MM_DD` free-form-prose field this story added (again) to two conformance fixtures has no structural mechanism to keep a correction consistent with the fixture's own `source`/`note` fields over time.
  evidence: Two fixtures now each carry a `correction_2026_08_18` key documenting a transcription fix, following the precedent `correction_2026_08_16` already set in `near-midnight-birth.toml`. As more corrections accumulate across fixtures there is no validation that a correction's claims don't drift out of sync with the original `source` prose it's amending.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-date-every-station-and-know-what-is-standing-retrograde.md`
  summary: `find_stations()`'s coarse-grid scan never records a turn whose speed reads exactly zero on the very first grid sample (`speeds[0]`, i.e. exactly at `month_start_utc`), and two consecutive grid samples both reading exactly zero near a real turn could double-record it as two Stations instead of one.
  evidence: Surfaced by edge-case-hunter and blind-hunter review of this story's diff. The sign-change loop in `core/transits/stations.py` only inspects transitions between consecutive samples (`s0`/`s1`), never treating `speeds[0]` itself as a candidate turn, and the `s1 == 0` branch has no dedup guard against an adjacent grid point also reading exactly zero. Real ephemeris speed is a continuous float, so hitting exactly `0.0` on a grid sample is astronomically unlikely in practice, but the logic gap is real and untested.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-date-every-station-and-know-what-is-standing-retrograde.md`
  summary: `_require_utc_interval` (in both `core/transits/stations.py` and, before it, `core/transits/aspects.py`) accepts any `tzinfo` whose *current* `utcoffset()` happens to equal zero, not strictly `datetime.timezone.utc` -- a DST-observing zone momentarily at UTC+0 would pass the check silently.
  evidence: Surfaced by edge-case-hunter review of this story's diff, but the check itself is Story 3.2 mirroring a pattern `core/transits/aspects.py` already established in Story 3.1 -- not something this story introduced. A bisected instant computed against such a boundary would carry a wrong UTC offset without any error.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-date-every-station-and-know-what-is-standing-retrograde.md`
  summary: Neither `find_stations()` nor `find_transit_aspects()` dedupes a body name that appears in both `config.bodies.fast` and `.slow`, or repeated within one list -- such a config would silently scan (and emit duplicate records for) the same body twice.
  evidence: Surfaced by edge-case-hunter and blind-hunter review of this story's diff, but `find_transit_aspects()` (Story 3.1) already has the identical gap -- `find_stations()` only inherits it by scanning `tuple(config.bodies.fast) + tuple(config.bodies.slow)` the same way.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-date-every-station-and-know-what-is-standing-retrograde.md`
  summary: The `retrograde-station-month.toml` fixture's `correction_2026_08_18` (Mars/Jupiter) and this story's new `correction_2026_08_19` (Mercury's station bracket longitude) both verify the transcribed Astro.com value only against this same codebase's own real computation, not an independent second source -- a circularity risk if the computation itself were ever subtly wrong in a way that happens to agree with a plausible-looking "correction."
  evidence: Surfaced by blind-hunter review of this story's diff. `correction_2026_08_19`'s own text cites "Story 3.2's real find_stations() computation independently locates Mercury's actual Dec 2022 station at 294.3567 degrees" as the justification for changing the fixture -- the same self-referential verification method `correction_2026_08_18` already used and passed review with in Story 3.1.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-locate-the-month-s-new-and-full-moons.md`
  summary: `find_lunations()`'s coarse-grid scan never records a crossing whose signed offset reads exactly zero on the very first grid sample (`offsets[0]`, i.e. exactly at `month_start_utc`) -- the same class of gap already deferred for `find_stations()` in Story 3.2.
  evidence: Surfaced by blind-hunter review of this story's diff. The sign-change loop in `core/transits/lunations.py` only inspects transitions between consecutive samples (`d0`/`d1`); when `d0 == 0` the `elif d0 != 0 and ...` branch is skipped, so a Lunation landing exactly on `month_start_utc` is silently dropped. Traced (not just suspected): this is the identical structural gap already deferred for `core/transits/stations.py`'s `speeds[0]` case, inherited here by the Code Map's own "mirror verbatim" instruction from `core/transits/ingresses.py`, which has the same gap untested. Astronomically unlikely to land exactly on a grid boundary in practice, but the logic gap is real across all of `aspects.py`/`stations.py`/`ingresses.py`/`lunations.py`.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-5-start-a-month-s-computation-and-watch-it-finish.md`
  summary: `ReportRun` never pins which `StoredNatalChart` version a run was driven against -- `natal_ready`'s deserialized chart is re-fetched as "whichever chart is currently non-superseded" on every `drive()` call, so a birth-data correction landing between `natal_ready` completing and `transits_ready` running (e.g. across a restart) would compute `transits_ready` against a different chart than the run implicitly started with.
  evidence: Surfaced by blind-hunter review of this story's diff. `shell/http/routes/report_runs.py::_drive_run` always calls `_current_chart(session, client.id)` fresh rather than reading a chart id recorded on `run` itself; no column exists to pin one. The realistic race window is tiny for a single-user tool (a correction is a separate, deliberate form submission), and this pairs naturally with Story 3.8's freeze/reproducibility work rather than warranting a schema change here.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-5-start-a-month-s-computation-and-watch-it-finish.md`
  summary: Nothing stops two `ReportRun` rows from being created for the same `(client_id, month)` -- no uniqueness constraint at the schema or route level, and no decision recorded on whether duplicates should be allowed, deduplicated, or rejected.
  evidence: Surfaced by blind-hunter review of this story's diff. `migrations/versions/0005_report_run.py` indexes `client_id` alone; `POST /clients/{client_id}/report-runs` never checks for an existing run before inserting. Story 3.6+ (Payload assembly) will need to decide which run is "the" run for a client-month anyway, a natural point to resolve this.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-5-start-a-month-s-computation-and-watch-it-finish.md`
  summary: No concurrency control exists around `drive()` -- two concurrent requests against the same `ReportRun` (two browser tabs polling, a retried HTTP request) could both read the same `run.stage` and race to run the same "next" stage and write `run.transit_events`/`run.stage`.
  evidence: Surfaced by blind-hunter review of this story's diff. No version column, row lock (`SELECT ... FOR UPDATE`), or test covers concurrent polling of the same run. Low practical impact for a single-user tool with one browser tab per run, but the gap is real.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-5-start-a-month-s-computation-and-watch-it-finish.md`
  summary: `ReportRun.month`'s `"YYYY-MM"` format is validated only at the HTTP boundary (`_MONTH_PATTERN` in `shell/http/routes/report_runs.py`), not on the model or in `drive()` itself -- a malformed month reaching `client_month_interval_utc` any other way raises a deterministic, permanent `ValueError` that `with_backoff` would still retry 3 times as if it were transient, since `with_backoff` never distinguishes permanent from transient failures.
  evidence: Surfaced by blind-hunter review of this story's diff. The test suite's own direct `ReportRun(client_id=..., month="2026-01")` construction shows the model itself accepts any string. Today the only creation path is the HTTP route, which does validate first, so this is defense-in-depth rather than a reachable bug.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-5-start-a-month-s-computation-and-watch-it-finish.md`
  summary: `deserialize_natal_chart` assumes the JSON shape `_serialize` wrote exactly matches the current dataclass fields, with no defensive handling -- a future migration or field rename would raise a raw `KeyError`/`TypeError` that `shell/http/routes/report_runs.py::_drive_run` doesn't translate, surfacing as an unhandled 500 instead of the router's otherwise-consistent explicit 404/422 handling.
  evidence: Surfaced by blind-hunter review of this story's diff. Not reachable through any normal usage path today (both functions are maintained together in `shell/adapters/postgres/client.py`), but the gap would bite the moment a future story changes either shape without the other.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-5-start-a-month-s-computation-and-watch-it-finish.md`
  summary: `client_month_interval_utc`'s docstring claims PEP 495 fold/gap handling for a month boundary landing on a DST transition, but no test actually constructs such a boundary -- `test_a_dst_observing_zone_never_raises_across_a_full_year` only proves no month in a full year raises, not that a genuine fold/gap resolves correctly, since America/Chicago's real transitions land on a Sunday in March/November at 2am local, never on the 1st of a month at midnight.
  evidence: Surfaced by blind-hunter review of this story's diff. Verifying the claim meaningfully needs either a zone with an unusual month-boundary transition or a contrived `fold=`-based test, neither of which this story's fixtures currently exercise.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-5-start-a-month-s-computation-and-watch-it-finish.md`
  summary: No mutating POST route in the application (`/clients`, `/clients/{id}/edit`, `/clients/{id}/delete`, and now `/clients/{id}/report-runs`) carries CSRF protection -- authentication is session-cookie-only, the classic CSRF shape.
  evidence: Surfaced by blind-hunter review of this story's diff, but confirmed pre-existing: `shell/http/routes/clients.py`'s `create_client`/`correct_client`/`delete_client` already follow the identical session-cookie-plus-form-body pattern with no token check, predating this story. Grep for `csrf`/`CSRF` across `shell/` returns nothing.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-6-assemble-the-report-payload-each-section-needs.md`
  summary: `data/sections.toml`'s `aspect_natal_points` values are validated only as "a list of strings" -- a typo like `"venuz"` loads without error and silently produces a filter that can never match, with no load-time warning.
  evidence: Surfaced by blind-hunter review of this story's diff. Unlike `domain_profile`/`house_bodies`/`aspect_bodies`, which `shell/sections.py` checks against closed enums, `_read_optional_string_tuple` accepts any string. The shipped file's values are all correct today; this only bites a future hand-edit.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-6-assemble-the-report-payload-each-section-needs.md`
  summary: `shell/sections.py::load_sections_config` never checks for stray extra top-level keys in `data/sections.toml` (only `[sections]`'s own keys and each `[sections.*]` table's keys are checked) -- an unrecognized top-level key is silently ignored.
  evidence: Surfaced by blind-hunter review of this story's diff. The same gap exists in `shell/computation.py`, which this module deliberately mirrors per the story's Code Map -- fixing it only here would diverge from that precedent rather than close the gap consistently.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-6-assemble-the-report-payload-each-section-needs.md`
  summary: `shell/sections.py::_read_table`'s error message (`"[{name}] is required."`) fires identically whether a table key is missing or present with the wrong type, misleading whoever is debugging a malformed `data/sections.toml`.
  evidence: Surfaced by blind-hunter review of this story's diff. Inherited verbatim from `shell/computation.py`'s own `_read_table`, which has the identical ambiguity -- same reasoning as the sibling top-level-keys gap above: a shared fix belongs in the mirrored module, not a one-off deviation here.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-6-assemble-the-report-payload-each-section-needs.md`
  summary: A Section can set `house_bodies`/`aspect_bodies` with no corresponding `houses`/`aspect_natal_points` key -- the loader accepts it, but at runtime the body selector becomes dead configuration (the empty `houses`/`aspect_natal_points` check short-circuits `_matches_ingress`/`_matches_aspect` to `False` before the body selector is ever consulted), with no load-time warning.
  evidence: Surfaced by blind-hunter review of this story's diff. Harmless today (no Section in the shipped file does this), but a future hand-edit could set one field expecting it to matter and be silently wrong.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-6-assemble-the-report-payload-each-section-needs.md`
  summary: A domain Section (`amore`/`lavoro`/`denaro`/`benessere`) with every filter field empty/false and `include_all_events=false` loads successfully and yields a `SectionPayload` carrying only its `profile` with every event list empty -- almost certainly a configuration mistake, but nothing flags it at load time.
  evidence: Surfaced by blind-hunter review of this story's diff. `shell/sections.py` has no "at least one filter is active" check for a non-`include_all_events` Section. The shipped file's five domain-adjacent Sections are all correctly populated today; this only bites a future hand-edit that empties one by accident.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-7-project-the-two-day-lists-by-code-so-a-day-cannot-be-misfiled.md`
  summary: Nothing validates that `data/computation.toml`'s `[harmonic]` table keeps `harmonic_aspects`/`disharmonic_aspects` and `harmonic_conjunction_bodies`/`disharmonic_conjunction_bodies` disjoint from each other.
  evidence: Surfaced by blind-hunter review of this story's diff. `core/payload/day_lists.py::_classify_aspect()` checks the harmonic branch first, so a future hand-edit that lists the same aspect or body in both sets would silently resolve it as harmonic with no error -- exactly the kind of misfiling this story exists to prevent, but the fix belongs in the `[harmonic]` table's own loader/validation (`shell/computation.py`, Story 1.5's home), not in this story's pure projection function.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-8-freeze-the-payload-so-any-report-can-be-reproduced-years-later.md`
  summary: `tests/test_report_payload_store.py` and every other SQLite-stands-in-for-Postgres test in this repo run against a plain `create_engine("sqlite://")`, which never enforces foreign keys (`PRAGMA foreign_keys=ON` is not set anywhere) -- so no test can actually prove `delete_client_and_derived()`'s deletion order (`ReportPayload` before `ReportRun`, since the former's `report_run_id` FKs to the latter) is load-bearing; the tests would pass identically with the order reversed.
  evidence: Surfaced by blind-hunter review of this story's diff. Pre-existing gap in the whole test suite's Postgres stand-in, not introduced by this story -- every prior story's SQLite fixture has the same blind spot. A fix belongs in the shared test fixture/conftest, not a one-off in this story's test file.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-8-freeze-the-payload-so-any-report-can-be-reproduced-years-later.md`
  summary: `shell/runner/driver.py`'s stage functions (including the new `_run_payload_ready`) always recompute against whatever `ComputationConfig` is live in the process right now, never the version a Client's `StoredNatalChart` was originally computed under -- so if `data/computation.toml` changes between a chart's computation and a later report run, `resolve_house_rulers`/`assemble_domain_profiles`/`find_transit_aspects` etc. silently mix config versions with no drift check or warning.
  evidence: Surfaced by blind-hunter review of this story's diff, but the pattern predates this story -- `_run_transits_ready` (Story 3.5) already has the identical exposure. Worth a dedicated look across the whole runner, not a one-story fix.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-8-freeze-the-payload-so-any-report-can-be-reproduced-years-later.md`
  summary: No test drives a stage function's `with_backoff` retry path specifically for `payload_ready` to confirm a transient failure after `store_report_payload()`'s `flush()` (but before `drive()`'s outer `commit()`) cannot leave more than one pending/flushed `ReportPayload` row in the session across retries.
  evidence: Surfaced by blind-hunter review of this story's diff. The unique index added to `report_payload.report_run_id` (this story's patch) turns any such duplicate into a loud `IntegrityError` rather than a silent double-write, which meaningfully narrows the risk -- but whether `with_backoff` rolls back the session between retries is still unverified. Worth a focused test once `with_backoff`'s own contract is checked, not blocking this story.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-9-read-the-facts-behind-a-month-entry-by-entry.md`
  summary: `report_run_poll.html`'s "View Payload" link is gated on `run.stage == "payload_ready"` by exact equality, so once a future story appends a stage after `payload_ready` to `_STAGE_SEQUENCE` (e.g. an Epic 4+ Report-generation stage), a run that has advanced past `payload_ready` would lose the link even though its `ReportPayload` still exists and is still viewable.
  evidence: Surfaced by blind-hunter review of this story's diff. Harmless today -- `payload_ready` is still the last named stage in `shell/runner/driver.py::_STAGE_SEQUENCE`, so exact equality and "payload_ready or later" are currently identical. The fix (checking against the stage's position rather than exact identity, or an explicit "payload exists" flag) belongs with whichever future story is the first to add a stage after `payload_ready`.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-9-read-the-facts-behind-a-month-entry-by-entry.md`
  summary: `GET /report-runs/{run_id}/payload` sets no `Cache-Control`/no-store header, so a Client's natal placements and transit data could be retained in browser/proxy disk cache despite the route being session-authenticated.
  evidence: Surfaced by blind-hunter review of this story's diff. Not specific to this route -- every authenticated view in `shell/http/` (chart wheel, client edit, the poll view itself) has the identical gap; none of them sets cache-control headers today. Worth a single fix applied uniformly (e.g. middleware-level `Cache-Control: no-store` on every authenticated response) rather than a one-off in this story's route.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-1-write-the-style-guide.md`
  summary: The Style Guide gives no register guidance for how prose should acknowledge month-to-month continuity or change (still-active/tightened/resolved/new).
  evidence: `epic-4-context.md` treats the ReportTheme comparison as central to avoiding repetition ("nothing significant changed" is computed, not judged), and Story 4.7 owns "write this month as a continuation, not a reprint" — but FR-30's minimum content list for the Style Guide never mentions continuity, so this was correctly out of this story's frozen scope. Sections 1 and 8 are natural homes for such guidance once Story 4.4/4.7 exist to inform it.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-1-write-the-style-guide.md`
  summary: The Style Guide never describes the Generator's actual output contract — a per-sentence cited structure where each sentence carries the Payload entry IDs it rests on, and an uncited sentence is a Gate violation.
  evidence: `epic-4-context.md`'s Technical Decisions fix this structure and note it is "enforced in Epic 5." §4 of the guide discusses traceability only as a general prose obligation. This is Story 4.5's prompt-engineering concern (translating the guide's register rules into the structured contract), not this story's register-content scope.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-1-write-the-style-guide.md`
  summary: The Style Guide never references the PRD's own claim-density counter-metric (SM-C1) or gives any numeric per-Section target for claim/date anchoring.
  evidence: SM-C1 measures "Astronomical Claims per Report, and the share of Sections anchored to a date" as the PRD's chosen counter to the vagueness failure mode §3 spends most of its space warning against, but FR-30's minimum content list for the guide is qualitative only — adding a numeric target is a product-metrics decision beyond this story's frozen scope.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-1-write-the-style-guide.md`
  summary: No per-Section length or sentence/paragraph-count budget is specified anywhere in the guide.
  evidence: The Report presumably feeds a fixed UI/PDF layout, but FR-30's minimum content list doesn't require a length budget and none of the planning artifacts specify one yet — worth resolving once Story 4.5/4.6's rendering shape is concrete.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-1-write-the-style-guide.md`
  summary: The Style Guide gives no guidance for the sparse- or empty-Payload case (a month with few or no entries in a given Section's domain).
  evidence: Not part of FR-30's minimum content list; this is closer to a Story 4.5 prompt-engineering concern (how the Generator behaves given thin input) than a register-content question, but it's a real gap a prompt author will hit.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-1-write-the-style-guide.md`
  summary: The Style Guide gives no guidance on cross-Section consistency (e.g. Section 1's overview restating Sections 2–5's specific claims, or a transit's caption repeated verbatim between a prose Section and a day-list entry).
  evidence: Not part of FR-30's minimum content list. Worth a pass once Story 4.5 generation exists and real output can be inspected for this failure mode.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-1-write-the-style-guide.md`
  summary: The `version: 1` marker in `data/style-guide.seed.md` is a bare, undelimited prose line, unlike sibling `data/computation.toml`/`data/sections.toml`'s `#`-comment-header-plus-`version = N` TOML convention with a loader-computed content hash for drift detection.
  evidence: The spec only required a marker "Story 4.2's seeding logic can read" (satisfied — it's plainly greppable), not a specific structured format. Story 4.2 should settle the exact parsing convention (and whether a content hash is needed) when it builds the seeding loader.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-1-write-the-style-guide.md`
  summary: The Style Guide gives no fixed Italian nomenclature for recurring astrological terms (house names, aspect names, "casa" vs. "domicilio," etc.), leaving terminology free to vary between Reports.
  evidence: §4 requires every claim to name "a planet, transit, or house" but nothing pins the Italian vocabulary for those terms consistently. Not part of FR-30's minimum content list; worth a glossary pass once real generated output surfaces actual inconsistencies.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-derive-a-reporttheme-from-a-payload.md`
  summary: `ReportTheme` carries no signal for Ingress events (a slow planet crossing into a new natal house), so Story 4.4's diffing cannot detect "a slow planet just changed houses" as a continuity event.
  evidence: AD-14 and this story's spec both scope `ReportTheme` to Aspects/Lunations/StandingRetrogrades only — a deliberate architecture-level boundary, not an oversight in this story. Worth revisiting once Story 4.4/4.7 show whether house-ingress continuity is something the eight Sections actually need to narrate.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-derive-a-reporttheme-from-a-payload.md`
  summary: `report_theme` has no composite index for "latest theme for a Client," and there's no documented plan for how Story 4.4 will fetch "this run's theme" and "the prior run's theme" for the same Client.
  evidence: Only single-column indexes exist (`client_id`, unique `report_run_id`) — fine for this story's write pattern, but Story 4.4's diffing needs exactly two comparable rows per Client and should settle whether that goes through `ReportRun` lookups first or a direct `report_theme` query before deciding if an index is actually needed.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-render-cited-sentences-into-prose-i-could-read-aloud.md`
  summary: The `draft_ready` stage's live Generator call runs synchronously inside the request/response cycle (`drive()` walks every registered stage in one call), with no request-level timeout — a slow or hanging Gemini call hangs the HTTP request itself, not just the poll cadence the driver's own design notes assumed.
  evidence: Blind Hunter review of this story's diff. `shell/runner/driver.py`'s own docstring already flags `draft_ready` as "the first stage with a live external call" and defers rate-ceiling sizing to Story 4.8, but a request-level timeout on the Gemini call is a distinct concern Story 4.8's own scope (10 RPM backoff sizing) doesn't obviously cover and should be confirmed in scope there or raised separately.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-render-cited-sentences-into-prose-i-could-read-aloud.md`
  summary: No test proves `with_backoff` actually retries a failing Generator call specifically, and nothing distinguishes a retryable failure (rate limiting) from a permanent one (bad API key, safety-filter rejection) — a permanent failure would retry uselessly instead of failing fast.
  evidence: Blind Hunter review. `draft_ready` reuses the generic `with_backoff` wrapper untested against a real `GenerationError`; Story 4.8 (rate-limit backoff) is the natural place to add both the retryable/permanent distinction and a `draft_ready`-specific retry test.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-render-cited-sentences-into-prose-i-could-read-aloud.md`
  summary: No failure state is surfaced anywhere when a stage's `with_backoff` retries are exhausted — `ReportRun` has no error field, and `report_run_poll.html` has no failure branch, so an exhausted run just looks like it's perpetually "processing."
  evidence: Blind Hunter review. Pre-existing gap in `ReportRun`/the poll template since Story 3.5 (applies to every stage, not just `draft_ready`), surfaced now because `draft_ready` is the first stage likely to fail for a reason Francesco can't fix by waiting (a bad Gemini key, a persistent safety-filter rejection).

- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-render-cited-sentences-into-prose-i-could-read-aloud.md`
  summary: `report_draft.html` shows no identifying context (Client name, month) and no navigation back to the poll page, Client, or Payload view — a bookmarked or shared draft URL gives no way to tell whose report it is.
  evidence: Blind Hunter review. Mirrors `report_payload.html`'s identical, pre-existing omission (Story 3.9) rather than a regression specific to this story — worth a single shared fix (e.g. a small header partial) across both report-run sub-views rather than a one-off patch to just the new one.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-render-cited-sentences-into-prose-i-could-read-aloud.md`
  summary: The "View Draft"/"View Payload" links on the poll page only appear on an exact `run.stage` match (`== "draft_ready"` / `== "payload_ready"`), so once later stages (`gate_passed`, `exported`) are registered, a fully-completed run will silently lose both links even though the draft and payload are still reachable at their URLs.
  evidence: Blind Hunter review. `report_run_poll.html`'s new "View Draft" link mirrors the pre-existing "View Payload" link's own exact-match pattern (Story 3.9) rather than introducing a new one — both need a shared "stage has reached or passed X" check once `gate_passed`/`exported` land, not a one-off fix to either link alone.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-7-write-this-month-as-a-continuation-not-a-reprint.md`
  summary: `shell/http/routes/report_runs.py::start_report_run()` never checks for an existing `ReportRun` before creating one, and no unique constraint exists on `(client_id, month)` — two runs can be created for the same Client and month, and `most_recent_prior_report_theme()`'s `ORDER BY ReportRun.month DESC LIMIT 1` would pick between them non-deterministically (row order is unspecified without a tiebreaker). User-visible consequence: a Report could silently narrate continuity ("still active"/"resolved") against the wrong sibling run's `ReportTheme` for that month, with no error and no way for Francesco to tell which of the two runs supplied it.
  evidence: Blind Hunter review of this story's diff. Pre-existing gap in Story 3.5's run-creation route, not introduced by this story, which only surfaced it because it's the first consumer that queries "the" ReportRun for a given client+month rather than one already known by id.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-7-write-this-month-as-a-continuation-not-a-reprint.md`
  summary: `ReportRun.month` (`shell/adapters/postgres/report_run.py`) is a bare `str` with no database-level format constraint — `"YYYY-MM"` is validated only at `shell/http/routes/report_runs.py::start_report_run()`'s HTTP boundary, so any other write path (a script, a future route, a migration backfill) could insert a malformed value that silently breaks `most_recent_prior_report_theme()`'s string-ordering assumption.
  evidence: Blind Hunter review of this story's re-derived diff. This new query is the first consumer whose *correctness* (not just display) depends on `ReportRun.month` always being zero-padded `"YYYY-MM"`; a CHECK constraint or a model-level validator would close this for good rather than relying on the one HTTP route being the only writer forever.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-8-absorb-a-rate-limit-without-my-involvement.md`
  summary: No locking or mutual exclusion around `drive()` means two overlapping HTTP requests (the poll route's own `hx-trigger="every 2s"` racing the start route, or two browser tabs) can call `drive()` on the same `ReportRun` concurrently, racing on `stage`/`stage_failure_count` writes and, now that `draft_ready`'s backoff can block a single request for up to ~18s, widening the window in which the "3 attempts per 18s = 10/min" ceiling reasoning could be exceeded by overlapping calls.
  evidence: Blind Hunter review. Pre-existing characteristic of `drive()`'s no-queue, poll-cadence-as-drain design (Story 3.5, AD-10) — not introduced by this story, which only makes the race window materially longer by giving `draft_ready` a real multi-second backoff schedule instead of the old ~0.1s one.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-8-absorb-a-rate-limit-without-my-involvement.md`
  summary: The poll route 404s instead of rendering a run's terminal-failure state if the Client's stored chart is superseded (Story 2.7) after the run already failed, because `_drive_run()` requires `_current_chart()` to find a non-superseded chart before `drive()` — and its own `failed_at` short-circuit — ever run.
  evidence: Blind Hunter review. Pre-existing coupling between `poll_report_run`/`_drive_run` and the Client's *current* chart (predates this story, applies to any run at any stage), not something Story 4.8 introduced — surfaced here because this story is the first to make "the poll page must always be able to show why a run stopped" an explicit product requirement.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-8-absorb-a-rate-limit-without-my-involvement.md`
  summary: Once `ReportRun.failed_at` is set, `drive()` treats the row as permanently terminal — nothing clears `failed_at`/`stage_failure_count`, and no route or documented workflow lets Francesco requeue a run after a since-resolved outage (an expired API key, a temporary Gemini incident). The only apparent recourse is starting an entirely new run for the same Client/month.
  evidence: Blind Hunter review. Story 4.8's own Acceptance Criteria stop at "marked failed and surfaced with the reason" — a retry/requeue affordance is a reasonable next step but was never part of this story's scope, and `4-9-build-against-the-generator-without-spending-quota`/Epic 5 are the more natural homes for revisiting this.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-define-what-counts-as-a-claim-as-versioned-data.md`
  summary: Several `signs` tokens (`cancro`, `leone`, `bilancia`, `vergine`, `ariete`) are common Italian words/homonyms outside astrology (illness, lion/surname, a scale, virgin, battering ram) — `is_claim()`'s plain substring match will misclassify a sentence using one of these ordinarily as a Claim, triggering an unnecessary Gate check/regeneration against the Payload.
  evidence: Blind Hunter review of this story's diff. Rooted in AD-8's closed-vocabulary design itself (a bare literal-token list, no disambiguation), which this story's frozen intent mirrors verbatim rather than something introduced by this story's code choices. Consequence is bounded (extra regeneration, never a missed unsafe claim), so it's a quality/cost concern for Story 5.2 or a future vocabulary revision, not a blocker here.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-define-what-counts-as-a-claim-as-versioned-data.md`
  summary: `is_claim()`'s `casa`+ordinal rule only checks that both tokens appear anywhere in the sentence, not that they're adjacent or grammatically related — e.g. "Sono tornato a casa: sei la seconda persona a saperlo." would false-positive as a Claim even though "seconda" has nothing to do with "casa".
  evidence: Blind Hunter review of this story's diff. This is exactly what the spec's Design Notes specified ("`casa_ordinals` is a Claim token only combined with the literal word `casa` in the same sentence") — a deliberate same-sentence heuristic chosen to avoid a dependency-parsing dependency, not a coding deviation. Same bounded-regeneration consequence as the sign-homonym finding above; worth revisiting together.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-define-what-counts-as-a-claim-as-versioned-data.md`
  summary: `retrogrado`/`stazionario` are matched as single literal strings with no handling of Italian gender/number agreement (`retrogradi`, `retrograda`, `stazionaria`, etc.) — a sentence like "I pianeti sono retrogradi questo mese" would silently fail to be classified as a Claim, a false *negative* that lets an unverified retrograde claim skip the Gate entirely once Story 5.2 lands.
  evidence: Blind Hunter review of this story's diff. AD-8 and the Story 5.1 AC name the vocabulary as bare words ("retrogrado", "stazionario") with no mention of grammatical inflection anywhere in the architecture or epics text, so literal single-token matching is the one coherent reading of the frozen intent, not an ambiguity this story's spec could have resolved differently. Highest-severity of the deferred findings — a real gap in the grounding guarantee, not just an availability cost — worth resolving before or alongside Story 5.2 (e.g. matching a stem/prefix, or listing inflected variants explicitly in `vocabulary.it.json`).

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-define-what-counts-as-a-claim-as-versioned-data.md`
  summary: `day_of_month_pattern` (`\b([1-9]|[12][0-9]|3[01])\b`) matches any bare number 1–31 regardless of context (ages, degrees, temperatures, counts), e.g. "Ho 15 anni" would be misclassified as a Claim.
  evidence: Blind Hunter review of this story's diff. Rooted in AD-8 naming "a day-of-month numeral" as a bare vocabulary category with no contextual qualifier specified anywhere in the architecture or epics text — the frozen intent gives one coherent reading (a plain numeral-range pattern), not a choice this story's spec made freely. Same bounded-regeneration consequence as the other false-positive findings above.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-check-every-claim-against-the-payload.md`
  summary: `_CASA_ORDINAL_TO_HOUSE` (`core/gate/run.py`) maps ordinary Italian words like `"prima"`/`"seconda"` to house numbers 1/2; combined with `is_claim()`'s same-sentence-only `casa`+ordinal proximity check (already deferred under Story 5.1), a mundane sentence containing both `casa` and an unrelated `"prima"`/`"seconda"` anywhere in it can be misclassified as a house Claim and then checked against a specific house number, producing a spurious `invented_fact`/`contradicted_fact` violation rather than just an unnecessary regeneration.
  evidence: Blind Hunter review of this story's diff. Builds directly on the pre-existing Story 5.1 `casa`+ordinal proximity gap (already logged above); Story 5.2 is the first place that turns the false classification into a specific numeric house comparison, so a later fix likely needs to touch both stories together.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-check-every-claim-against-the-payload.md`
  summary: `_asserted_retrograde()`/`_retrograde_facts()` (`core/gate/run.py`) treat the vocabulary's `retrogrado` and `stazionario` tokens as asserting the identical fact (`direction == "retrograde"` or a `standing_retrograde` entry) — a correct sentence describing a body's station turning *direct* (`stazionario` used for the turning-point moment, not the retrograde condition) is wrongly flagged `contradicted_fact`.
  evidence: Blind Hunter review of this story's diff. The frozen spec's Boundaries text ("retrograde is asserted only by station.direction == 'retrograde' or any standing_retrograde entry") explicitly commits to this unified reading without distinguishing the two tokens' astrological meaning; fixing it correctly means renegotiating that frozen rule (and possibly Story 5.1's vocabulary), not something this story's implementation can resolve unilaterally. Fails safe (over-rejects a true statement) rather than admitting a false one.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-check-every-claim-against-the-payload.md`
  summary: `_house_facts()` (`core/gate/run.py`) adds an Ingress's `house_departed` and `house_entered` to the same fact set without distinguishing them, so a Claim naming the house a body just left is treated as equally grounded as one naming the house it entered — no invented house number can pass, but the Gate cannot tell "just entered X" from "just left X" apart.
  evidence: Blind Hunter review of this story's diff. The Design Notes' category table lists both fields together with no semantics on which; low practical risk since only the two real numbers from the cited event are ever accepted, but worth a future refinement if Story 5.5's surfaced detail needs to explain entered-vs-departed precisely.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-check-every-claim-against-the-payload.md`
  summary: `is_claim()`'s bare `day_of_month_pattern` (1-31, already logged as a Story 5.1 false-positive risk) now has a concrete downstream cost once Story 5.2 wired verification in: any ordinary number 1-31 in prose (an age, a degree, an orb, a count) makes the sentence a Claim requiring a citation whose date matches that number, so unrelated numbers can trigger spurious `empty_citation`/`invented_fact`/`contradicted_fact` Gate failures and regenerations, not just an unnecessary classification as noted in the original Story 5.1 finding.
  evidence: Blind Hunter review of this story's diff. Confirms and sharpens the existing Story 5.1 deferred finding on this same pattern — Story 5.2 is the first place this false-positive risk becomes an actual Gate failure (and regeneration cost) rather than just a classification curiosity, worth prioritizing if regeneration rates look high in practice.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-3-make-the-gate-the-only-path-to-an-exportable-report.md`
  summary: The new static AST guard in `tests/test_export_boundary.py` (`_annotation_names`) only recognizes `ast.Name`/`ast.Attribute` nodes in a parameter annotation, so a function written with an explicit quoted forward reference (e.g. `def sneaky(draft: "GeneratedDraft")`) is invisible to the scan and would evade `test_no_function_accepting_a_generateddraft_also_has_export_in_its_name`.
  evidence: Blind Hunter review of this story's diff. Practical risk is low today since the whole codebase already uses `from __future__ import annotations`, making an explicit quoted annotation non-idiomatic and unlikely to appear — but the gap is real and the same blind spot likely exists in `tests/test_import_boundary.py`'s older, structurally similar visitor. Worth hardening both together if a future author ever does write a quoted annotation.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-4-regenerate-a-failing-report-automatically-whole.md`
  summary: `gate_passed` has no entry in `_STAGE_BACKOFF_OVERRIDES`, so `with_backoff` retries the deterministic, pure `run_gate()` call up to 3 times (with two real sleeps, ~0.3s) on every single Gate failure before `drive()`'s stage-failure/regeneration handling even sees it — pointless work since a pure function re-checking the same already-persisted draft cannot produce a different result.
  evidence: Blind Hunter review of this story's diff. Pre-existing since Story 5.3 introduced `gate_passed` with no backoff override — Story 5.4's `except GateFailedError` branch doesn't change when `with_backoff` itself gives up, only what happens after. Low-severity (bounded, small, real-time cost only), not something this story introduced or is scoped to fix.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-4-regenerate-a-failing-report-automatically-whole.md`
  summary: `shell/http/templates/report_run_poll.html` renders its "Failed: {{ run.failure_reason }}" banner and its "View Draft" link as independent, non-exclusive blocks. Once a run terminally fails via regeneration-bound exhaustion, `run.stage` is deliberately left at `draft_ready` (so the final draft stays reachable, per this story's own design) — both blocks render together, so Francesco sees a working "View Draft" link right next to the failure banner, with nothing on the draft view itself marking that draft as Gate-rejected.
  evidence: Blind Hunter review of this story's diff. The same shape already existed before this story: the old 5-consecutive-failures terminal path (Story 4.8's generic bookkeeping, as it applied to `gate_passed` pre-5.4) also left `run.stage` at `draft_ready` on terminal failure, so this ambiguity was already reachable, not introduced here. Distinguishing a Gate-passed draft from a rejected one on the draft view is naturally Story 5.5's territory ("See exactly what failed and what it contradicts").

- source_spec: `_bmad-output/implementation-artifacts/spec-5-4-regenerate-a-failing-report-automatically-whole.md`
  summary: No template or route surfaces regeneration progress during an active cycle — a poll mid-regeneration just shows "Stage: payload_ready" with no "regenerating, attempt N of `_MAX_REGENERATIONS`" context, even though the run is silently retrying the Generator in the background.
  evidence: Blind Hunter review of this story's diff. Not required by any FR-21/AD-10 acceptance criterion (only "automatic and bounded" is required) and not something a prior story's UI anticipated, but a real, reasonable UX improvement once regeneration is real. Natural fit for Story 5.5 or a later polish pass.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-4-regenerate-a-failing-report-automatically-whole.md`
  summary: `_run_draft_ready` re-fetches `current_style_guide(session)` fresh on every regeneration attempt (by design, per Story 4.2's "edit without a deploy"), while `ReportPayload`/`StoredReportTheme` are always read back frozen from the original `payload_ready` run. An admin editing the Style Guide in the narrow window between two polls of the same regeneration cycle could see the Style Guide version drift across attempts within one run, even though the Payload/astronomy are guaranteed identical.
  evidence: Blind Hunter review of this story's diff. No FR/AD requires the Style Guide to stay fixed across regeneration attempts (only the Payload/astronomy is called out, in FR-21's own "so the astronomy cannot change between attempts"), so this isn't a violation of any stated invariant — but it's a genuinely new scenario 5.4 introduces (`draft_ready` previously ran at most once per run, so no such drift window could exist before this story) and is worth an explicit decision if it ever matters in practice.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-4-regenerate-a-failing-report-automatically-whole.md`
  summary: No test exercises `migrations/versions/0012_bounded_regeneration.py` against pre-existing data — e.g. a `report_draft`/`report_run` row created under the pre-5.4 schema correctly receiving `attempt=0`/`regeneration_count=0` via the migration's `server_default` and satisfying the new composite unique index.
  evidence: Blind Hunter review of this story's diff. `tests/test_migration_chain.py` proves the chain applies cleanly against an empty schema; a pre-existing-data backfill test is a pattern this project has not established for any prior additive migration either (e.g. `0010_report_run_failure.py`), so this is a systemic gap in migration-testing practice, not unique to this story.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-5-see-exactly-what-failed-and-what-it-contradicts.md`
  summary: `view_report_draft`'s recomputed `run_gate()` uses `request.app.state.gate_vocabulary` -- the currently loaded vocabulary -- not the version that actually classified the original failure. If `vocabulary.it.json` is edited/redeployed between a run's terminal failure and Francesco later opening its draft, the violations shown can differ from what actually caused the failure.
  evidence: Blind Hunter review of this story's diff. This is exactly why this epic's own Technical Decisions call for every Report to record "the Gate vocabulary version that classified it" -- but that persistence is explicitly Story 5.6's `GATE_RESULT` table, which this story's own Boundaries deliberately avoid pre-empting ("no `GATE_RESULT` audit table, no persisted violations list -- Story 5.6"). Recomputation from the current vocabulary is correct until 5.6 lands; the risk window only opens once the vocabulary is edited after a run has already failed.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-6-keep-the-gate-s-record-so-a-regression-is-visible-early.md`
  summary: `gate_passed` is not in `_STAGE_BACKOFF_OVERRIDES`, so `drive()`'s `with_backoff(...)` (default `max_attempts=3`) retries a `GateFailedError` up to 3 times before `drive()`'s own `except GateFailedError` block runs -- pure waste, since `run_gate()` is deterministic and every retry recomputes the identical result. Persistence is already correctly deduplicated (this story writes the `gate_result` row from `drive()`'s except block, not inside the retried stage function), so this only costs latency (up to ~0.3s per check) across a fully bound-exhausted run, never a duplicate row.
  evidence: Blind Hunter review of this story's diff. Pre-existing since Story 5.4 introduced `gate_passed`'s regeneration path; not caused by this story. Fixing it means adding a `max_attempts=1` (or similar) override for `gate_passed`, which trades away `with_backoff`'s resilience against a genuinely transient DB blip during `_run_gate_passed`'s own reads/writes -- a real tradeoff this story's spec deliberately left untouched, worth a deliberate decision rather than a silent change.

- source_spec: `_bmad-output/implementation-artifacts/spec-5-6-keep-the-gate-s-record-so-a-regression-is-visible-early.md`
  summary: `_run_gate_passed` now calls `store_report(...)` then `store_gate_result(...)` back to back on the pass path. If `store_gate_result`'s own `flush()` ever fails (e.g. a transient DB error), `with_backoff` retries the whole stage function, and the retry's `store_report(...)` call raises a unique-constraint `IntegrityError` on `report.report_run_id` (already flushed, uncommitted, from the first attempt) -- masking the original `store_gate_result` failure with an unrelated one, and reaching `drive()`'s generic `except Exception` path (incrementing `stage_failure_count`) instead of surfacing the real cause.
  evidence: Blind Hunter review of this story's diff. This story is what introduces the second write after `store_report(...)` -- previously it was the stage function's last statement, so no such retry-and-mask window existed. Matches the pre-existing, already-tracked class of risk in `epic-4-retro-item-23` ("guard with_backoff-retried two-write stage functions against a partial flush poisoning the transaction"), which this story's own Boundaries deliberately named out of scope rather than re-solving here.

- source_spec: `_bmad-output/implementation-artifacts/spec-deferred-work-40-dispose-and-tune-the-app-engine.md`
  summary: `create_app()`'s lifespan hook has a shutdown phase (dispose the engine) but no startup phase, so a database that is unreachable at boot is not detected until the first request that needs it -- `/healthz` stays liveness-only and reports the process up regardless.
  evidence: Blind Hunter review of this story's diff. Pre-existing since Story 1.1/2.3 introduced the engine and `/healthz`; not caused by this story, only made more visible now that `create_app()` has a lifespan hook in place to potentially extend. Related to the already-tracked liveness-only `/healthz` gap from Story 1.1's deferred items, but distinct: this is specifically about using the new lifespan's startup phase for an eager reachability check, which this story's spec deliberately scoped out (dispose + `pool_pre_ping` only).

- source_spec: `_bmad-output/implementation-artifacts/spec-deferred-work-41-bound-client-and-chart-string-columns.md`
  summary: `migrations/versions/0014_bound_client_and_chart_string_columns.py` narrows three previously-unbounded columns (`client.name`/`.iana_zone`, `natal_chart.computation_config_content_hash`) to `VARCHAR(n)` with no pre-flight check that an existing row doesn't already exceed the new bound, and no acknowledgment that Postgres's `ALTER COLUMN TYPE` here takes an `ACCESS EXCLUSIVE` lock for a full-table scan.
  evidence: Blind Hunter review of this story's diff. Low practical risk today -- both columns are already written only through this app's own validated paths (the HTTP route, the Geocoder, the sha256 hasher), so no existing row plausibly exceeds 200/64 characters, and the `client`/`natal_chart` tables are small for a single-operator tool -- but the migration itself makes no defensive check, and a genuinely large future table would turn this into a real production risk. Worth a deliberate pre-flight-query or `NOT VALID`-style mitigation decision if this pattern is reused for a bigger table later.

- source_spec: `_bmad-output/implementation-artifacts/spec-deferred-work-41-bound-client-and-chart-string-columns.md`
  summary: `place_cache.iana_zone` and `report_payload.computation_config_content_hash`/`.sections_config_content_hash` remain unbounded `String` columns, even though this story bounded the same two logical values (an IANA zone id, a sha256 content hash) on `Client`/`StoredNatalChart`.
  evidence: Blind Hunter review of this story's diff. Named explicitly out of scope by this story's own spec Boundaries ("Never... `PlaceCache.iana_zone`... `ReportPayload`'s two hash columns -- named out of scope by the deferred item itself; a separate follow-up if ever needed") -- logged here per that note, not a new discovery.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-1-read-a-report-with-its-facts-one-click-away.md`
  summary: Neither the finished-Report view (`report.html`, this story) nor the pre-existing Draft view (`report_draft.html`, Story 4.6) shows each Sentence's `entry_ids` (citations) or the Gate's `vocabulary_version` -- for a page whose entire premise is Gate-verified groundedness, Francesco has no way to see what backs a given sentence from the rendered page itself.
  evidence: Blind Hunter review of this story's diff. Pre-existing since Story 4.6 introduced `report_draft.html`'s rendering shape, which this story's `report.html` deliberately mirrors byte-for-byte per its own spec's "reuse `render_draft`" boundary; not something this read-only story's scope covers introducing.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-1-read-a-report-with-its-facts-one-click-away.md`
  summary: `view_report_payload`, `view_report_draft`, and now `view_report` each independently repeat the same "look up a row for `run_id`, `RuntimeError` if missing" block for `ReportPayload`/`Client` -- three near-identical inline lookups in the same module with no shared helper.
  evidence: Blind Hunter review of this story's diff. The duplication pattern predates this story (the first two occurrences already existed); this story's boundaries explicitly required `view_report_draft`/`view_report_payload` to "stay byte-for-byte unchanged," so extracting a shared helper now would mean touching routes this story was scoped to leave alone.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-1-read-a-report-with-its-facts-one-click-away.md`
  summary: `report.html`'s per-section/list-section rendering loop is a byte-for-byte copy of `report_draft.html`'s own loop (Story 4.6), with no shared Jinja partial -- any future change to how a Section renders has to be made in both files to stay in sync.
  evidence: Blind Hunter review of this story's diff. Deduplicating requires editing `report_draft.html`, which this story's own spec Boundaries named out of scope ("Never: ... stay byte-for-byte unchanged"); a shared `{% include %}` partial is the natural fix once that file is back in scope for another story.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-export-a-passed-report-to-pdf-and-markdown.md`
  summary: Export a passed Report to Markdown, alongside the PDF export this spec covers.
  evidence: Split at planning time to keep the spec within the 900-1600 token scope target -- the original draft covering both formats (WeasyPrint PDF adapter + a separate Markdown renderer, on top of the shared `ExportRecord` table/migration/cascade) measured ~2367 tokens. Markdown export can reuse the same `ExportRecord` table, gate, and route family this spec establishes for PDF; only a second renderer and route are needed -- and will need its own template distinct from `report_export.html`, which is HTML/PDF-oriented.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-export-a-passed-report-to-pdf-and-markdown.md`
  summary: `download_report_pdf` (`GET /report-runs/{run_id}/export/pdf`) is a GET route that always mutates state -- it writes a new `ExportRecord` row on every call and may advance `run.stage` to `"exported"` on the first one -- so a browser link-prefetch, crawler, or accidental retry silently inflates the export audit trail.
  evidence: Blind Hunter review of this story's diff. Consistent with the existing `poll_report_run` precedent of a GET route with side effects in the same module (`shell/http/routes/report_runs.py`), so not unique to this story, but worth a deliberate look once more GET routes accumulate this shape.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-export-a-passed-report-to-pdf-and-markdown.md`
  summary: The exported PDF's section headings render as the raw internal snake_case keys (`energia_generale`, `giorni_di_attenzione`, `consiglio_finale`, etc.) rather than human-readable Italian titles, in a document meant to be handed directly to a client.
  evidence: Blind Hunter review of this story's diff. Inherited unchanged from `report.html`/`report_draft.html`'s own section-heading rendering (Stories 4.6/6.1), which this story's Boundaries required reusing verbatim -- not introduced by this story, and would need a shared section-title mapping to fix everywhere at once.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-export-a-passed-report-to-pdf-and-markdown.md`
  summary: `shell/http/templates/report_export.html` ships with no CSS at all -- no page-break control, margins, or typography -- for a PDF meant to be handed directly to a paying client rather than an internal debug view.
  evidence: Blind Hunter review of this story's diff. This story's spec scoped the template as "minimal HTML for WeasyPrint input" with no styling requirement named; visual polish is a natural follow-up once the plain-content export is proven out.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-export-a-passed-report-to-pdf-and-markdown.md`
  summary: `download_report_pdf` re-implements `view_report`'s fetch-and-assemble chain (`Report` -> `ReportRun` -> `ReportDraft` -> `ReportPayload` -> `Client` -> `render_draft`) inline instead of factoring out a shared helper -- a fourth near-identical occurrence in the same module.
  evidence: Blind Hunter review of this story's diff. The first three occurrences (`view_report_payload`, `view_report_draft`, `view_report`) were already logged as a deferred-work item after Story 6.1's review; this story's Boundaries required `view_report` to "stay untouched beyond one added link," so extracting a shared helper now would mean touching a route this story was scoped to leave alone.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-export-a-passed-report-to-pdf-and-markdown.md`
  summary: No test exercises two rapid/concurrent export requests for the same run, and no test asserts the actual PDF content of a *second* export -- only its `ExportRecord` count and `run.stage` are checked on repeat exports.
  evidence: Blind Hunter review of this story's diff. Matches this codebase's existing convention of tracking concurrency edge cases as deferred-work rather than blocking a story on race-condition tests (e.g. epic-4-retro-item-26, epic-5-retro-item-44).

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-export-a-passed-report-to-pdf-and-markdown.md`
  summary: `shell/http/templates/report_export.html` (and every other template in `shell/http/templates/`) declares `<html lang="en">` even though most of this application's rendered content -- including every Report Section -- is Italian prose.
  evidence: Blind Hunter review of this story's diff. Pre-existing and app-wide: all 13 existing templates use `lang="en"` uniformly, including `report.html`/`report_draft.html` which this story's template deliberately mirrors; not introduced by this story and would need a coordinated fix across every template, not a one-off change here.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-record-how-the-report-went-out-in-one-interaction.md`
  summary: `ExportRecord.disposition`'s two-value domain (`"as_generated"`/`"edited"`) is enforced only by the HTTP route's `_DISPOSITION_VALUES` check (`shell/http/routes/report_runs.py`), not by the schema or the Python type system -- a plain `sa.String(16)` column with no `CHECK` constraint, and a bare `str | None` type hint rather than `Literal["as_generated", "edited"] | None`. A direct DB write, a future caller of `record_send_disposition()`, or a bug bypassing the route could still store an arbitrary string.
  evidence: Blind Hunter review of this story's diff. Matches how `ExportRecord.format` (Story 6.2, same table) was already left unconstrained beyond a length bound -- consistent with this codebase's existing convention of enforcing closed vocabularies at the application boundary rather than via DB `CHECK`/`ENUM`, so not obviously wrong, but worth a deliberate look given how many docstrings in this story assert "exactly two values."

- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-record-how-the-report-went-out-in-one-interaction.md`
  summary: `report.html`'s disposition-label lookup (`{% for value, label in disposition_choices %}{% if value == latest_export.disposition %}...`) has no fallback for an unrecognized `disposition` value -- it would silently render an empty `<p>` instead of surfacing the anomaly.
  evidence: Blind Hunter review of this story's diff. Only reachable if the deferred item above (domain not enforced at the schema level) is ever actually exploited; low likelihood given the single write path, but a one-line `{% else %}` fallback would close it cheaply whenever that item is addressed.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-record-how-the-report-went-out-in-one-interaction.md`
  summary: `record_export_disposition`'s existence check (`_latest_export_record`) and `record_send_disposition()`'s own internal query each independently find "the latest `ExportRecord` for this run" on a single disposition POST, instead of the first lookup's result being threaded through to the second.
  evidence: Blind Hunter review of this story's diff. A minor efficiency/duplication nitpick, not a bug -- fixing it cleanly means changing `record_send_disposition()`'s signature to accept an `ExportRecord` id directly rather than a `run_id`, which is a small API shape change worth a deliberate look rather than a reflexive patch.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-record-how-the-report-went-out-in-one-interaction.md`
  summary: `ExportRecord.elapsed_seconds` has no sanity bound -- clock skew, a manually-set `ReportRun.created_at`, or a run left in `gate_passed` for an unusually long time would silently store a negative or implausibly large value with nothing flagging it as anomalous.
  evidence: Blind Hunter review of this story's diff. Low real-world likelihood for a single-operator tool driven by manual clicks, and the "correct" fix (clamp vs. raise vs. flag) is a genuine design choice rather than an obvious one-line patch -- worth a deliberate decision if this metric is ever relied on for the per-Report time-budget success metric.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-record-how-the-report-went-out-in-one-interaction.md`
  summary: `record_send_disposition()`'s boolean return conflates "no `ExportRecord` exists for this run" and "the latest one already has a disposition" into the same `False` -- the function's own docstring requires the caller to do a separate existence check to tell them apart, which today's one caller (`record_export_disposition`) does correctly, but any future direct caller (a script, a background job) could easily miss.
  evidence: Blind Hunter review of this story's diff. A real API-design sharp edge, but changing the return shape (e.g. a small result enum) to make the two states distinguishable is more than a trivial patch, and the one existing caller is already correct -- worth revisiting if a second caller is ever added.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-3-record-how-the-report-went-out-in-one-interaction.md`
  summary: No correction/undo path exists once a disposition is recorded -- `record_send_disposition`'s `WHERE disposition IS NULL` clause makes the write deliberately permanent, so a misclick between "Sent as generated" and "Sent, edited first" cannot be corrected through any route, UI affordance, or even an admin/CLI escape hatch.
  evidence: Blind Hunter review of this story's diff. Deliberate by design -- matches this codebase's existing write-once philosophy for `Report`/`StoredGateResult`/`ExportRecord` -- but a real, user-facing gap worth a conscious product decision (e.g. a narrow "undo within N minutes" affordance) rather than silently accepting permanent misclicks.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-5-take-a-backup-i-actually-hold.md`
  summary: Nothing addresses what happens to a downloaded backup file after it leaves the browser -- encryption at rest, secure storage, retention, or rotation of old backups, even though the file is a full, unencrypted plaintext dump of every Client's PII (names, birth dates/times, precise coordinates).
  evidence: Blind Hunter review of this story's diff. Out of scope for a backend route -- this is an operational/procedural decision for how Francesco actually holds the file once downloaded, not a code change, but real given the export's sensitivity and worth a conscious decision before this route sees regular use.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-6-be-told-when-my-backup-is-out-of-date.md`
  summary: `GET /backup` now has a durable side effect (an INSERT + COMMIT into `backup_record` on every call), violating GET's safety/idempotency expectation -- a browser retry, link prefetch, proxy, or health-check scanner hitting the route would silently record a "backup completed" timestamp that was never a deliberate operator action.
  evidence: Blind Hunter review of this story's diff. Low real-world likelihood for a single-operator, authenticated, attachment-download route not linked from anywhere crawlable -- but a genuine correctness gap in the staleness signal's own honesty if it is ever triggered by something other than Francesco's deliberate click.

- source_spec: `_bmad-output/implementation-artifacts/spec-6-6-be-told-when-my-backup-is-out-of-date.md`
  summary: This app has no CSS anywhere (no stylesheet, no `<style>` block, no shared layout) across any of its 13 templates, so the new "Backup out of date" warning -- like every other status message in the app -- renders as a plain, unstyled paragraph indistinguishable from ordinary text, undercutting its purpose as a warning worth noticing during a batch.
  evidence: Blind Hunter review of this story's diff. Pre-existing and systemic across the whole app, not introduced by this story -- worth a deliberate, app-wide minimal-styling pass rather than a one-off fix scoped to this single banner.

- source_spec: `_bmad-output/implementation-artifacts/spec-7-1-add-a-past-report-to-the-corpus.md`
  summary: The hand-rolled urlencoded form parser (`_parse_form`, `_FormTooLarge`, `_FormNotUtf8`, `_MAX_*_FORM_BODY_BYTES`) is now copy-pasted across `shell/http/app.py`, `shell/http/routes/clients.py`, `shell/http/routes/style_guide.py` and `shell/http/routes/corpus.py`; likewise `_UTCDateTime` is imported as a private symbol from `shell/adapters/postgres/report_run` by `style_guide.py`, `backup_record.py` and now `corpus_entry.py`.
  evidence: Blind Hunter review of this story's diff. Both are pre-existing cross-module smells that Story 7.1 adds another instance to per its own spec instruction ("mirror style_guide.py::_parse_form"). Consolidating the form parser into one shared module and promoting `_UTCDateTime` to a public shared column-types module is a focused refactor touching several call sites, not a trivial patch.

- source_spec: `_bmad-output/implementation-artifacts/spec-7-1-add-a-past-report-to-the-corpus.md`
  summary: `GET /corpus` returns every entry with each report's full `content` rendered in a `<pre>` block, with no pagination, no preview/truncation, and no single-entry view route (`GET /corpus/{id}`).
  evidence: Blind Hunter review of this story's diff. Fine at Story 7.1's expected volume, but epic-7-context.md states Francesco has "hundreds of existing hand-written reports" to load, so the unbounded full-content list will become unwieldy. Worth a pagination/preview pass, most naturally alongside Story 7.3's composition view.

- source_spec: `_bmad-output/implementation-artifacts/spec-7-2-mark-an-entry-paired-or-unpaired.md`
  summary: `_render_new_form` runs `list_clients` (a full `client` table load) even on the `_FormTooLarge` / `_FormNotUtf8` body-rejection paths, which exist to reject an abusive body cheaply.
  evidence: Story 7.2 routed the two body-level 422 handlers in `shell/http/routes/corpus.py` through `_render_new_form`, which unconditionally calls `list_clients(session)` to populate the Client picker; the oversized/non-UTF-8 branches have no submitted values to echo and do not need the picker, so the query is pure overhead on the exact requests that path is meant to shed.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-1-pass-conformance-across-the-full-adversarial-fixture-set.md`
  summary: Month-fixture `expected.transit_positions` rows only ever assert `retrograde` where it is `true`; a body that is direct is indistinguishable from a body whose direction was never transcribed, so `_calc_body`'s speed sign is unchecked for most bodies.
  evidence: `compare()` walks only the keys present in `expected`, and the three month fixtures carry `retrograde = true` on a handful of rows and nothing on the rest. Requiring an explicit `retrograde` bool on all ten rows of every month fixture would turn every row into a positive direction assertion. Fixture-transcription scope (Francesco's), broader than Story 8.1's wiring.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-1-pass-conformance-across-the-full-adversarial-fixture-set.md`
  summary: RESOLVED 2026-08-27 (commit 874ff9d). The three `correction_2026_08_27` fixture values were re-verified against a logged-in Astro.com "Natal chart and transits" session; each `PENDING` clause is replaced with a `reverify_2026_08_27` line. Kept here only as a record.
  evidence: Original concern: the re-verification obligation (Story 8.1 AC4) lived only in a TOML comment that a green build never surfaces. Outcome: 2023-08-01 00:00 UT transiting Jupiter 13 Tau 41' / Uranus 22 Tau 45' show no 'r' marker (direct, confirms true->false); 2018-02-01 00:00 UT transiting Moon 18 Leo 11' = 138.183 (0.004 from the corrected 138.1793), root cause a two-sign transcription offset. No fixture values changed by the re-verify. The broader "a green build never flags an unresolved PENDING" point still stands for future corrections.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-1-pass-conformance-across-the-full-adversarial-fixture-set.md`
  summary: The per-fixture `correction_*` / `reverify_*` metadata log in the conformance fixtures is now five-plus entries deep and out of chronological order (`reverify_2026_08_20` precedes `correction_2026_08_19`), becoming a changelog-in-a-fixture that is its own maintenance burden.
  evidence: `tests/conformance/fixtures/no-lunations-month.toml` header carries `correction_2026_08_18`, `reverify_2026_08_20`, `correction_2026_08_19`, `correction_2026_08_27` in that file order. Pre-existing ordering drift, not introduced by Story 8.1; consider consolidating into a single ordered `history` array or a sidecar file.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-2-re-verify-the-generation-provider-s-data-terms-and-record-it.md`
  summary: Runtime enforcement of `GEMINI_DATA_TERMS_VERIFIED_AT` freshness is still absent -- `shell/config.py::_read_gemini_data_terms_verified_at` accepts any ISO date, including a future one (epic-4-retro-item-25, still open), and nothing anywhere warns when the recorded check is stale (older than N months).
  evidence: Blind Hunter review of the Story 8.2 diff. Story 8.2 deliberately scoped out any startup/staleness check ("Never: no new staleness banner, no startup check") and added a future-date guard only at the docs-record level (`checked <= today` in tests/test_data_terms_record.py), not on the env var at process start. The runtime future-date guard is the still-open epic-4-retro-item-25; a "record too old" staleness signal has no owner. Worth a conscious decision before the next re-verification cycle.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-3-measure-the-latency-the-prd-only-assumed.md`
  summary: Release-validation records (docs/release-validation/latency.md, gemini-data-terms.md) have no automated staleness check on their `checked` date and no guard binding their prose/values to the epics.md / PRD lines they mirror beyond the single budget number.
  evidence: Blind-hunter review of story 8.3 — the long "Re-measure trigger" list in latency.md is prose only; nothing fails when `checked` goes stale or when an NFR line is edited after the record was written. Same gap exists in the story 8.2 record. A shared guard (max age, and a checksum/quote bind to the governing NFR text) would make both records self-policing.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-4-project-storage-growth-against-the-free-tier-ceiling.md`
  summary: `core/payload/freeze.py::canonical_json_bytes` docstring and `shell/adapters/postgres/report_payload.py`'s class docstring both assert every persisted `ReportPayload` "is written as" canonical JSON (sorted keys, no insignificant whitespace), but the write path passes the plain dict to SQLAlchemy's `JSON` column, which serializes with the engine's default `json.dumps` (`", "` / `": "` separators, insertion-order keys). The stored text is therefore not canonical.
  evidence: Blind Hunter review of the Story 8.4 diff. `shell/http/app.py:132` builds the engine with no `json_serializer`, and `store_report_payload` does `ReportPayload(payload=frozen)` with no canonicalization. Pre-existing inconsistency between the documented contract and the write path; surfaced because Story 8.4's size measurement had to pick one serialization. Low functional impact (Postgres `json`, not `jsonb`; ids are still hashed from `canonical_json_bytes` separately), but the docstrings should either be corrected or the write path should canonicalize.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-4-project-storage-growth-against-the-free-tier-ceiling.md`
  summary: The opt-in measurement harnesses (`test_measure_payload_size`, `test_measure_latency`) are skipped in every CI run and import many private symbols from `tests/test_runner_driver.py`; if those drift the harness breaks silently while the always-on record-guards stay green, so the release gate can pass on an unverifiable record.
  evidence: Blind Hunter review of the Story 8.4 diff. Both harnesses are `skipif` unless an env var is set and nothing periodically exercises them. A scheduled non-blocking job (or a lightweight always-on smoke that drives one run, not the full sample) would keep them honest without taxing the default suite.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-4-project-storage-growth-against-the-free-tier-ceiling.md`
  summary: There is no decision-log / ADR index in the repo; the storage-growth policy (Story 8.4) and prior ratified decisions (8.2, 8.3) live only as prose inside their release-validation files, invisible from any decisions index, with same-day/same-person ratification and no linked commit, PR, or review reference.
  evidence: Blind Hunter review of the Story 8.4 diff. "Raised as an explicit decision rather than absorbed" (Story 8.4 AC-3) is satisfied in-file but not discoverable. A lightweight `docs/decisions/` log or an entry format the release checklist points at would make ratified release-gate decisions auditable.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-4-project-storage-growth-against-the-free-tier-ceiling.md`
  summary: The storage-growth projection's `payload_p90_bytes` rests on a single non-adversarial fixture (Fort Worth, born 2026-01-01, one 12-consecutive-month window). Payload size scales with transit-event count, so a defensible upper p90 should be measured against Story 8.1's adversarial fixtures (retrograde-station month, double-lunation month) which are designed to maximise event counts.
  evidence: Blind Hunter review of the Story 8.4 diff. The record acknowledges the fixture is a typical-month sample and leans on the overhead factor plus the 50%-trigger policy to absorb the gap, but a re-measure across the adversarial set (and ideally a second birth chart) would tighten the number the release gate records.
- source_spec: `_bmad-output/implementation-artifacts/spec-retro-c-two-write-guard-cluster.md`
  summary: A deliberate off-cycle backup taken via the bare `GET /backup` URL (when the run list shows no staleness warning, so no `?record=1` link is rendered) no longer records a `backup_record` row, so Story 6.6's "last backup" tracking never updates for it -- there is no always-visible "record a backup" control, only the link inside the stale-warning `<p role="alert">` block.
  evidence: Blind Hunter review of the retro-C diff. epic-6-retro item 49 was scoped to stop *non-deliberate* hits from clearing the warning; gating the record behind `?record=1` also silently drops the deliberate-but-not-stale case. Pre-existing shape (the `/backup` link was always only in the stale-warning block), surfaced by this change making the bare URL a no-op for recording.
- source_spec: `_bmad-output/implementation-artifacts/spec-retro-c-two-write-guard-cluster.md`
  summary: `GET /backup?record=1` is a state-changing authenticated GET with a guessable parameter -- a malicious page's `<img src="https://.../backup?record=1">` (or an auto-submitting form) loaded in Francesco's authenticated browser records a `backup_record` row and clears the Story 6.6 staleness warning with no interaction, the same "silently clear the warning" outcome item 49 targets, via CSRF.
  evidence: Blind Hunter review (iteration 2) of the retro-C diff. epic-6-retro item 49 named "move behind a POST" as the robust option; the "minimal GET-hardening" decision (human-chosen) closes the incidental-prefetch/bookmark vector but leaves cross-site forgery open. Full fix is POST + CSRF token, or a confirmation step. Lower urgency: single-operator tool behind `AuthMiddleware`, no data loss (an `<img>` cannot read the cross-origin PII response body), and the warning re-arms on the next Report.

- source_spec: `_bmad-output/implementation-artifacts/spec-retro-e-gate-wiring-and-generator-tests.md`
  summary: A deterministic `GenerationError` (`prompt_construction`, and pre-existing `parsing`) is still retried 3x with exponential backoff by the `draft_ready` stage, wasting ~18s+ of sleeps on a failure that cannot succeed on retry.
  evidence: `_STAGE_BACKOFF_OVERRIDES["draft_ready"]` is `{"max_attempts": 3, "base_delay_seconds": 6.0}` (`shell/runner/driver.py:139`); `with_backoff` retries on any exception. `run_gate`/`gate_passed` already got `max_attempts=1` for the same reason (deterministic failure). A non-retryable classification for deterministic `GenerationError` steps (or `max_attempts=1` for `prompt_construction`/`parsing`) is the same lesson. Surfaced by epic-4-retro-item-31's review; adjacent to open items epic-1-retro-item-6 / epic-5-retro-item-44 on backoff overrides. Pre-existing, not introduced by bundle E.
  triage: defer (blind-hunter review of spec-retro-e)

- source_spec: `_bmad-output/implementation-artifacts/spec-retro-e-gate-wiring-and-generator-tests.md`
  summary: `shell/http/draft_view.py::_entry_date` guards only the unrecognized-`kind` branch; `return entry[field]` for a *recognized* kind whose date field is absent still raises a bare `KeyError`, and an aspect entry with `perfected_at is None` returns `None` despite the `-> str` annotation.
  evidence: bundle E's item-32 change swapped the bare `ValueError` for `RuntimeError` on unknown `kind` and the new docstring calls it an "impossible-state guard", but the second impossible state (present kind, missing/None date value) is unguarded. `project_day_lists()` should never emit such an entry, so this is defence-in-depth, not a live bug. Surfaced incidentally by the blind-hunter review; pre-existing, out of item-32's scope.
  triage: defer (blind-hunter review of spec-retro-e)

- source_spec: `_bmad-output/implementation-artifacts/spec-epic-6-retro-item-46-render-weasyprint-native-deps.md`
  summary: `strip_comments` is now copied verbatim into both `tests/test_dockerfile_ephemeris_build.py` and `tests/test_dockerfile_weasyprint_runtime.py`; it only strips `space-#` trailing comments and mishandles `#` inside a quoted string in a `RUN` line, so the two copies share a latent Dockerfile-parsing bug that can now drift apart.
  evidence: The spec deliberately chose local duplication over a cross-test import (test modules do not import each other in this repo). Extracting a robust shared Dockerfile-instruction helper (into a conftest or a `tests/_dockerfile.py`) fits the shared-helper extraction already contemplated by epic-8-retro item 62. No current Dockerfile line triggers the bug, so this is hardening, not a live defect. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-epic-6-retro-item-46-render-weasyprint-native-deps)

- source_spec: `epic-3-retro-item-22` (manual browser check, 2026-08-28 — `docs/release-validation/manual-browser-checks.md`)
  status: RESOLVED 2026-08-28 by `spec-epic-3-retro-item-22-bind-ephemeris-path-per-thread.md`. `core/ephemeris/identity.py` now records the verified directory and exposes `bind_verified_ephemeris_path_to_current_thread()`; `_calc_body` and `compute_natal_chart` call it first, re-pinning pyswisseph's thread-local path on whatever thread computes. Verified: `docker compose` report run reaches `payload_ready`/`gate_passed` and `GET /report-runs/{id}/payload` renders (was a hard `transits_ready` failure). New worker-thread regression tests in `test_ephemeris_identity.py` / `test_transit_aspects.py` / `test_natal_chart.py`; full suite green (1413 passed).
  summary: The entire monthly-report pipeline (`transits_ready` and every stage after it, Epic 3 onward) cannot run in the deployed application. Every `POST /clients/{id}/report-runs` fails at `transits_ready` with `EphemerisIntegrityError: body 0 was not computed via the Swiss Ephemeris (calc_ut returned flags 260); a Moshier fallback is never acceptable`, for every `month` tried.
  evidence: Root-caused live during the item-22 browser check. `verify_ephemeris_identity()` calls `swe.set_ephe_path(DEFAULT_EPHEMERIS_DIR)` exactly once, at `shell/http/app.py` module import, on the main thread. In the vendored `pyswisseph` build, `swe_set_ephe_path()` state is NOT visible across threads — reproduced in-container: after `import shell.http.app`, `core.ephemeris.positions._calc_body(jd, 0)` for 2026-09-15 succeeds on the main thread and raises the exact error on a `threading.Thread` / `anyio.to_thread` worker; calling `swe.set_ephe_path(str(DEFAULT_EPHEMERIS_DIR))` inside that worker thread makes it succeed. FastAPI runs sync (`def`) route handlers in an anyio worker threadpool; `poll_report_run` and `start_report_run` (`shell/http/routes/report_runs.py:228,253`) are sync, so `_drive_run` -> `drive()` -> `core.transits.aspects.find_transit_aspects` -> `_calc_body` all execute on a threadpool thread with no ephemeris path. `create_client` is `async def`, so natal computation runs on the event-loop (main) thread and works — which is why client creation and `/chart` look fine. The full pytest suite is green because pytest is single-threaded (main thread only). Not caught by any test, `python -c` repro, or `docker exec` repro — only the live uvicorn server exhibits it.
  triage: fix-now candidate (blocks Epic 3+ end to end in production; needs its own spec/review). Options: (a) `swe.set_ephe_path(str(ident.directory))` at the top of `_calc_body` — cheap, idempotent, keeps the guarantee on whatever thread computes; (b) make `poll_report_run`/`start_report_run` `async` and dispatch `drive()` through a threadpool whose worker initializer sets the path; (c) have the runner explicitly re-establish the verified ephemeris path before its first `swe` call. Note the natal path (`compute_natal_chart` in an async route today) would hit the same failure the moment it is ever called from a sync route or a background thread — option (a) covers that too. [RESOLVED via option (a)-style thread bind — see `status:` above.]

- source_spec: `_bmad-output/implementation-artifacts/spec-epic-3-retro-item-22-bind-ephemeris-path-per-thread.md`
  summary: No test drives the real report pipeline (`drive()` → `core/transits/*`) through the HTTP layer on a worker thread. `tests/test_http_report_runs.py` and `tests/test_http_clients.py` both fake `drive()` / `compute_natal_chart` precisely because Starlette's `TestClient` runs the ASGI app on its own thread and pyswisseph's path was thread-local — the exact gap that let epic-3-retro item 22 ship. The item-22 fix makes `core/ephemeris/` thread-safe, so those `fake_drive` / `fake_chart_computation` workarounds could now be replaced (or supplemented) with one real end-to-end HTTP test that reaches `payload_ready`.
  evidence: `tests/test_http_report_runs.py:5-13` and `tests/test_http_clients.py:246-256` docstrings state the workaround and its reason. Fits the standing "one real-adapter integration test per port, kept out of the fast unit suite" question already raised in epic-2-retro (action items 1-3 lesson). The item-22 core-level `ThreadPoolExecutor` regression tests cover the defect itself; this is the missing HTTP-integration layer.
  triage: defer (self-review of spec-epic-3-retro-item-22-bind-ephemeris-path-per-thread)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-10-advance-a-report-run-without-blocking-the-request.md`
  summary: `advance()`'s Postgres advisory lock is released by the internal `session.rollback()` in its `except GateFailedError` / `except Exception` / non-concurrent-`IntegrityError` branches, so the regeneration and stage-failure bookkeeping and the final `session.commit()` on those paths run in a fresh, unlocked transaction.
  evidence: The rollback-first pattern is load-bearing (epic-5-retro-item-39: roll back before touching `run` so an aborted transaction cannot mask the failure cause). `pg_try_advisory_xact_lock` is transaction-scoped, so that rollback drops it. A second poll arriving in the sub-millisecond gap between the rollback and the commit could acquire the lock and re-run the same failing stage, double-incrementing `regeneration_count` / `stage_failure_count` and reaching terminal failure an attempt or two early. Narrowed — not closed — by the concurrent-`advance()` unique-constraint `IntegrityError` classification the spec keeps as defense-in-depth. Not introduced by this story: pre-AD-20 the driver had no advisory lock at all and both the start POST and every poll drove with no row lock. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-3-10)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-10-advance-a-report-run-without-blocking-the-request.md`
  summary: `tests/test_latency_record.py` now times a full `_drive` drain (many `advance()` calls plus a commit per stage) rather than a single poll's latency, so the Story 8.3 latency harness no longer measures the metric AD-20 makes operator-visible — one poll's wall time, especially the `draft_ready` poll that carries the real Generator call plus AD-9 backoff.
  evidence: Under the pre-AD-20 driver a fully-local run finished inside the start request, so an end-to-end `drive()` timing was a reasonable latency proxy. AD-20 splits completion across >=5 polls; per-poll latency is now the thing Francesco waits on. Spec-3-10 only required keeping the harness compiling/passing (`update its direct `drive` import to `advance` + drain`), not redefining what Story 8.3 measures. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-3-10)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-the-application-shell.md`
  summary: The new sidebar "Esci" link is a plain `GET /login` that never clears the session cookie, so signing out leaves a valid session alive until its 24h expiry.
  evidence: `base.html` renders `<a class="app-sidebar__signout" href="/login">Esci</a>`. There is no logout route in the codebase and Story 9.1's spec forbids new routes (`Never: No new route`), so a real CSRF-safe `POST /logout` that deletes the cookie needs its own small story (fits AD-15's single-principal auth work). Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-1-the-application-shell)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-the-application-shell.md`
  summary: `static/tokens.css` carries the dark palette in three parallel hardcoded copies — `--<key>-dark` properties on `:root` that nothing references, plus the same hexes re-typed under `@media (prefers-color-scheme: dark)` and under `:root[data-theme="dark"]`.
  evidence: The `--*-dark` properties (lines ~57-82) are never read with `var()`; the two dark blocks re-hardcode identical hexes rather than referencing them. Dark mode works, so this is a DRY/maintainability smell, not a bug. The redundancy was driven by the spec's `Always` clause requiring "a CSS custom property for every token in DESIGN.md's `colors:` map" plus `test_tokens_css_defines_a_custom_property_for_every_design_colour_key`. A clean fix (drop the dead props, make the media/attribute blocks the single dark source, relax the completeness test) is a small follow-up better done once a browser/visual dark-mode check exists to catch regressions. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-1-the-application-shell)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-the-application-shell.md`
  summary: The <900px off-canvas drawer implements a Tab/Esc focus loop but not full modal-dialog semantics — no `aria-modal`/`role="dialog"`, the rest of the page is never `inert`/`aria-hidden` while it is open, and background scroll is not locked.
  evidence: `shell.js` cycles focus within `[data-app-sidebar]` and closes on Esc/scrim, which meets Story 9.1's "focus-trapped drawer" AC, but background content stays in the accessibility tree and scrolls behind the scrim. Story 9.9 ("Italian everywhere, and the accessibility floor") explicitly owns the modal/drawer trap audit — fold this hardening there. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-1-the-application-shell)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-the-application-shell.md`
  summary: The vendored shell assets (`tokens.css`, `shell.js`, `htmx.min.js`) are referenced by bare unversioned `/static/...` paths, so after a vendored-asset change an operator can sit on stale CSS/JS with only `StaticFiles` ETag revalidation as protection.
  evidence: `base.html` hardcodes the `/static/...` strings. `StaticFiles` sends ETag/Last-Modified so revalidation (304) works, but there is no content-hash query string or build id for a hard cache-bust. Low urgency for a single-operator internal tool on auto-deploy; worth a follow-up (a `?v=<hash>` helper or a Jinja `url_for('static', ...)` with a version param). Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-1-the-application-shell)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-the-application-shell.md`
  summary: The drawer's runtime behaviour (focus trap, Esc-to-close, scrim click, focus restoration, close-on-widen) is only pinned by source-string greps in `tests/test_http_shell.py`, not by a real DOM/browser test.
  evidence: The project's test stack is pytest + Starlette `TestClient` with no browser-automation dependency, so a behavioural drawer/theme-toggle test needs new infrastructure (Playwright or similar). Story 9.9's accessibility-floor pass will need the same infra for its keyboard-only sweep — introduce it there and backfill drawer/toggle behavioural tests. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-1-the-application-shell)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-the-application-shell.md`
  summary: `ruff format --check .` reports ~71 files repo-wide would be reformatted by the installed ruff 0.16.3 — the tree was last formatted with an older ruff and has drifted. Not caused by Story 9.1 (its new/edited files are format-clean; the diffs are in untouched pre-existing blocks).
  evidence: `.venv/bin/python -m ruff check .` is clean; only `ruff format --check` diverges, and only in code Story 9.1 did not touch. Fix is a one-time repo-wide `ruff format` commit plus pinning ruff in `pyproject.toml` dev deps so the formatter version stops drifting. Surfaced incidentally while verifying this change.
  triage: defer (verification of spec-9-1-the-application-shell)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-2-a-home-dashboard-instead-of-a-404.md`
  summary: The Home dashboard renders each run's `updated_at` as a bare UTC wall-clock (`strftime("%d/%m/%Y %H:%M")`), so an Italian operator sees "last updated" times 1–2h behind local time with no `Z`/`UTC` marker.
  evidence: `shell/http/routes/home.py:111`. The codebase has no established display-timezone convention — `payload_view.py` converts-and-labels with `%Z` for provenance, but list/detail screens render stored values as-is. A correct fix (DST-aware `Europe/Rome`, applied consistently across screens) belongs with the Story 9.9 UI sweep or a shared formatting helper. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-2-a-home-dashboard-instead-of-a-404)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-2-a-home-dashboard-instead-of-a-404.md`
  summary: `--primary-100` has no dark-theme value in `tokens.css`, so `.status-badge--running` (and the pre-existing `.is-active` sidebar item and the `tokens.css:622` rule) render dark-mode text on a near-white `#EBE7F5` chip — likely below the WCAG AA contrast floor the epic mandates.
  evidence: `tokens.css` redefines `--primary-700`/`--focus-ring`/`--*-surface` under both dark blocks but not `--primary-100` (only defined on bare `:root`, line 35). Story 9.2's running badge follows the existing 9.1 pairing, so this is a token-system gap surfaced (not introduced) by this change. Fix: add `--primary-100-dark` and wire it into both dark blocks; re-check every `--primary-100 + --primary-700` pairing. Owned by the Story 9.9 accessibility-floor pass. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-2-a-home-dashboard-instead-of-a-404)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-2-a-home-dashboard-instead-of-a-404.md`
  summary: No database index backs the Home dashboard's read paths — `ORDER BY report_run.updated_at DESC LIMIT 20` and `backup_is_stale`'s `ORDER BY report.created_at DESC LIMIT 1` (now run on every dashboard load and every Client-reports load).
  evidence: `ReportRun.updated_at` and `Report.created_at` are plain columns (no `index=True`) in `shell/adapters/postgres/report_run.py` / `report.py`. Story 9.2's frozen scope forbids data-model changes, so the index migration is deferred. Low urgency at single-operator scale (~dozens of rows) but the right follow-up as the corpus grows. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-2-a-home-dashboard-instead-of-a-404)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-2-a-home-dashboard-instead-of-a-404.md`
  summary: The Home dashboard shows only the 20 most-recent runs across all Clients with no total count, no "vedi tutti" link, and no pagination, so at a month-end batch (~28 Clients) in-flight runs beyond the 20th are hidden with no indication any exist.
  evidence: `_RECENT_LIMIT = 20` in `shell/http/routes/home.py` with a hard `.limit(...)` and no companion count query. The story AC only asks for "recent ReportRuns", so this is an enhancement, but it undercuts the dashboard's stated purpose ("what needs attention"). Consider a count/summary line or a filtered full-list view (possibly Story 9.3 scope). Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-2-a-home-dashboard-instead-of-a-404)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-2-a-home-dashboard-instead-of-a-404.md`
  summary: Home dashboard run rows are ordered purely by `updated_at` desc, so terminal runs (`Esportato`, `Verifica non superata`) interleave with in-flight ones and the operator cannot quickly isolate what needs attention.
  evidence: `shell/http/routes/home.py` `order_by(ReportRun.updated_at.desc(), ReportRun.id.desc())` with no state grouping/filter. Matches the mockup's flat recency list, so not a spec deviation, but a "failed / running first" grouping or a state filter would better serve the dashboard's purpose. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-2-a-home-dashboard-instead-of-a-404)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-2-a-home-dashboard-instead-of-a-404.md`
  summary: Home dashboard run rows are not links — the operator can see a run's status but cannot click through to `/report-runs/{run_id}` from Home, which is in tension with EXPERIENCE.md's wayfinding rule "a run in progress is reachable from Home".
  evidence: `shell/http/templates/home.html` renders each row as plain spans. The `mockups/key-home.html` reference also shows plain `<td>` cells (no anchors) and the story AC only requires a status badge, so the implementation matches both — but "reachable from Home" reads more naturally as one-click navigable. Confirm with Francesco at screen sign-off; if wanted, link the row (whole-row or client-name + month) to the run route, mirroring `client_reports.html`. Surfaced during triage of the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-2-a-home-dashboard-instead-of-a-404)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-2-a-home-dashboard-instead-of-a-404.md`
  summary: The backup-stale banner uses `role="alert"` (an assertive live region) for content present at page load, so a screen reader announces it on every dashboard visit; WAI-ARIA reserves `alert` for content that appears dynamically.
  evidence: `shell/http/templates/home.html` sets `role="alert"`, matching the frozen spec and the already-shipped `client_reports.html` banner (Story 6.6). Fix both together in the Story 9.9 accessibility pass — switch to `role="status"` (polite) or a plain labelled region. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-2-a-home-dashboard-instead-of-a-404)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-3-the-clienti-list-and-the-client-scoped-tabs.md`
  summary: The new breadcrumb (`_client_tabs.html` and `client_list.html`) is a `<p>` with a literal `/` separator rather than the semantic `<nav aria-label="breadcrumb"><ol>` pattern, so a screen reader announces the slash verbatim and the trail is not exposed as a navigation landmark.
  evidence: `shell/http/templates/_client_tabs.html` renders `<p class="breadcrumb"><a href="/clients">Clienti</a> / {{ client.name }}</p>`; `client_list.html` similarly. This is the app's first breadcrumb — no house pattern existed — and the Story 9.3 CSS block is explicitly marked "PROVISIONAL — Story 9.8 consolidates". Fold a semantic breadcrumb component (`<nav aria-label="breadcrumb">` + `<ol>`/`<li>`, `/` via CSS `::before`) into the Story 9.8 shared-primitive consolidation; update the literal-string assertion in `tests/test_http_client_tabs.py` at the same time.
  triage: defer (blind-hunter review of spec-9-3-the-clienti-list-and-the-client-scoped-tabs)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-4-client-create-correct-and-delete-restyled.md`
  summary: The client create / correct / delete screens still mix English into `<html lang="it">` — the `<h1>`s ("New Client", "Correct Client", "Delete Client"), the birthplace candidate `<legend>` ("More than one place matched … choose one"), and the primary submit labels ("Create Client", "Review correction") — while Story 9.4 translated only the destructive-confirm copy.
  evidence: `shell/http/templates/client_new.html` / `client_edit.html` / `client_delete.html`. Story 9.4's spec ("Ask First") deliberately deferred non-destructive-confirm body copy to the Story 9.9 Italian sweep, matching the Story 9.3 precedent; this is the concrete backlog for that pass (headings, legend, submit labels, and a consistent cancel/back affordance on the create form). Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-4-client-create-correct-and-delete-restyled)

- source_spec: `_bmad-output/implementation-artifacts/spec-9-4-client-create-correct-and-delete-restyled.md`
  summary: The verbatim EXPERIENCE.md delete-consequence sentence ("Elimina definitivamente {nome} e il suo tema natale…", including the `has_superseded_chart` clause) is duplicated between the JS modal in `client_edit.html` and the no-JS panel in `client_delete.html`, so the Italian string has two edit sites.
  evidence: Story 9.4's spec keeps component CSS/markup provisional and names Story 9.8 as the consolidation point ("do not build on these class names elsewhere"); a shared partial/macro for the consequence sentence belongs in that 9.8 modal-primitive extraction. Surfaced by the blind-hunter review of this change.
  triage: defer (blind-hunter review of spec-9-4-client-create-correct-and-delete-restyled)
