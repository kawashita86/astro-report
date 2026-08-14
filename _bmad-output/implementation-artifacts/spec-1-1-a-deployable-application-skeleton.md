---
title: 'Story 1.1 — A deployable application skeleton'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
baseline_commit: '562378819b5e81c5c297299c88829bedb9d19eeb'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The repository has no source code, no dependency manifest, no container and no deployment. Every later story would land in a repository that has never been deployed.

**Approach:** Scaffold the project so the application boots on its production host against its production database: `uv` on Python 3.13 with a committed lockfile, a Docker image running FastAPI as a single process, forward-only Alembic migrations applied before traffic is accepted, and `shell/config.py` as the single validated reader of the environment.

## Boundaries & Constraints

**Always:**
- Exactly one module reads the environment: `shell/config.py`, validating into a **frozen** settings object at startup. Any other module reading `os.environ` is a defect, and a test enforces it.
- Startup fails loudly on a missing or invalid setting — non-zero exit, message naming the offender. Never default a required setting, never serve in a degraded configuration.
- Alembic is forward-only: every `downgrade()` raises. Migrations complete at deploy **before** the service accepts traffic.
- `core/` (pure) and `shell/` (all I/O) are sibling roots per the architecture tree. `shell/` may import `core/`, never the reverse.
- All durable state lives in Postgres; the container filesystem is ephemeral.
- Every component stays inside a free tier at 30–200 Reports/month: Render (free, EU region), Neon Postgres 18 (free, Europe/Frankfurt).
- Versions come from the stack seed (FastAPI, SQLModel 0.0.39, Alembic 1.19.1, Jinja2 3.1.6); the lockfile owns them thereafter.

**Ask First:**
- Provisioning the Render service or Neon project — these need Francesco's accounts. Produce the repo-side configuration and HALT with manual steps.
- Any runtime dependency outside the stack seed, or any design that would not sit inside a free tier at target volume.

**Never:**
- No auth or sessions (1.4), no ephemeris or checksum assertion (1.3), no `computation.toml` contents (1.5), no conformance harness (1.6), no import-boundary test (1.2) — create the directories, not the enforcement.
- No domain models or `Client` table; the baseline migration establishes the chain only.
- No staging environment. No `utils`/`helpers`/`common` modules. No `downgrade()` bodies.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid environment | All required vars set, well-formed | Frozen settings built; app serves | N/A |
| Missing required var | `DATABASE_URL` unset | Aborts before serving; non-zero exit | Names `DATABASE_URL` as missing |
| Malformed value | `DATABASE_URL` without a postgres scheme | Aborts before serving | Names the variable and why it is invalid |
| Unrecognized enum | `ENVIRONMENT=staging` | Aborts before serving | Names the variable and permitted values |
| Mutation attempt | Runtime assignment to a settings attribute | Raises | Frozen object rejects mutation |
| Migration fails at deploy | Baseline revision errors | Deploy aborts; no traffic accepted | Non-zero exit propagates to the deploy step |
| Downgrade attempted | `alembic downgrade` invoked | Raises, no schema change | Forward-only is mechanical, not documented |

</frozen-after-approval>

## Code Map

The repository contains **no source code** — only planning artifacts and `product_research.md`. Everything below is created; nothing is modified.

**Read-only references:**
- `_bmad-output/implementation-artifacts/epic-1-context.md` -- stack seed, conventions, source tree
- `…/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md` -- §"Source tree" is the canonical layout; §"Structural Seed" holds versions and deployment topology; AD-11, AD-15, AD-18
- `…/architecture/architecture-astro-report-2026-08-14/BUILD-ORDER.md` -- §"E0" is this chunk
- `_bmad-output/planning-artifacts/epics.md` -- Story 1.1 acceptance criteria verbatim (~line 402)

