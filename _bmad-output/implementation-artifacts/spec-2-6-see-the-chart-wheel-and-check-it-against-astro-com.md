---
title: 'See the chart wheel and check it against Astro.com'
type: 'feature'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '63eab714fef8732483d655170422db9a891b376a'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Client's Natal Chart (Story 2.2, persisted by Story 2.3) is stored but invisible --
Francesco has no way to eyeball planetary positions, house cusps and natal Aspects against Astro.com
before trusting anything built on it.

**Approach:** A new authenticated `GET` route in `shell/http/` loads a Client's stored
`StoredNatalChart`, maps it into Kerykeion's chart-drawing model (positions only -- Kerykeion never
recomputes them), and renders the resulting SVG wheel inline in a minimal HTML page for Francesco's
own verification.

## Boundaries & Constraints

**Always:**
- The route lives in `shell/http/` (presentation, not `core/`) -- ARCHITECTURE-SPINE.md's FR-5 row
  names this exact split and mandates Kerykeion's SVG renderer for it.
- Authenticated by default via the existing `AuthMiddleware` -- nothing added to
  `shell.http.auth.ALLOWLIST`.
- Wheel positions come only from the Client's stored `NatalChart` (ascendant, midheaven, planets,
  houses) -- no recomputation of positions, cusps or ascendant/midheaven via Kerykeion's own subject
  factory. Kerykeion's `AstrologicalSubjectModel` and its `KerykeionPointModel`s are built directly
  from stored fields via `kerykeion.utilities.get_kerykeion_point_from_degree()`.
- `kerykeion` (verified installable as `kerykeion==5.12.9`, no conflict with pinned
  `pyswisseph==2.10.3.2`) is added as a new `pyproject.toml` dependency, used only from `shell/http/`.
- Aspects shown are `kerykeion.chart_data_factory.ChartDataFactory.create_natal_chart_data()`'s own
  recomputation over these identical mapped positions, configured with this project's aspect set/orb
  (`ComputationConfig.orbs.natal`, read from `request.app.state.computation_config`) via its
  `active_aspects` parameter -- not a re-serialization of `chart.aspects`. Same geometry, same orb, same
  five aspect types, so the result is equivalent; hand-building the element/quality distributions
  `SingleChartDataModel` also requires would only duplicate what the factory already computes as a
  byproduct.
- Body-name mapping to Kerykeion's `AstrologicalPoint` literal: `true_node` ->
  `True_North_Lunar_Node`, `south_node` -> `True_South_Lunar_Node`, every other stored name ->
  `.capitalize()`.

**Ask First:** none anticipated.

**Never:**
- No Report or export route ever reaches this view (FR-5) -- it is Francesco's own verification tool
  only, and nothing built by this story links to it from an exported artifact.
- No new domain error type -- an unknown Client id, or a Client with no stored chart, is a plain 404.
- No persistence -- this route only reads.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Client with a stored chart | `GET /clients/{id}/chart`, authenticated | 200; HTML page with an inline SVG wheel showing all planets, the 12 house cusps, and natal Aspects | N/A |
| Unknown client id | `GET /clients/{id}/chart`, id not in DB | 404 | plain 404, no chart data touched |
| Unauthenticated request | No/invalid session cookie | 401 | existing `AuthMiddleware` default |
| Retrograde planet | A stored `PlanetPosition` with `retrograde=True` | The mapped point carries a negative `speed`, matching Kerykeion's retrograde convention | N/A |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `core/types/chart.py:20,42,86` -- `PlanetPosition`, `HouseCusp`, `NatalChart` -- the stored shapes
  this route reads; no changes.
- `shell/adapters/postgres/client.py:31,51` -- `Client`, `StoredNatalChart` -- DB rows selected by
  `client_id`; `planets`/`houses` are JSON with every `Decimal` serialized to `str` (parse back with
  `Decimal(...)` before building Kerykeion points).
- `shell/http/app.py:61` (`get_session`), `:74-102` (`create_app`) -- the session dependency to reuse,
  and where the new router must be `include_router()`-ed, mirroring `clients_router`.
- `shell/http/routes/clients.py:42-43,151-167` -- `Jinja2Templates` setup and the
  `Depends(get_session)` route pattern this new route follows.
- `shell/http/templates/client_new.html` -- the plain server-rendered HTML convention (no CSS
  framework, no JS) the new template matches.
- `core/types/computation.py:32-38` (`Orbs`) -- `ComputationConfig.orbs.natal`, the single configured
  Orb this route reads via `request.app.state.computation_config` (set in `shell/http/app.py`).
- `_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md:435`
  -- the FR-5 row mandating Kerykeion's SVG renderer, called from `shell/http/`.
- `kerykeion` (new dependency, v5.12.9):
  - `kerykeion.schemas.kr_models.AstrologicalSubjectModel` -- built directly; `city`/`nation` are
    placeholders (never Client-facing), `lat`/`lng`/`tz_str` from the `Client` row.
  - `kerykeion.utilities.get_kerykeion_point_from_degree(degree, name, point_type, speed=...)` --
    builds one `KerykeionPointModel` per stored longitude; `.house` set afterward via
    `kerykeion.utilities.get_house_name(number)`.
  - `kerykeion.chart_data_factory.ChartDataFactory.create_natal_chart_data(subject, active_aspects=...)`
    -- produces the `ChartDataModel` from the manually-built subject.
  - `kerykeion.charts.chart_drawer.ChartDrawer(chart_data).generate_svg_string()` -- the SVG string
    embedded in the template.

