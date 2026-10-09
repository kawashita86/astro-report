# Sprint Change Proposal — 2026-10-09

**Project:** astro-report · **Author:** Developer (correct-course) for Francesco · **Mode:** Batch
**Change scope:** Major (SPEC constraints and non-goals amended, six new capabilities, spine amendments
AD-1, AD-12, AD-15, AD-16, AD-18 and new AD-22, new Epic 11)
**Trigger document:** `change-request-2026-10-09-chart-data-api-for-alerenzi.md`
**Status:** Approved by Francesco 2026-10-09 — document edits §4.1–4.4, §4.6 and the sprint-status / RGD-7 rows applied; §4.7 code-side rows land with their stories. (RGD-6 was already taken by backup handling, so the API decision is RGD-7.)

---

## Section 1: Issue Summary

**Trigger.** The alerenzi shop (*Universo Magico di Ale Renzi*, WordPress plugin `consultation-manager`)
drafts written astrology consultations with an LLM, and today that LLM gets only free-text birth data.
Every planet, house or aspect it writes is invented. Alerenzi's approved CAP-24 / AD-28 make chart data
a port whose responses are computed from a real ephemeris and frozen per consultation. astro-report
already has that engine (vendored, SHA-pinned Swiss Ephemeris, Placidus, `ComputationConfig`, the
Nominatim + historical-offset resolver, the transit engine, Astro.com conformance), but it has no machine
interface: every route is HTML/HTMX behind the operator's session cookie.

**Category.** A new requirement from a stakeholder, the sibling product. It conflicts with five clauses
of astro-report's contract, so it is a correct-course and not a plain story.

**Evidence.**

| Fact | Source |
|---|---|
| Four products need computed data: natal, natal + transits, synastry + composite, solar return + 12-month transits | change request §2 |
| The core transit functions already take any half-open UTC window, and only the runner derives a month | `core/transits/aspects.py::find_transit_aspects(natal_chart, month_start_utc, month_end_utc, config)`; `shell/runner/month.py::client_month_interval_utc` |
| Full-month scan p90 ≈ 0.19 s, so a 12-month window takes about 2–3 s | `docs/release-validation/latency.md` (`month_scan_p90_seconds`) |
| Auth is cookie-only middleware with an exact allowlist plus prefixes, and HTML navigation redirects to `/login` | `shell/http/auth.py` (`AuthMiddleware`, `ALLOWLIST`, `ALLOWLIST_PREFIXES`) |
| OpenAPI and docs pages are already disabled | `shell/http/app.py` (`docs_url=None`, `openapi_url=None`) |
| Only `core/ephemeris/` may touch the Swiss Ephemeris | AD-1; `tests/test_import_boundary.py::test_core_touches_no_facility_outside_ephemeris` |
| `TransitAspectEvent.orb_entry_at` is clamped to the window start, never earlier | `core/types/transits.py` |
| Italian aspect names are not in the Gate vocabulary; they exist only as a display table | `core/gate/vocabulary.it.json` (keys: planets, signs, casa_ordinals, retrogrado, stazionario); `shell/http/stage_view.py` |
| `ComputationConfig` is at `version = 1` | `data/computation.toml` |

## Section 2: Impact Analysis

### Checklist status

| Item | Status | Note |
|---|---|---|
| 1.1 Trigger | [x] | External change request; no astro-report story revealed it |
| 1.2 Problem | [x] | New requirement from a stakeholder |
| 1.3 Evidence | [x] | Table above |
| 2.1 Current epic | [x] | Epic 10 (all stories in `review`) is untouched |
| 2.2 Epic changes | [!] | New Epic 11, six stories |
| 2.3 Remaining epics | [x] | No planned epic is affected; Epics 1–10 keep their scope |
| 2.4 Obsolete or new | [x] | Nothing becomes obsolete; one new epic |
| 2.5 Order | [x] | Epic 11 is independent of Epic 10's review outcome; it starts once this proposal is approved |
| 3.1 PRD | [!] | §8 non-goals, FR-28, new §4.9 (FR-31–FR-36) |
| 3.2 Architecture | [!] | AD-1, AD-12, AD-15, AD-16, AD-18 amended; new AD-22; deployment diagram, source tree, capability map |
| 3.3 UX | [N/A] | No operator screen changes. API error messages follow the Italian-only constraint |
| 3.4 Other | [!] | `computation.toml` v2, `shell/config.py` + README + `.env.example` (`API_TOKEN_HASH`), `AGENTS.md`, `docs/decisions/` RGD-7, Coolify network, `sprint-status.yaml` |
| 4.1 Direct adjustment | Viable | New epic inside the existing structure; Effort Medium, Risk Low–Medium |
| 4.2 Rollback | Not viable | Nothing to revert |
| 4.3 MVP review | Not viable | astro-report's MVP is unchanged; the new scope is additive and isolated from Report generation |
| 4.4 Selected | [x] | Direct adjustment, plus a contract amendment |

