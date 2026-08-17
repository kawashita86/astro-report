# Deferred Work

Findings surfaced by review that are real but not this story's problem. Each names
the spec that surfaced it. Append only.

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
