# Epic 11 Context: Chart data API for the alerenzi consultation plugin

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Expose the existing engine as a machine interface for one client, the alerenzi WordPress plugin, so its AI-drafted consultations name only positions a real ephemeris computed. The plugin requests natal charts, transit windows, synastry with composite and solar returns, then stores the frozen responses itself. astro-report stores nothing about those subjects and produces no Report for them. alerenzi Story 7.6 starts once this epic is deployed.

## Stories

- Story 11.1: An authenticated, stateless API skeleton
- Story 11.2: Resolve a place and compute a natal chart on request
- Story 11.3: Transits over any window up to 13 months
- Story 11.4: Synastry and the midpoint composite
- Story 11.5: The solar return, at home or relocated
- Story 11.6: Vocabulary, API notes for the plugin team, and deployment

## Requirements & Constraints

- JSON API under `/api/v1`, versioned: breaking change means `/api/v2`, additive fields are allowed in v1. Never in any OpenAPI or docs page.
- Bearer-token auth only on `/api/`; session cookies are not accepted there and the bearer token is ignored on HTML routes. Failures are always JSON `401`, never a redirect.
- Stateless: no Client, chart or birth data written to the database or logs. Only the place cache may be filled. Logs carry endpoint, status, duration and computation version only.
- Deterministic: identical request, ComputationConfig and ephemeris give byte-identical bodies, with no timestamp in the body.
- Every chart response carries a `meta` block: API version, ComputationConfig version, hash, orbs and house system, ephemeris manifest SHA-256, zodiac.
- Error envelope `{code, message, field}` with Italian messages. Codes: `invalid_request`, `birth_time_required`, `place_unresolved`, `window_too_long`, `ephemeris_out_of_range`, `unauthorized`, `internal_error`.
- Input is local civil birth date and time plus a resolved place. It is converted to UTC with the historical offset. A DST gap or fold is `invalid_request` with `field: "subject.birth_time"`, never a silent guess.
- Unknown birth time is supported for the API only (`time_known: false`): a noon chart with no angles, houses or house-dependent outputs, and the Moon carried as a range. Report generation stays exact-time-only. Solar return with unknown time is `birth_time_required`.
- Transit windows are local dates, half-open, converted to one UTC interval, at most 13 calendar months (`window_too_long`). The maximum is a code constant, not config.
- Angles are 4-place decimal strings in `[0, 360)`. Bodies, signs, aspects and directions use the glossary ids verbatim, with no synonyms. Italian names come only from the vocabulary endpoint.
- No second engine and no third-party API. Out of scope: targeted solar return, progressions, chart patterns, report generation and Oroscopo Personale.

## Technical Decisions

- AD-22 governs the epic. `shell/http/api/` mounts the router, and `AuthMiddleware` branches on the `/api/` prefix before the cookie check.
- `API_TOKEN_HASH` (Argon2) is read only in `shell/config.py`. Unset means every API call is `401`. A malformed value fails startup.
- Handlers are sync routes on FastAPI's threadpool. They create no thread, executor or task and never touch the `RunDriver`. Every `core/ephemeris/` entry point they reach binds the verified ephemeris path first (a known pitfall, missed twice).
- API types are separate from `Client` and `NatalChart` storage. No API result reaches Payload assembly, the Generator or the Gate.
- `core/` stays pure. New pure code goes in `core/synastry/` (inter-aspects, overlays, composite midpoints) and `core/ephemeris/` (`returns.py` using `swe.solcross_ut`, the time-unknown chart type). Typed errors are raised from `core/errors.py` and mapped to HTTP in one place in the shell.
- `data/computation.toml` goes to `version = 2`: `orbs.synastry = "7.0"` (valid 6.0–8.0) and `[composite] houses`. The composite house method is chosen by a transcribed Astro.com fixture. Pinned hash and version tests are updated.
- Composite planets are midpoints on the shorter arc, with a documented deterministic rule for exact opposition. Composite aspects use the natal orb. The composite needs both birth times.
- Canonical JSON serialiser is reused from `core/payload/freeze.py`.
- Conformance: adversarially chosen Astro.com fixtures, transcribed by Francesco, for synastry, composite (including a near-opposition pair), solar returns (birthplace, relocated, near New Year, 29 February) and a 12-month transit window across a retrograde station.
- New syntactic guards ship with `test_the_guard_detects_a_*` negative tests. Anything involving rows uses `fk_enforcing_engine()` from `tests/_fk.py`. No migration is expected, and any added one is forward-only.

## Cross-Story Dependencies

- Build order: 11.1, then 11.2, then 11.3, 11.4 and 11.5 in any order, then 11.6.
- 11.2 provides subject parsing, local-to-UTC conversion and the time-unknown type reused by 11.3–11.5.
- 11.3's 12-month result must equal the union of the monthly scans.
- 11.6 serves the Gate vocabulary from one shared shell module the operator UI also reads. It also carries regenerated-and-drift-tested example responses, the VPS latency measurement (p90 ≤ 30 s), the Coolify network and hostname hand-off to alerenzi, and RGD-7.