### Epic impact

- **Epics 1–10:** no scope or acceptance criteria change. Report generation, the Gate, the Payload and
  every Report-facing constraint keep their exact current meaning.
- **New Epic 11 — Chart data API for the alerenzi plugin:** six stories (§4.6).

### Artifact conflicts

| Contract clause | Conflict | Resolution (decision) |
|---|---|---|
| Non-goal "no techniques beyond natal + monthly transits" | Synastry, composite and solar return are needed | D1: amend. No *Report generation* for them; computation only, for the API |
| Constraint "exact birth time mandatory … no noon chart … anywhere" + AD-16 + non-goal | Alerenzi orders may lack a time | D2 = (B): reduced chart, API only. Client, Natal Chart and Report paths stay exact-time-only |
| Constraint "exactly one principal" + AD-15 + CAP-23 + FR-28 | A machine client authenticates | D3: a service token is an integration credential, not a principal (RGD-7) |
| Constraint "analyzed month is one half-open interval from the local month" + AD-12 | Arbitrary windows are needed | D4: Reports keep the month rule; the API takes any half-open window ≤ 13 months |
| AD-11 / CAP-24 / CAP-27 | Would birth data be stored? | D5: the API is stateless; only `PLACE_CACHE` may grow |

### Technical impact

- **New code:** `shell/http/api/` (router, bearer auth, JSON errors, serialisers); `core/synastry/`
  (inter-aspects, overlays, composite midpoints — pure arithmetic over `NatalChart`); and in
  `core/ephemeris/` (the AD-1 exception): the solar-return instant (`swe.solcross_ut`), the unknown-time
  natal variant (noon chart plus day-range), and composite houses when they are derived from the MC.
- **Changed code:** `AuthMiddleware` gets an `/api/v1` branch; `shell/config.py` gets `API_TOKEN_HASH`;
  `data/computation.toml` goes to v2; the Italian aspect-name table moves from `stage_view.py` to a shared
  shell module.
- **No migration** — the API writes no table except the existing place cache.
- **Thread binding:** API handlers are sync `def` routes that FastAPI runs in its worker threadpool. Every
  new `core/ephemeris/` entry point calls `bind_verified_ephemeris_path_to_current_thread()` first, as
  `compute_natal_chart` already does. Handlers create no threads and never touch the `RunDriver`, so
  `tests/test_concurrency_boundary.py` holds.
- **Config hash churn:** the v2 bump changes `content_hash`. Any test that pins the v1 hash or version is
  updated in the story that bumps it (11.4). Stored Payloads keep recording v1, as intended.

## Section 3: Recommended Approach

**Direct adjustment with a contract amendment:** amend the SPEC, PRD and spine as below, then add Epic
11. The API is a thin, stateless shell surface over the existing pure core plus three new core units. It
shares no state with the Report pipeline, so the Report guarantees (Gate, Payload byte-identity, export
gate) are untouched by construction.

**Decisions taken in this correct-course** (change request §8):

| # | Question | Decision |
|---|---|---|
| D1 | §3.1 non-goal | Amended: synastry, composite and solar return are **computed for the chart data API only**. No Report generation or Gate for them. Progressions, directions and chart patterns stay out |
| D2 | §3.2 unknown birth time | **(B) reduced chart, API only.** Rules in §4.2 (computation-tables). **Exception: `charts/solar-return` requires a known time** and returns `birth_time_required`; see the correction below |
| D3 | §3.3 principal / AGPL | The alerenzi WordPress server is a **machine client of the same business, not a principal**: no UI, no session, no access to stored Client data, stateless computation only. The single human principal is unchanged. Recorded as RGD-7; see AGPL below |
| D4 | §3.4 windows | Any half-open window of local dates in the subject's zone, converted once to UTC, **at most 13 calendar months**. This limit is not an astronomical value: it is a code constant in the API module, not in `computation.toml` and not an env var |
| D5 | §3.5 persistence | **Stateless.** No Client, chart or subject row; no birth data or coordinates in logs. Only `PLACE_CACHE` may grow |
| D6 | §4.5 12-month transits | **Synchronous.** Measured month scan p90 ≈ 0.19 s ⇒ 12 months ≈ 2–3 s, against a 30 s target. Story 11.6 measures on the VPS |
| D7 | §4.6 composite houses | Set by an Astro.com composite fixture in Story 11.4, stored as `[composite] houses` in `computation.toml`. If the fixture shows MC-derived houses, the latitude is the arithmetic mean of the two birth latitudes |
| D8 | §4.9 Style Guide | **Manual export.** No style-guide endpoint. `GET /api/v1/vocabulary/it` is built |
| D9 | Network | **Coolify internal Docker network** (both apps attached to one predefined network; the plugin calls astro-report by its internal hostname over HTTP). Public HTTPS on the production domain is the fallback. Story 11.6 verifies it from the WordPress container |