**To create:**
- `pyproject.toml`, `.python-version`, `uv.lock` -- Python 3.13 pin, stack-seed deps, committed lockfile
- `Dockerfile`, `.dockerignore`, `compose.yaml`, `render.yaml` -- single-process image; local app+Postgres; Render EU blueprint with a pre-deploy migration step
- `shell/config.py` -- **the** environment reader; frozen settings
- `shell/http/app.py` -- FastAPI factory and an unauthenticated liveness route at `/healthz`
- `core/`, `shell/` -- package roots per the architecture tree
- `alembic.ini`, `migrations/env.py`, `migrations/versions/<baseline>.py` -- forward-only chain
- `tests/test_config.py`, `tests/test_env_access_is_centralized.py` -- I/O matrix, single-reader guard
- `tests/test_forward_only_migrations.py`, `tests/test_migrations_precede_traffic.py` -- matrix rows 6 and 7 (deploy-abort and downgrade-refusal), added by the step-03 matrix audit
- `docker-entrypoint.sh` -- applies migrations, then execs the server; carries the before-traffic ordering
- `.env.example`, `.gitignore`, `README.md` -- required variables, run/deploy steps, cost note

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml` + `.python-version` + `uv.lock` -- initialize the `uv` project, pin Python 3.13, declare stack-seed deps, commit the lockfile -- reproducible builds
- [x] `core/`, `shell/`, `shell/http/` -- create package roots matching the architecture tree -- later stories need a structure that exists
- [x] `shell/config.py` -- validate every environment variable into a frozen settings object; fail loudly and specifically -- AC 2
- [x] `shell/http/app.py` -- FastAPI factory consuming settings; liveness route -- gives the image something to serve and the deploy something to verify
- [x] `alembic.ini`, `migrations/env.py`, `migrations/versions/<baseline>.py` -- wire Alembic to the settings-provided URL; baseline revision; `downgrade()` raises -- forward-only must be mechanical
- [x] `Dockerfile`, `.dockerignore` -- Python 3.13 slim, install from the lockfile, one process on the platform-provided port -- AC 1
- [x] `compose.yaml` -- local Postgres plus app -- the only non-production environment
- [x] `render.yaml` -- EU region, Docker runtime, migrations before traffic via `docker-entrypoint.sh` rather than `preDeployCommand` (paid-instance feature) -- AC 1's "before traffic"
- [x] `tests/test_config.py` -- cover every I/O matrix row -- validation is this story's load-bearing behavior
- [x] `tests/test_env_access_is_centralized.py` -- fail if any module but `shell/config.py` reads the environment -- AC 2 needs enforcement, not discipline
- [x] `tests/test_forward_only_migrations.py`, `tests/test_migrations_precede_traffic.py` -- cover matrix rows 6 and 7, which were live-verified but not test-covered -- a hand-checked property is one refactor from being lost
- [x] `.env.example`, `.gitignore`, `README.md` -- required variables, local run, deploy, and the €0/month component breakdown -- AC 3 recorded once

**Acceptance Criteria:**
- Given a clean checkout, when `uv sync --locked` runs, then it succeeds on Python 3.13 without resolving new versions.
- Given the built image run with a valid environment, when it starts, then a single FastAPI process serves the liveness route on the platform-provided port.
- Given a deploy, when it proceeds, then migrations complete before traffic is accepted, and a migration failure aborts the deploy.
- Given the deployment configuration, when regions are inspected, then the web service is in an EU region and the database in Europe/Frankfurt.
- Given 30–200 Reports per month, when each component is checked against its plan, then all sit inside a free tier and the documented total is €0/month.

## Spec Change Log

- **2026-08-14 — migrations run in the container entrypoint, not as a Render pre-deploy step.**
  Render's `preDeployCommand` is documented as available for *paid* web services only, so using it
  would break the "every component stays inside a free tier / €0-per-month" Always-constraint. The
  ordering it exists to guarantee is instead enforced by `docker-entrypoint.sh`, which runs
  `alembic upgrade head` and only then `exec`s the server: migrations still complete before traffic
  is accepted, a failing migration still exits non-zero and aborts the deploy (the health check
  never passes and the previous version keeps serving), and `exec` keeps the container to a single
  process. Recorded in `render.yaml` and the README as the step to move if the service ever moves
  to a paid plan. No "Ask First" was triggered: the chosen design *is* the free-tier one.
- **2026-08-14 — three runtime dependencies outside the literal stack seed.** `uvicorn` (an ASGI
  server; FastAPI cannot serve without one) and `psycopg[binary]` (a Postgres driver; SQLModel and
  Alembic cannot connect without one) are mechanical consequences of the seeded choices rather than
  new design, so they were added without halting. `httpx`, `pytest` and `ruff` are dev-only. Flagged
  here so the judgement is visible rather than assumed.
- **2026-08-14 (review round 1) — twelve findings applied.** Two were live defects: `Settings`'
  generated repr printed the database password in full (now a hand-written repr redacting to
  `user:***@host`, with the raw value still on the attribute), and `migrations/env.py` routed the
  URL through `ConfigParser`, which raised `ValueError: invalid interpolation syntax` on any
  password containing `%` — percent-encoding being routine in generated Postgres passwords, this
  would have broken every deploy at the migration step. The engine is now built directly from
  `settings.sqlalchemy_url`. The rest closed test gaps (the HTTP app and the migration chain were
  untested; both guards could pass while broken), removed the `ENV PORT=8000` image default that
  contradicted the "nothing is defaulted" contract, moved the entrypoint's cheap checks ahead of
  the irreversible migration, and corrected a README instruction for a `.env` file nothing loaded.
- **2026-08-14 — `Settings` is a frozen dataclass without `slots`.** With `slots=True`, CPython's
  generated `__setattr__` raises a confusing `TypeError` instead of `FrozenInstanceError` when an
  *unknown* attribute is assigned. Dropping `slots` makes the matrix's "mutation attempt" row raise
  `FrozenInstanceError` for both known and unknown attributes.

## Design Notes

`shell/config.py` is what makes AD-11 and AD-18 enforceable later: the environment supplies *deployment* facts, while astronomical tuning values will come from `data/computation.toml` as an explicitly-passed `ComputationConfig` — never from the environment. Keep the two homes separate from the first commit.

The liveness route is deliberately unauthenticated and returns no data. Story 1.4 introduces auth-by-default plus a one-place allowlist; this route is that allowlist's first entry and must not grow a payload meanwhile.

## Verification

**Commands:**
- `uv sync --locked` -- succeeds, no lockfile drift
- `uv run pytest` -- all pass, including config validation and the env-access guard
- `uv run ruff check .` -- clean
- `docker build -t astro-report .` -- image builds
- `docker compose up -d && curl -fsS localhost:8000/healthz` -- success from a single process
- `uv run alembic upgrade head` -- baseline applies locally
- `uv run alembic downgrade -1` -- **raises**; forward-only holds
- `DATABASE_URL= uv run python -c "import shell.config"` -- non-zero exit naming `DATABASE_URL`

**Manual checks (Francesco — requires account access):**
- Render web service created from `render.yaml`, EU region, free plan, Docker image
- Neon project in Europe/Frankfurt, free plan; connection string set as `DATABASE_URL` on Render
- After first deploy: liveness route responds over HTTPS, and the deploy log shows migrations completing before traffic

## Suggested Review Order

**Configuration — the one environment reader**

- Start here: the frozen settings object every other module receives instead of the environment.
  [`config.py:58`](../../shell/config.py#L58)

- Hand-written repr redacts the password; the raw URL stays reachable but never prints.
  [`config.py:78`](../../shell/config.py#L78)

- Every variable is checked before any is reported, so one run names all offenders.
  [`config.py:181`](../../shell/config.py#L181)

- Import-time load: a misconfigured process dies before it can serve.
  [`config.py:212`](../../shell/config.py#L212)

**Migrations before traffic — the ordering, and where it can break**

- Bypasses Alembic's ini layer entirely; a `%` in the password used to abort every deploy.
  [`env.py:19`](../../migrations/env.py#L19)

- Cheap failures fire before the irreversible step: no command given, exit 64.
  [`docker-entrypoint.sh:18`](../../docker-entrypoint.sh#L18)

- PORT validated up front, so `set -u` cannot abort after the schema moved.
  [`docker-entrypoint.sh:25`](../../docker-entrypoint.sh#L25)

- Migrations run, then the server replaces the shell — one process, correct order.
  [`docker-entrypoint.sh:39`](../../docker-entrypoint.sh#L39)

- Forward-only is mechanical: the refusal is the whole body, so nothing half-applies.
  [`0001_baseline.py:27`](../../migrations/versions/0001_baseline.py#L27)

**The serving surface**

- Settings passed in, not read here — keeps the single-reader rule intact and tests hermetic.
  [`app.py:19`](../../shell/http/app.py#L19)

- Liveness only, no body: the first entry in Story 1.4's unauthenticated allowlist.
  [`app.py:37`](../../shell/http/app.py#L37)

**Deployment**

- EU region, free plan; migrations via entrypoint because `preDeployCommand` is paid-only.
  [`render.yaml:18`](../../render.yaml#L18)

- Image invokes the entrypoint; `CMD` supplies the server it execs.
  [`Dockerfile:42`](../../Dockerfile#L42)

- The only non-production environment: production image, unmodified, local Postgres.
  [`compose.yaml:27`](../../compose.yaml#L27)

**Tests — the guards, and proof they bite**

- Matrix rows 1–5: validation is this story's load-bearing behavior.
  [`test_config.py`](../../tests/test_config.py)

- The single-reader rule exists only while this passes; now non-vacuous per root.
  [`test_env_access_is_centralized.py`](../../tests/test_env_access_is_centralized.py)

- Matrix row 6, reading code rather than text so a comment cannot satisfy it.
  [`test_migrations_precede_traffic.py`](../../tests/test_migrations_precede_traffic.py)

- Matrix row 7, plus the generator template so future revisions inherit the refusal.
  [`test_forward_only_migrations.py`](../../tests/test_forward_only_migrations.py)

- Drives real Alembic: one head, linear chain, `env.py` actually executed.
  [`test_migration_chain.py`](../../tests/test_migration_chain.py)

- Pins the 204-with-no-body contract two deployment configs depend on.
  [`test_http_app.py`](../../tests/test_http_app.py)
