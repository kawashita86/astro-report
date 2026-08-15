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