**Corrections to the change request** (to send back to the alerenzi side):

1. **Solar return with an unknown birth time is not valid.** At noon the natal Sun can be off by up to
   ±0.5°, which moves the return instant by up to ±12 h. The RS ascendant and cusps then swing by up to
   half the zodiac, and the RS Moon by about ±6.5°. The endpoint rejects `time_known: false` with
   `birth_time_required`. The plugin shows "no computed solar return without a birth time", and the
   twelve-month transits (§4.5) remain available in reduced form.
2. **Boundary events.** `orb_entry_at` is clamped to `window_utc.start` (the existing core semantics)
   rather than reported before it. The rule is: `orb_entry_at == window_utc.start` ⇔ already in orb when
   the window opens; `orb_exit_at == null` ⇔ still in orb when it closes. Nothing is dropped. AC 3 is
   restated accordingly (§4.6, Story 11.3).
3. **Module placement.** The solar-return instant, the noon/day-range variant and MC-derived composite
   houses call Swiss Ephemeris, so they live in `core/ephemeris/` (the only AD-1 exception), not in
   `core/returns/`. The pure synastry and composite arithmetic lives in `core/synastry/`.
4. **Vocabulary.** Italian aspect names are not in `core/gate/vocabulary.it.json`. The endpoint serves
   the Gate vocabulary plus the operator-UI aspect-name table, moved into one shared shell module so both
   the UI and the API read it. The Gate vocabulary version is not bumped.
5. **`meta.computation.version`** will be `2` after the bump (it is `1` today), and `orbs.synastry` is
   reported in it.

**AGPL position (RGD-7, Francesco's position of record, not legal advice).** The AGPL chain (Kerykeion
→ pyswisseph → Swiss Ephemeris) obliges a source offer to users who interact with the program over a
network. Shop customers never interact with astro-report. The alerenzi operator does so indirectly,
through the plugin, so astro-report's Corresponding Source is offered to the alerenzi operator, and that
offer is recorded. No offer extends to anyone else. If the plugin ever exposes computed data to shop
customers interactively, this position is revisited.

**Effort:** Medium (six stories; the core reuse is high). **Risk:** Low–Medium. The main risks are the
composite house convention and the unknown-time rules, and fixtures pin both. **Timeline:** independent
of Epic 10's review.

## Section 4: Detailed Change Proposals

### 4.1 SPEC — `_bmad-output/specs/spec-astro-report/SPEC.md`

**Capabilities — append after CAP-30:**

```markdown
- **CAP-31** — Serve chart data to one integration client
  - **intent:** The alerenzi consultation plugin gets astro-report's computed astronomy over a versioned JSON API, so its drafts can name only positions a real ephemeris produced.
  - **success:** `/api/v1` accepts only `Authorization: Bearer` with the one configured token and answers `401` JSON otherwise (never a redirect); the session cookie is not accepted there and the token is not accepted on HTML routes; identical request, ComputationConfig and ephemeris files return a byte-identical body; every chart response carries `meta` (API version, ComputationConfig version, hash and orbs, house system, ephemeris manifest SHA-256, zodiac); errors are `{code, message (Italian), field}`; nothing about a subject is written to the database or to logs, and only the place cache may grow. Mechanism: `ARCHITECTURE-SPINE.md` AD-22.

- **CAP-32** — Resolve a place and compute a natal chart on request
  - **intent:** The plugin resolves a birthplace to confirmed candidates, then gets the natal chart for local birth data without astro-report storing anyone.
  - **success:** `places/resolve` returns every candidate from the CAP-2 resolver, cache first, and `place_unresolved` for none; `charts/natal` converts local date and time with the historical offset, rejects a DST gap or fold as `invalid_request` on `birth_time`, echoes `birth_instant_utc` and `utc_offset`, and returns the same positions, cusps, rulers and aspects as the stored Natal Chart for the same birth data; with `time_known: false` it returns the reduced chart defined in `computation-tables.md`.

- **CAP-33** — Compute transits over an arbitrary window
  - **intent:** A consultation can cover the next three months or the twelve months from a birthday, not only a calendar month.
  - **success:** Any half-open window of local dates in the subject's zone up to 13 calendar months is converted once to UTC and scanned with exactly the Report engine's bodies, orbs and Moon exclusion; the event set equals the union of the month-by-month scans of the same span, with no duplicate or missing perfection, station, ingress or lunation at a month seam; boundary events follow the clamp rule in `computation-tables.md`; a longer window is `window_too_long`.

- **CAP-34** — Compute synastry and the composite chart
  - **intent:** A couple consultation gets both natal charts, their inter-aspects, the house overlays both ways and the midpoint composite.
  - **success:** Inter-aspects cover every pair of A and B points over the five major aspects within `orbs.synastry`; overlays place each person's planets in the other's Placidus houses; the composite uses the shorter-arc midpoint with the documented opposition rule and the configured `[composite] houses` method; results match the Astro.com synastry and composite fixtures; unknown-time omissions follow `computation-tables.md`.

- **CAP-35** — Compute a solar return, at home or relocated
  - **intent:** A solar return consultation gets the return chart for the place the customer spends the birthday, read against the natal chart.
  - **success:** The return instant is the exact solar return nearest the birthday in the requested year; the RS chart is a full Placidus chart at the stated location (the birthplace by default); the comparison gives the RS ascendant's natal house, RS planets in natal houses and RS-to-natal aspects within the natal orb; results match the Astro.com fixtures (birthplace, relocated, a birthday near New Year, a 29 February birthday); an unknown birth time is `birth_time_required`.

- **CAP-36** — Share the Italian vocabulary
  - **intent:** The plugin's prose uses exactly the words astro-report's Gate and operator UI use.
  - **success:** `GET /api/v1/vocabulary/it` returns the Italian names for every id the chart responses use (bodies, signs, aspects, house ordinals, directions), read from the same files the Gate and the UI read.
```

