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