**To create:**
- `shell/http/chart_wheel.py` -- `build_subject(client, chart) -> AstrologicalSubjectModel`,
  `active_aspects(orb: Decimal) -> list[ActiveAspect]` -- isolates the Kerykeion-shape translation
  from the route handler.
- `shell/http/routes/chart.py` -- `GET /clients/{client_id}/chart` -- loads `Client` +
  `StoredNatalChart` by id, 404s if either is missing, calls `chart_wheel.py`, renders the template.
- `shell/http/templates/chart_wheel.html` -- minimal page embedding `{{ svg | safe }}`.
- `tests/test_http_chart_wheel.py` -- one test per I/O matrix row.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml` -- add `kerykeion==5.12.9` -- required for SVG rendering (ARCHITECTURE-SPINE.md FR-5)
- [x] `shell/http/chart_wheel.py` -- create -- maps `StoredNatalChart`/`Client` into Kerykeion's subject, active-aspects config and SVG string -- AC1
- [x] `shell/http/routes/chart.py` -- create -- `GET /clients/{client_id}/chart` route -- AC1, AC3
- [x] `shell/http/app.py` -- register the new router -- wires the route in, mirrors `clients_router`
- [x] `shell/http/templates/chart_wheel.html` -- create -- embeds the SVG, no export/download affordance -- AC3
- [x] `tests/test_http_chart_wheel.py` -- unit-test the I/O matrix rows -- AC1-AC3

**Acceptance Criteria:**
- Given a Client with a stored Natal Chart, when Francesco opens the chart wheel, then it shows
  planetary positions, house cusps and natal Aspects, all read from the stored chart's positions.
- Given the wheel route, when the codebase is inspected, then its rendering logic lives entirely in
  `shell/http/`, never in `core/`.
- Given any Client-facing artifact this or a later story produces, when it is inspected, then no route
  or template reaches the chart wheel from it.

## Spec Change Log

## Design Notes

Kerykeion recomputes Aspects on the mapped positions rather than re-displaying `chart.aspects`
verbatim. Since the positions, Orb and five-aspect set are identical to what produced the stored
Aspects, the recomputed set is geometrically equivalent -- and this avoids hand-building the
element/quality distributions `SingleChartDataModel` requires as a side channel just to inject a
precomputed Aspect list, which `ChartDataFactory.create_natal_chart_data()` already produces as a
byproduct of its own aspect pass.

## Verification

**Commands:**
- `uv run pytest tests/test_http_chart_wheel.py` -- new tests green
- `uv run pytest` -- full suite green
- `uv run ruff check .` -- clean

**Manual checks (if no CLI):**
- Create a Client via `/clients/new`, then open `/clients/{id}/chart` in a browser; compare the
  rendered wheel's planet signs/houses and Aspects against Astro.com for the same birth data.

## Suggested Review Order

**The route: authenticated read, plain 404s**

- Entry point: loads the Client and its stored chart, 404s on either miss, hands both to the mapper below.
  [`chart.py:44`](../../shell/http/routes/chart.py#L44)

- No new domain error -- an unknown Client or a chart-less Client is the same plain 404.
  [`chart.py:49`](../../shell/http/routes/chart.py#L49)

- Kerykeion's own recomputation over the mapped positions, configured to this project's orb -- not a re-serialization of `chart.aspects`.
  [`chart.py:59`](../../shell/http/routes/chart.py#L59)

**Mapping stored data into Kerykeion's shape**

- Entry point: builds the Kerykeion subject directly from stored fields -- Kerykeion never recomputes a position itself.
  [`chart_wheel.py:72`](../../shell/http/chart_wheel.py#L72)

- Client name is escaped before reaching Kerykeion, since it embeds the value unescaped into the SVG's own `<title>` -- closes a stored-XSS path found in review.
  [`chart_wheel.py:132`](../../shell/http/chart_wheel.py#L132)

- Body-name mapping to Kerykeion's literal: the two lunar nodes are special-cased, everything else matches by capitalization.
  [`chart_wheel.py:57`](../../shell/http/chart_wheel.py#L57)

- House cusps keyed onto `AstrologicalSubjectModel`'s twelve fixed field names.
  [`chart_wheel.py:112`](../../shell/http/chart_wheel.py#L112)

- Ascendant/Medium Coeli added to `active_points` -- without this the angles silently don't render.
  [`chart_wheel.py:122`](../../shell/http/chart_wheel.py#L122)

- This project's five-Aspect set, each at the configured natal Orb.
  [`chart_wheel.py:185`](../../shell/http/chart_wheel.py#L185)

**Wiring**

- The new router registered alongside the existing `/clients` router.
  [`app.py:104`](../../shell/http/app.py#L104)

- `kerykeion==5.12.9` added as a new dependency, verified against the pinned `pyswisseph`.
  [`pyproject.toml:12`](../../pyproject.toml#L12)

**Peripherals**

- Minimal page embedding the SVG inline, no export/download affordance.
  [`chart_wheel.html`](../../shell/http/templates/chart_wheel.html#L12)

- Position-correctness check: reads Kerykeion's own rendered attribute back and compares it to the stored longitude, so a swapped-index bug can't pass silently.
  [`test_http_chart_wheel.py:100`](../../tests/test_http_chart_wheel.py#L100)

- The XSS regression: a Client name containing markup renders escaped, not raw.
  [`test_http_chart_wheel.py:227`](../../tests/test_http_chart_wheel.py#L227)

- Remaining I/O matrix coverage: unknown Client, chart-less Client, unauthenticated request, retrograde mapping.
  [`test_http_chart_wheel.py:248`](../../tests/test_http_chart_wheel.py#L248)
