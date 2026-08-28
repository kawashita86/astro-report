<!-- bmad:context -->
<!-- Verified 2026-08-28 against ce6767b. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## astro-report

Natal charts, monthly transits and grounded eight-section Italian reports for a single
operator. Python 3.13 (`uv`), FastAPI with Jinja2/HTMX templates, SQLModel on Postgres,
Alembic migrations; deployed as one Render web service against Neon Postgres. `core/` is a
pure functional core; `shell/` is everything imperative and imports `core/`, never the
reverse. The canonical build contract is `_bmad-output/specs/spec-astro-report/SPEC.md`;
deeper design and planning live under `_bmad-output/`.

## Policy

- Work directly on `main` — no feature branches, no PRs. `render.yaml` auto-deploys every
  commit and CI does not block it, so run `uv run pytest` locally before pushing.
- Migrations are forward-only: never fill in a `downgrade()` body, never run
  `alembic downgrade`. Correct a bad migration with a new forward one.
  `tests/test_forward_only_migrations.py` enforces this, generator template included.
- Never hand-edit `data/ephemeris/*.se1` or its `SHA256SUMS` — vendored and
  identity-checked at startup.

## Where things are

- Changing computed or generated behavior, or any FR-level feature:
  `_bmad-output/specs/spec-astro-report/SPEC.md` is the contract; companions
  `computation-tables.md` (orbs, house system, rulers, aspect tuning) and `sections.md`
  (the eight-Section contract) win over any doc that restates them.
- Structural or architectural changes:
  `_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md`
  (the `AD` invariants) and its `BUILD-ORDER.md`.
- Every environment variable is read only in `shell/config.py` and validated at startup;
  astronomical tuning values are not env vars — they live in `data/computation.toml` as a
  `ComputationConfig`.

## Running and verifying

- `uv run pytest` runs store and adapter tests against in-memory SQLite, which ignores
  `VARCHAR(n)` lengths and foreign keys. `tests/test_migration_chain_on_postgres.py` is the
  only real-Postgres check and skips unless `MIGRATION_TEST_DATABASE_URL` points at a
  throwaway database — run it against real Postgres before pushing a migration (schema bugs
  have shipped green three times without it).

## Conventions that differ from defaults

- `core/` never imports `shell/`; outside `core/ephemeris/`, `core/` touches no filesystem,
  network, clock, environment or randomness. Design pure functions — data in, data out.
  `tests/test_import_boundary.py` enforces it syntactically.
- Only `shell/config.py` reads the environment; every other module takes a `Settings`
  object. No module or package is named `utils`, `helpers`, or `common` anywhere. Both
  enforced by the boundary tests.
- Every module opens with a prose docstring explaining why it exists, not what it does.
- Every function and method is fully type-hinted.
- Every syntactic-guard test ships negative tests proving the guard can fail
  (`test_the_guard_detects_a_*`) — add them alongside any new guard.
- New store or cascade tests use `fk_enforcing_engine()` / `fk_enforcing_session()` from
  `tests/_fk.py`, never a bare `create_engine("sqlite://")` — FK enforcement is off by
  default in SQLite and a wrong delete order passes silently.

## Known pitfalls

- The Swiss Ephemeris path (`swe.set_ephe_path`) is process-global C state, not per-module
  or per-thread. Any new code path that computes a chart must set the verified vendored
  path for its own thread (see `core/ephemeris/identity.py`; tests re-pin it via an autouse
  fixture in `tests/conftest.py`). Missed twice — epic-3 retro item 22 and commit `ce6767b`.

<!-- /bmad:context -->
