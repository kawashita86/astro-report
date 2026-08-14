# Epic 1 Context: A private application I can sign into, with correctness guardrails that cannot be retrofitted

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Stand up the project from nothing — there is no starter template and no source code yet — so that a locked-down application boots on its production host against its production database, reachable only by its single operator. Alongside the skeleton, put the three mechanical guardrails in place *before* any astronomy is written: the enforced purity boundary between pure computation and everything that touches the world, the checksum-pinned ephemeris that refuses to boot if its identity has changed, and the conformance fixture harness with its first adversarially-chosen reference charts. Each of these is worth nothing if retrofitted — a Placidus or ephemeris error caught in week two is a fix, the same error caught in week ten is a rewrite of everything layered on top. This epic also establishes the single home for every astronomical tuning value, so nothing downstream invents a second one.

## Stories

- Story 1.1: A deployable application skeleton
- Story 1.2: The purity boundary, enforced by a test rather than by discipline
- Story 1.3: An ephemeris whose identity is asserted before the application serves anything
- Story 1.4: Sign in as the only person who can reach this application
- Story 1.5: One home for every astronomical tuning value
- Story 1.6: A conformance harness that runs before there is anything to conform
- Story 1.7: Reference charts chosen to break the computation, not to flatter it

## Requirements & Constraints

- **Single principal, structurally.** No Client data, Report, Payload or chart wheel is reachable without authenticating — including via error messages and error bodies. A session survives a multi-hour working batch without re-authentication. There is no users table, no account creation, no invitation flow, no password reset for others, and no role distinction. Adding a second principal is a contract revision, not a feature (it would also trigger the AGPL source-offer obligation the current shape avoids).
- **Zero running cost.** Every component sits inside a free tier at the target volume of 30–200 Reports per month. A design requiring paid infrastructure at that volume must be raised, not absorbed.
- **EU/EEA hosting and storage** wherever the chosen free tier offers the choice.
- **Availability is best-effort.** No SLA; an hour of downtime is an inconvenience.
- **Conformance is a release gate.** No Report reaches a Client before computed output matches the Astro.com benchmark across the full reference set. This epic builds the mechanism, not the passing result.
- **Determinism is the reason the guardrails exist.** The same code must produce the same numbers on every run and every deployment — a station or cusp crossing landing on the wrong day is the deliverable failing.

## Technical Decisions

**Paradigm — functional core, imperative shell.** `core/` holds only pure functions; `shell/` holds everything touching the world. The dependency rule is one-directional and absolute: `shell/` imports `core/`, `core/` never imports `shell/`. This is enforced by `tests/test_import_boundary.py` running on every change in CI, not by discipline — the rule exists only while the test does. It must also fail on any network, clock, filesystem or environment facility imported under `core/`. **The single declared exception** is the ephemeris: pyswisseph/Kerykeion read the vendored `.se1` files from disk inside `core/ephemeris/`. A second exception is a spine amendment, not a judgement call.

**Source tree to create.** `core/` with `types/`, `errors.py`, `ephemeris/`, `transits/`, `domains/`, `payload/`, `memory/`, `gate/`. `shell/` with `config.py`, `ports/`, `adapters/`, `runner/`, `http/`. Plus `data/` (ephemeris files, `computation.toml`, `sections.toml`, `style-guide.seed.md`), `migrations/`, `tests/`. **No module named `utils`, `helpers` or `common` anywhere.** Modules are `snake_case` and a module's name states its stage.

**Ephemeris identity.** `sepl_18.se1` and `semo_18.se1` are vendored with SHA-256 checksums pinned from the files actually downloaded. The shell calls `swe.set_ephe_path()` explicitly at startup and verifies each file; a missing file or mismatch means the application refuses to start and names the failing file. The Moshier fallback is never an accepted runtime state under any configuration. The verified identity must be exposed as a value later stories persist alongside computed output.