**Constraints — edit:**

OLD:
```
- Exact birth time to the minute is mandatory. No noon chart, solar-house fallback or house-less path exists anywhere in the system.
```
NEW:
```
- Exact birth time to the minute is mandatory for every Client, Natal Chart and Report. No noon chart, solar-house fallback or house-less path exists anywhere in Client creation, Report production or export. The one exception is the stateless chart data API (CAP-32–CAP-34), which may return a reduced, explicitly flagged `time_known: false` chart under the rules in `computation-tables.md`; nothing it computes is stored or reaches a Report. *(Amended 2026-10-09, correct-course.)*
```

OLD:
```
- All computation and storage is UTC. The analyzed month is one half-open UTC interval derived from the Client's local calendar month, so every Transit Event belongs to exactly one Report.
```
NEW:
```
- All computation and storage is UTC. The analyzed month is one half-open UTC interval derived from the Client's local calendar month, so every Transit Event belongs to exactly one Report. The chart data API's transit window is likewise one half-open UTC interval, derived once from local dates in the subject's zone and at most 13 calendar months long. *(Amended 2026-10-09, correct-course.)*
```

OLD:
```
- Exactly one principal, enforced structurally. Adding a second is a revision of this contract, not a feature — it would also trigger the AGPL source-offer obligation the current shape avoids.
```
NEW:
```
- Exactly one principal, enforced structurally. Adding a second is a revision of this contract, not a feature — it would also trigger the AGPL source-offer obligation the current shape avoids. The alerenzi plugin's service token is not a principal: it is one machine credential of the same business, reaches only the stateless `/api/v1` computation surface, and can read no stored Client, chart, Report or Payload. Corresponding Source is offered to the alerenzi operator (`docs/decisions/` RGD-7). *(Amended 2026-10-09, correct-course.)*
```

**Non-goals — edit:**

OLD:
```
- No astrological techniques beyond natal chart and monthly transits — synastry, compatibility, solar returns and progressions are out.
```
NEW:
```
- No Report generation for techniques beyond natal chart and monthly transits. Synastry, the midpoint composite and the solar return are computed for the chart data API only (CAP-34, CAP-35), with no Generator, Gate or Report. Progressions, directions and targeted (relocation-search) solar returns are out. *(Amended 2026-10-09, correct-course.)*
```

OLD:
```
- No support for Clients with an unknown birth time. Rectification, noon charts, solar houses and house-less readings are all out.
```
NEW:
```
- No support for Clients with an unknown birth time. Rectification, noon charts, solar houses and house-less readings are all out of Client creation and Reports. The chart data API's reduced `time_known: false` chart is the only exception (see Constraints). *(Amended 2026-10-09, correct-course.)*
```

Add a non-goal:
```
- No second machine client and no general-purpose public API. `/api/v1` serves the alerenzi plugin only, is absent from any public documentation page, and stores nothing about the subjects it computes.
```

**Header note:** none; the companions list is unchanged.

### 4.2 Computation tables — `_bmad-output/specs/spec-astro-report/computation-tables.md`

Header line: `Governs CAP-3, CAP-6, CAP-7, CAP-9, CAP-10, CAP-11, CAP-12, CAP-13, CAP-32–CAP-35.`

**Orbs — add a row:**

| Orb | Default | Tunable range |
|---|---|---|
| Synastry inter-aspect | ±7.0° | ±6.0° to ±8.0° |

Composite and solar-return aspects (RS chart and RS-to-natal) use the natal Orb.

**Append these sections:**