**Configuration.** `shell/config.py` is the only reader of the environment, validated into a frozen settings object at startup; no other module touches `os.environ`. Startup fails loudly on a missing or invalid setting. Separately, `data/computation.toml` is the single versioned home for orbs (natal ±7.0°, range 6.0–8.0; transit-to-natal ±2.0°, range 1.5–2.5), house system (Placidus), fast/slow body sets, traditional and modern Ruler tables, and the harmonic/disharmonic classification table. It carries an integer version and content hash, loads into a frozen `ComputationConfig`, and is **passed explicitly as an argument** into every core function that needs it — never read ambiently. Out-of-range values fail loading with a typed domain error naming the offender.

**Conventions binding from story one.** Typed domain errors from a single `core/errors.py`; core never returns `None` to mean failure and never imports an HTTP status code. Core values are frozen dataclasses that never mutate their input; all writes live in `shell/adapters/postgres/`. UUIDv7 primary keys. Timezone-aware UTC everywhere, ISO-8601 with explicit `Z` — a naive datetime crossing any boundary is a defect. Angles as `Decimal`, never binary float. Alembic migrations forward-only, one per change, applied at deploy before traffic is accepted. Structured logging that never carries birth data, names or Report prose — an identifier only. Domain vocabulary is used verbatim and untranslated; the four domains stay Italian and lowercase (`amore`, `lavoro`, `denaro`, `benessere`).

**Durability posture.** All durable state lives in Postgres. The container filesystem carries only vendored ephemeris, templates and application code; nothing written at runtime is ever read back after a restart.

**Stack seed.** Python 3.13 with `uv` and a committed lockfile · FastAPI · Jinja2 + HTMX 2.x (pinned deliberately — 4.0 replaces the XHR transport and is not a drop-in) · SQLModel · Alembic · argon2-cffi · PostgreSQL on Neon (Europe/Frankfurt) · Render web service, free plan, EU region. Two environments only: local (Docker Compose, local Postgres) and production. No staging.

**Route authentication.** Every route is authenticated by default; the allowlist of unauthenticated routes is declared in exactly one place and covered by a test that fails if any route outside it is reachable anonymously.

**Conformance harness shape.** A runner walks `tests/conformance/fixtures/` and compares computed output against transcribed Astro.com values. The fixture format records birth data, expected planetary positions, house cusps, natal Aspects, and — for month fixtures — expected Transit Events, plus which adversarial case each fixture targets. An empty fixture set must report zero fixtures and succeed, not fail. A mismatch names the fixture, the field, the expected value and the computed value. The harness ships empty and fills as later epics land.

## UX & Interaction Patterns

No UX design contract exists for this project — interface work is derived from requirement consequences and the fixed presentation stack (FastAPI + Jinja2 server-rendered templates with HTMX 2.x; no SPA, no native app). The only surface this epic needs is sign-in with a session that survives a working batch.

## Cross-Story Dependencies

- Story 1.1 (skeleton, config, deployment) precedes everything; 1.2's directory structure and 1.4's config-driven auth both build on it.
- Story 1.3's exposed ephemeris identity is consumed by Epic 3's Report Payload, which records it.
- Story 1.5's `ComputationConfig` is a dependency of essentially every later core function (Epics 2, 3, 5) — it deliberately holds no logic and drives no computation in this epic.
- Story 1.6 (the runner) must land before Story 1.7 (the fixtures) has anywhere to go; both must precede Epic 2, which is validated against them.
- **Story 1.7 needs Francesco, not a developer, and sits on the critical path.** At least three transcribed charts must exist before Epic 2 begins; starting it on day one is deliberate. The full adversarial set covers a leap-day birth, births minutes either side of a historical DST switch, a near-midnight birth, a month containing a retrograde station, a month with two Lunations of one kind, and one with none.
- Client deletion (FR-29) was originally scheduled here but **moved to Epic 2**: no Client table exists until then, so a cascade written here would have nothing to cascade over. Every later story creating a table that references a Client carries an acceptance criterion that it joins that cascade.
- Epic 8 (release validation) closes against the harness built here.