```markdown
## Synastry and composite (chart data API only)

- **Inter-aspects:** every pair (A point, B point) over the ten planets, both Lunar Nodes, ascendant and midheaven; the five major aspects; the synastry Orb. No applying/separating flag (two static charts).
- **Overlays:** each person's ten planets and nodes placed in the other person's Placidus houses.
- **Composite (midpoint method):** each planet, node, ascendant and midheaven is the midpoint of the two positions on the shorter arc. For an exact opposition (arc = 180°, which has no shorter arc) the midpoint is A's longitude + 90°, normalized. Composite aspects use the natal Orb, with no applying flag.
- **Composite houses:** `[composite] houses` in the ComputationConfig — `midpoint_cusps` (each cusp the shorter-arc midpoint of the two cusps) or `derived_from_mc` (Placidus cusps from the composite MC at the arithmetic mean of the two birth latitudes). Set by the Astro.com composite fixture; changing it is a data edit and a version bump.

## Solar return (chart data API only)

- **Return instant:** the UTC instant when the transiting Sun's tropical longitude equals the natal Sun's, searched from local 00:00 two days before the birthday in the requested year (28 February for a 29 February birthday in a non-leap year), so the nearest return is found.
- **Chart:** a full Placidus chart for that instant at the stated location (the birthplace by default), with RS aspects within the natal Orb.
- **Comparison:** the natal house of the RS ascendant; the natal house of each RS planet and node; RS-to-natal aspects within the natal Orb.
- **Requires a known birth time.** A ±0.5° error in the natal Sun moves the instant by up to ±12 h, which invalidates the RS angles and cusps.

## Unknown birth time (`time_known: false`, chart data API only)

- The chart is computed for 12:00 local civil time on the birth date at the birthplace.
- **Omitted:** ascendant, midheaven, cusps, house rulers, every `house` field, ingresses and lunation houses.
- **Ranged:** every body carries its longitude at local 00:00 and at 24:00 of the birth date as `range`; `sign_uncertain` is true when the two fall in different signs. The Moon (about 13° per day) always carries its range.
- **Excluded from every aspect list** (natal, transit targets, synastry, composite): the angles, and every aspect involving the natal Moon, whose uncertainty (±6.5°) exceeds the transit Orb and rivals the natal Orb.
- **Synastry:** a time-unknown subject contributes no angles and no Moon aspects; overlays *into* that subject's houses are omitted. If either subject's time is unknown, the composite angles, houses and planet houses are null, and composite Moon aspects are excluded.

## API transit windows

The window is local dates `[start_date, end_date)` in the subject's zone, converted once to one half-open UTC interval, and at most 13 calendar months long. Bodies, Orbs and the transiting-Moon exclusion are exactly those of the monthly scan. **Boundary rule:** an aspect already in orb when the window opens is reported with `orb_entry_at` equal to the window's UTC start; one still in orb when it closes has `orb_exit_at` null; a standing retrograde is clamped the same way. Nothing in orb inside the window is dropped.
```

### 4.3 Architecture — `ARCHITECTURE-SPINE.md`

Frontmatter: `updated: '2026-10-09'`; add `binds:` entry `'4.9 Chart Data API (FR-31–FR-36)'`.

**AD-1 — append to Rule:**
```
*(Amended 2026-10-09.)* The solar-return instant (`swe.solcross_ut`), the unknown-time natal variant (noon chart and day range) and MC-derived composite houses are ephemeris reads and live in `core/ephemeris/`; synastry inter-aspects, overlays and composite midpoints are pure arithmetic over `NatalChart` and live in `core/synastry/`. This is not a second exception.
```

**AD-12 — append to Rule:**
```
*(Amended 2026-10-09.)* The chart data API's transit window is one half-open UTC interval derived once in `shell/http/api/` from local dates in the subject's zone (≤ 13 calendar months), passed to the same core functions as a month; local-to-UTC conversion of a subject's birth data happens at the same edge, and a DST gap or fold is rejected, never guessed.
```

**AD-15 — append to Rule:**
```
*(Amended 2026-10-09.)* One machine credential exists besides the operator's session: the alerenzi plugin's bearer token, held as an Argon2 hash in `API_TOKEN_HASH`. It is not a principal. It authenticates only `/api/v1`, which reaches stateless computation and the place cache and no stored Client data. It has no session, no UI and no account row. The AGPL position is recorded in `docs/decisions/` RGD-7. A second machine client or any read of stored data through the API is a PRD revision, as a second principal is.
```

**AD-16 — edit the sentence:**

OLD: `There is no noon chart, no solar-house fallback and no house-less path anywhere in the codebase.`
NEW: `There is no noon chart, no solar-house fallback and no house-less path anywhere in Client creation, Natal Chart storage or Report production. The stateless chart data API's flagged time-unknown variant (AD-22) is the single, separately typed exception: it produces no Client and its types cannot be passed to Payload assembly.` *(Amended 2026-10-09.)*

**AD-18 — append to Rule:**
```
*(Amended 2026-10-09.)* Version 2 adds `orbs.synastry` and `[composite] houses`. The API window maximum is not here: it changes no computed value, so it is a code constant.
```

**New AD-22 (after AD-21):**
```markdown
### AD-22 — The chart data API is a stateless, versioned, token-authenticated computation surface

- **Binds:** FR-31–FR-36, CAP-31–CAP-36
- **Prevents:** a machine interface quietly becoming a second way into Client data, a place where birth data persists or is logged, a source of non-reproducible numbers, or a thread that computes against Moshier.
- **Rule:**
  - **Surface.** `shell/http/api/` mounts `/api/v1`: JSON only, never in an OpenAPI or docs page. A breaking change is `/api/v2`; additive fields are allowed in v1.
  - **Authentication.** `AuthMiddleware` branches on the `/api/` prefix before the cookie check: there it accepts only `Authorization: Bearer`, verified against `Settings.api_token_hash` (Argon2), and answers `401 {code: "unauthorized"}` JSON on anything else, including a valid session cookie. Off that prefix the bearer header is ignored. When `API_TOKEN_HASH` is unset, every `/api/` request is `401`; a malformed value fails startup.
  - **Statelessness.** Handlers call core functions and serialise the result. They write nothing except through the existing place-cache path, construct no `Client`, and log only endpoint, status, duration and ComputationConfig version — never a body, birth data or coordinates.
  - **Determinism.** Bodies are canonical JSON (sorted keys, no insignificant whitespace, `Decimal` as fixed 4-place strings, instants ISO-8601 `Z`), with no timestamp in the body; identical request, ComputationConfig and ephemeris ⇒ identical bytes, asserted by test.
  - **Threads.** Handlers are sync routes run by FastAPI's worker threadpool. Every `core/ephemeris/` entry point they reach binds the verified ephemeris path first. Handlers create no thread, executor or task and never touch the `RunDriver` (`tests/test_concurrency_boundary.py`).
  - **Errors.** Typed core errors map to `{code, message, field}` with an Italian message; codes are `invalid_request`, `birth_time_required`, `place_unresolved`, `window_too_long`, `ephemeris_out_of_range`, `unauthorized`, `internal_error`.
  - **Separation from Reports.** API types (`ChartSubject`, the time-unknown chart, synastry and solar-return results) are distinct from `Client` and `NatalChart` storage. No API result reaches Payload assembly, the Generator or the Gate.
```

**Deployment diagram — add** `W["alerenzi WordPress container<br/>bearer token"]` with `W -->|HTTP, Coolify internal network<br/>/api/v1| R`, and replace the stale Render/Neon labels with Coolify/Netcup (current reality per `AGENTS.md`).

**Source tree — add:** `core/synastry/  # inter-aspects, overlays, composite midpoints (pure)`, `core/ephemeris/returns.py`, `shell/http/api/  # /api/v1, bearer auth, JSON errors [AD-22]`.

**Capability → Architecture map — add row:** `4.9 Chart Data API (FR-31–FR-36) | shell/http/api/, core/synastry/, core/ephemeris/ | AD-1, AD-12, AD-15, AD-16, AD-18, AD-22`.

### 4.4 PRD — `prds/prd-astro-report-2026-08-14/prd.md`

- **New §4.9 "Chart Data API (alerenzi)"** with FR-31–FR-36, each the PRD-voice twin of CAP-31–CAP-36 above (same success criteria), with a lead paragraph: "A stateless JSON surface that lets the alerenzi consultation plugin read astro-report's computed astronomy. It produces no Report and stores no subject. Added 2026-10-09 by correct-course."
- **FR-28 — append:** "One machine credential — the alerenzi plugin's bearer token — reaches only the stateless chart data API (FR-31) and no stored Client data; it is not an account (amended 2026-10-09)."
- **FR-1 — append:** "The chart data API's reduced time-unknown chart (FR-32) creates no Client and is not a degraded path of this requirement."
- **§8 Non-Goals:** the same two edits as the SPEC non-goals (synastry/solar-return bullet; unknown-time bullet), plus the "no second machine client" bullet.
- **§2.2 Non-Users — add:** "The alerenzi consultation plugin is a machine consumer of computed data, not a user (FR-31)."

### 4.5 UX — `EXPERIENCE.md` / `DESIGN.md`

N/A: no operator screen changes. API error `message` strings are Italian, consistent with the existing constraint that everything the operator sees is Italian.

### 4.6 Epics — `epics.md` (append)

```markdown
## Epic 11: Chart data API for the alerenzi consultation plugin

The alerenzi plugin's drafts name only positions a real ephemeris computed: it calls astro-report for natal charts, transit windows, synastry with composite, and solar returns, and stores the frozen responses itself. astro-report stores nothing about those subjects and produces no Report for them.

**FRs covered:** FR-31–FR-36 (new), FR-28 (amended)
**Governed by:** AD-22 (new); AD-1, AD-12, AD-15, AD-16, AD-18 (amended 2026-10-09) · **Unchanged:** AD-2, AD-7, AD-11
**Notes:** Source: `sprint-change-proposal-2026-10-09.md`, `change-request-2026-10-09-chart-data-api-for-alerenzi.md`. Build order: 11.1 → 11.2 → (11.3, 11.4, 11.5 in any order) → 11.6. Astro.com fixtures for 11.4 and 11.5 are transcribed by Francesco and chosen adversarially. When 11.6 is deployed, alerenzi Story 7.6 starts.

### Story 11.1: An authenticated, stateless API skeleton

As the alerenzi plugin,
I want a versioned JSON API that only my token opens,
So that I can call astro-report's engine without a session or a browser.

**Acceptance Criteria:**
- `/api/v1` router under `shell/http/api/`; `AuthMiddleware` branches on `/api/`: bearer only, Argon2 check against `Settings.api_token_hash`, `401` JSON `{code:"unauthorized", message, field:null}`, never a redirect.
- A valid session cookie without a token on `/api/v1/*` → 401; a valid token on an HTML route → treated as unauthenticated (redirect/401 as today).
- `API_TOKEN_HASH` read only in `shell/config.py`; unset ⇒ API answers 401 for everything; malformed ⇒ startup fails. README variable table and `.env.example` updated.
- JSON error envelope with Italian messages for every code in AD-22; typed core errors mapped in one place.
- `meta` block builder (API version, ComputationConfig version/hash/orbs/house system, ephemeris manifest SHA-256, zodiac); canonical JSON serialiser reused from `core/payload/freeze.py`.
- Logging guard: a test proves no request body, birth date, time or coordinate reaches any log record for an API call, with a negative test (`test_the_guard_detects_a_*`) proving the guard fails when a body is logged.
- Tests: no token, wrong token, cookie-only, token on HTML route, API absent from any docs/OpenAPI route.

### Story 11.2: Resolve a place and compute a natal chart on request

As the alerenzi plugin,
I want to resolve a birthplace and get a natal chart for local birth data,
So that the operator confirms the place and the draft gets real positions.

**Acceptance Criteria:**
- `POST /api/v1/places/resolve` → every CAP-2 candidate (display name, lat, lon, IANA zone), cache first; zero ⇒ `place_unresolved`.
- `POST /api/v1/charts/natal`: local date+time → UTC with the historical offset; DST gap or fold ⇒ `invalid_request`, `field: "subject.birth_time"`; response echoes `birth_instant_utc` and `utc_offset`.
- `time_known: true` output equals, field for field, the `NatalChart` that Client creation stores for the same birth data (planets, nodes, angles, cusps with traditional/modern/co-ruler, aspects with orb and applying flag), and matches an existing Astro.com natal fixture.
- `time_known: false` per `computation-tables.md` (noon chart; omissions; `range` and `sign_uncertain`; Moon and angle aspects excluded), implemented as a separate type in `core/ephemeris/`; tested at a sign boundary and with a Moon sign change during the day.
- No row is written except `PLACE_CACHE` (asserted by a row-count test over every table); repeat request ⇒ byte-identical body.

### Story 11.3: Transits over any window up to 13 months

As the alerenzi plugin,
I want the transits for the next three months or for the twelve months from a birthday,
So that a consultation's forecast rests on computed events.

**Acceptance Criteria:**
- `POST /api/v1/charts/transits` with `{subject, window:{start_date,end_date}}`, local dates, half-open, one UTC interval; > 13 calendar months ⇒ `window_too_long`; `end_date ≤ start_date` ⇒ `invalid_request`.
- Response: `meta`, `subject`, `window_utc`, `aspects`, `stations`, `standing_retrogrades`, `ingresses`, `lunations` (with `natal_house`), serialised from the existing core types.
- Seam test: for a 12-month window crossing a retrograde station, every perfection, station, ingress and lunation equals the union of the twelve monthly scans, with none duplicated or missing at a seam; boundary clamp rule per `computation-tables.md`.
- `time_known: false`: ingresses and lunation houses omitted; angle and natal-Moon targets excluded.
- Local timing recorded for a 12-month window (expected ≈ 3 s); the VPS measurement happens in 11.6.

### Story 11.4: Synastry and the midpoint composite

As the alerenzi plugin,
I want both charts, inter-aspects, overlays both ways and the composite,
So that a couple consultation has computed facts.

**Acceptance Criteria:**
- `core/synastry/` pure functions: inter-aspects (`orbs.synastry`), overlays, composite midpoints with the opposition rule (exact-opposition and near-opposition tests); MC-derived composite houses, if chosen, in `core/ephemeris/`.
- `data/computation.toml` → `version = 2` with `orbs.synastry = "7.0"` (loader validates 6.0–8.0) and `[composite] houses`; pinned hash/version tests updated.
- Composite house method set from a transcribed Astro.com composite fixture; synastry fixture covers inter-aspects and both overlays; composite fixture includes a near-opposition pair.
- `POST /api/v1/charts/synastry` response per change request §4.6, with unknown-time omissions per `computation-tables.md`; byte-identical repeat.

### Story 11.5: The solar return, at home or relocated

As the alerenzi plugin,
I want the solar return for the place the customer spends the birthday, read against the natal chart,
So that the annual consultation is computed.

**Acceptance Criteria:**
- `core/ephemeris/returns.py`: return instant via `swe.solcross_ut` from the anchor in `computation-tables.md`; binds the verified ephemeris path first.
- `POST /api/v1/charts/solar-return` with `{subject, year, location?}` (birthplace by default) → `return_instant_utc`, `location`, `chart` (§4.4 shape), `comparison` (`rs_ascendant_in_natal_house`, `rs_planets_in_natal_houses`, `rs_to_natal_aspects`).
- `time_known: false` ⇒ `birth_time_required`.
- Astro.com fixtures: birthplace, relocated, a birthday near New Year, a 29 February birthday.

### Story 11.6: Vocabulary, API notes for the plugin team, and deployment

As Francesco,
I want the API live on the VPS and reachable from the WordPress container,
So that alerenzi Story 7.6 can start.

**Acceptance Criteria:**
- `GET /api/v1/vocabulary/it` serves the Gate vocabulary plus the aspect and direction names, read from one shared shell module that the operator UI also reads (no second copy).
- `docs/api/chart-data-v1.md`: endpoints, request/response shapes, error codes, determinism, the boundary and unknown-time rules, and the version policy — for the alerenzi team.
- `API_TOKEN_HASH` set in Coolify; the astro-report and WordPress containers attached to one Coolify network; a call from the WordPress container to the internal hostname succeeds (public HTTPS fallback documented).
- 12-month `charts/transits` timed on the VPS (p90 over 20 calls) and recorded in `docs/release-validation/latency.md`; target ≤ 30 s.
- `docs/decisions/` RGD-7 (service token is not a principal; AGPL source offer to the alerenzi operator) recorded.
```

### 4.7 Other artifacts

| Artifact | Change | Lands with |
|---|---|---|
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | Add `epic-11: backlog`, stories `11-1-…` to `11-6-…` as `backlog`, `epic-11-retrospective: optional` | On approval |
| `docs/decisions/README.md` | RGD-7: service token is an integration credential, not a principal; AGPL source offer to the alerenzi operator | On approval |
| `AGENTS.md` (outside the `bmad:context` block) | Conventions: `/api/v1` is bearer-only and stateless; no birth data in logs; `core/ephemeris/` holds every new swe call | Story 11.1 |
| `README.md`, `.env.example` | `API_TOKEN_HASH` row | Story 11.1 |
| `data/computation.toml` | v2: `orbs.synastry`, `[composite] houses` | Story 11.4 |
| `shell/http/stage_view.py` | Italian aspect-name table moves to a shared shell module | Story 11.6 |
| Coolify | Shared network; `API_TOKEN_HASH` env | Story 11.6 |
| alerenzi side | Corrections 1–5 in §3 sent back (solar return needs a time; clamp rule; module placement; vocabulary source; config v2) | On approval |

## Section 5: Implementation Handoff

**Scope: Major.** The contract amendments (SPEC, PRD, spine) are PM/Architect-level. In this project
Francesco holds those roles, and the document edits in §4.1–4.4, §4.6 and the sprint-status/RGD-7 rows
are applied by the Developer agent on approval, as in the 2026-10-01 proposal.

| Role | Responsibility |
|---|---|
| Francesco (PM/Architect) | Approve this proposal; transcribe the Astro.com fixtures for 11.4 and 11.5 (synastry, composite with a near-opposition, two solar returns incl. New Year and leap day) and a 12-month window crossing a station for 11.3; confirm RGD-7; set the token in Coolify |
| Developer agent | Apply the document edits; build Stories 11.1–11.6 with `bmad-build` in order; run the real-Postgres checks before pushing (no migration expected, but the row-count test runs there too) |
| alerenzi side | Receive corrections 1–5; start Story 7.6 when 11.6 is deployed |

**Success criteria.** The eight cross-repo acceptance criteria of the change request §7, with AC 3 read
as "event set equals the union of monthly scans, with the clamp rule at the window edges", and AC 7 as
"time-unknown behaviour (B), tested both ways, with solar return rejecting it".
