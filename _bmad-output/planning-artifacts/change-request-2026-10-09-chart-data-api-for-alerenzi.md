# Change request: chart data API for the alerenzi consultation plugin (2026-10-09)

Input for `bmad-correct-course` in this repository. Written from the alerenzi side (the WordPress shop *Universo Magico di Ale Renzi*, plugin `consultation-manager`). It describes what that plugin needs from astro-report, why, what is already decided over there, and which parts of astro-report's own contract it touches. Astro-report's SPEC, spine and conventions still decide how it is built.

Upstream references (alerenzi repository, `/home/francesco/PhpstormProjects/alerenzi`):

- `_bmad-output/planning-artifacts/change-request-2026-10-09-prompts-and-knowledge.md`, §5 (astrology)
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-09.md` (approved): CAP-24, AD-28, Story 7.6
- `_bmad-output/planning-artifacts/architecture/architecture-alerenzi-2026-09-04/ARCHITECTURE-SPINE.md`: AD-28 "Chart data is a port; responses are frozen per consultation"

## 1. Why

The shop sells written astrology consultations. A WordPress plugin drafts each report with an LLM, and Alessandro reviews and approves it before it is sent. Today the LLM has only the customer's birth data as free text, so any planet, house or aspect it writes is invented. The plugin's rule (CAP-24) is that **the AI never computes astronomy**. Positions come from a real ephemeris, are stored with the consultation, and the AI may name only what is in that stored data. This is the same principle as astro-report's Groundedness Gate, applied in a different product.

astro-report already has the engine: pyswisseph with vendored, SHA-pinned ephemeris files, Placidus houses, `ComputationConfig` with version and hash, Nominatim geocoding with historical UTC offsets, transit aspects with exact perfection, stations, ingresses and lunations, and an Astro.com conformance harness. It has no machine interface: every route is an HTML/HTMX page behind the single operator's session cookie. Writing a second engine in PHP, or buying a third-party API, was considered and rejected:

- A third party would hold customer birth data and use settings different from astro-report's.
- A second engine would fork the conformance work.

## 2. Products that need data

| Product (alerenzi id) | Data the plugin needs |
|---|---|
| Tema Natale (10832) | Natal chart of one person |
| Consulenza astrologica (10823) | Natal chart + transits "now" (a window around the order date, e.g. the next 3 months) to answer the customer's question |
| Sinastria di Coppia (10839) | Both natal charts + synastry: inter-aspects, house overlays both ways, **composite chart** (midpoint method) |
| Rivoluzione Solare Annuale (10854) | Solar return for the year, **cast where the customer spends the birthday** (the birthplace by default, otherwise a place the customer states), read against the natal chart, **plus transits for the twelve months from the birthday** |

Out of scope:

- **Targeted solar return (RSMA, "rivoluzione solare mirata"):** searching for places that improve the year. This was decided on 2026-10-09 and is not sold.
- Progressions, directions, chart patterns.
- **Report generation:** the plugin writes its own prose and does not use astro-report's Generator, Gate, Style Guide runs or Reports.
- **Oroscopo Personale (10846):** keeps being produced *in* astro-report by hand. The API does not touch that flow.

## 3. Conflicts with astro-report's contract (need decisions in correct-course)

These are the reason this is a correct-course and not a plain story. Each comes with a recommendation from the alerenzi side; astro-report's owner decides.

### 3.1 Non-goal: "synastry, compatibility, solar returns and progressions are out"

**Needed:** synastry (with composite) and solar return, computed only. No report generation and no Gate for these.

**Recommendation:** amend the non-goal to "No *report generation* for techniques beyond natal chart and monthly transits. Synastry, composite and solar return are computed for the chart data API only." Progressions stay out. Chart-pattern detection stays out.

### 3.2 Constraint: "Exact birth time to the minute is mandatory. No noon chart, solar-house fallback or house-less path exists anywhere in the system."

**Conflict:** alerenzi's product pages say the birth time is optional ("se non la conosci puoi lasciarla vuota"). Some orders will arrive without it.

**Options:**

- **(A) Keep the constraint.** The API rejects an unknown time with a clear error (`birth_time_required`). The plugin then tells the operator that no chart data is available, and the consultation is handled without houses, or the operator asks the customer for the time.
- **(B) Amend it for the API only.** With `time_known: false` the API returns a reduced natal chart computed at local noon, flagged `time_known: false`: planets in signs, aspects between planets only, no ascendant, midheaven, houses, house rulers, ingresses or lunation houses. The Moon gets its possible range across the day instead of a single position. Report generation in astro-report stays exact-time-only.

**Recommendation: (B).** The rule exists to protect astro-report's own Reports, which ship unedited. In alerenzi every draft is reviewed by Alessandro, and the plugin hides house-based instructions when `time_known` is false. If (A) is chosen, the plugin can live with it, but those orders get no computed data.

### 3.3 Constraint: "Exactly one principal, enforced structurally. Adding a second is a revision of this contract … would also trigger the AGPL source-offer obligation."

**Needed:** one *machine* client, the alerenzi WordPress server, authenticated by a service token. There is no second human account, no users table, and no new UI login.

**Decision for astro-report's owner:** is a service token a second principal under this constraint, and does serving the plugin change the AGPL position? kerykeion and the Swiss Ephemeris are AGPL. The plugin's operator is Alessandro's business, the same business astro-report serves. Settle this before building and record it in the SPEC. If it is a problem, the alternative is to ship the computation as a library both apps use; the alerenzi plugin is PHP, so in practice that means a sidecar. Not recommended.

### 3.4 Transit window = "one half-open UTC interval derived from the Client's local calendar month"

**Needed:** arbitrary windows: twelve months from a birthday, or about three months from today.

**Recommendation:** the core transit functions already take `(start_utc, end_utc)`. Keep the month rule for Reports, and let the API pass any half-open UTC window up to a maximum length (e.g. 13 months), computed from local dates in the subject's zone.

### 3.5 Persistence

astro-report persists Clients, Natal Charts and Payloads. The plugin needs **no storage on the astro-report side**: it stores the response itself (alerenzi AD-28).

**Recommendation:** the API is **stateless**. No Client row, no chart row, no birth data written to the database or to logs. Only the existing place cache (CAP-2) may be used and filled, because it holds place names and coordinates, not people. This also keeps astro-report's CAP-24 (delete everything about a Client) and CAP-27 (backup) unaffected.

## 4. Proposed API contract (v1)

### 4.1 General

- **Prefix:** `/api/v1`, JSON in and out, UTF-8. Versioned: a breaking change means `/api/v2`, while additive fields are allowed in v1.
- **Authentication:** `Authorization: Bearer <token>`.
  - Only a hash of the token is stored, in a new environment variable read in `shell/config.py`, e.g. `API_TOKEN_HASH` (Argon2, like `AUTH_PASSWORD_HASH`), compared in constant time.
  - Session cookies are not accepted on `/api/*`, and the bearer token is not accepted on HTML routes.
  - A missing or invalid token gets `401` with a JSON body, never a redirect to the login page.
  - The `AuthMiddleware` allowlist and prefix logic needs an explicit branch for `/api/v1`.
- **Network:** both apps run on the same Netcup VPS under Coolify. Prefer the internal Coolify network, with HTTPS on the public domain as the fallback. Keep `/api/*` out of any public OpenAPI page.
- **Numbers:**
  - Angles are decimal strings with 4 decimal places, as in `core/` (`"123.4567"`), longitude normalised to `[0, 360)`.
  - Signs and degrees within sign are given too.
  - Instants are ISO 8601 UTC with `Z`.
- **Identifiers:**
  - Bodies, signs, aspects and directions use astro-report's existing glossary ids, verbatim (`sun` … `pluto`, `true_node`, `south_node`, `ascendant`, `midheaven`; `conjunction`, `sextile`, `square`, `trine`, `opposition`). No synonyms.
  - Italian display names come from §4.8, not from the chart responses.
- **Determinism:** identical request + identical `ComputationConfig` + identical ephemeris files ⇒ byte-identical response body. No timestamps in the body; a `Date` header is fine.
- **Errors:** `4xx/5xx` with `{ "code": "...", "message": "<Italian, operator-readable>", "field": "<json path or null>" }`. Codes:
  - `invalid_request`
  - `birth_time_required` (if 3.2 = A)
  - `place_unresolved`
  - `window_too_long`
  - `ephemeris_out_of_range`
  - `unauthorized`
  - `internal_error`
- **Meta on every chart response:**

```json
"meta": {
  "api_version": "1",
  "computation": { "version": 2, "content_hash": "…", "house_system": "placidus",
                   "orbs": { "natal": "7.0", "transit": "2.0", "synastry": "7.0" } },
  "ephemeris": { "manifest_sha256": "…" },
  "zodiac": "tropical"
}
```

The plugin stores `meta` with each result, so a draft can be traced to the exact settings, like astro-report's CAP-14.

### 4.2 Subject (a person's birth data)

```json
{
  "label": "A",
  "birth_date": "1985-03-12",
  "birth_time": "14:30",
  "time_known": true,
  "place": { "latitude": "45.4642", "longitude": "9.1900", "iana_zone": "Europe/Rome",
             "display_name": "Milano, Lombardia, Italia" }
}
```

- `birth_date` and `birth_time` are **local** civil time at the birthplace. astro-report converts them to UTC with the offset in force at that instant: the CAP-2 logic, `timezonefinder` + `zoneinfo`, including historical DST.
- An ambiguous or non-existent local time (DST fold or gap) returns `invalid_request` with `field: "birth_time"`, never a silent guess.
- `place` comes from §4.3: the plugin resolves it first and the operator confirms the candidate.
- No name, email or other personal data is sent. `label` is an opaque tag (`"A"`, `"B"`).

Every chart response echoes the resolved `birth_instant_utc` and `utc_offset` per subject, so the operator can check the conversion.

### 4.3 `POST /api/v1/places/resolve`

Request `{ "query": "Poggibonsi" }`. Response:

```json
{ "candidates": [ { "display_name": "Poggibonsi, Siena, Toscana, Italia",
                    "latitude": "43.4667", "longitude": "11.1500", "iana_zone": "Europe/Rome" } ] }
```

- Uses the existing Nominatim adapter and place cache: a repeat query does not hit Nominatim.
- Zero candidates ⇒ `place_unresolved`. Several candidates are all returned; the operator picks one in the plugin, as CAP-2 requires an explicit choice.

### 4.4 `POST /api/v1/charts/natal`

Request `{ "subject": { … } }`. Response (`time_known: true`):

```json
{
  "meta": { … },
  "subject": { "label": "A", "birth_instant_utc": "1985-03-12T13:30:00Z", "utc_offset": "+01:00", "time_known": true },
  "chart": {
    "ascendant": { "longitude": "…", "sign": "cancer", "degree": "…" },
    "midheaven": { "longitude": "…", "sign": "pisces", "degree": "…" },
    "planets": [ { "name": "sun", "longitude": "…", "sign": "pisces", "degree": "…", "house": 9, "retrograde": false } ],
    "houses": [ { "number": 1, "longitude": "…", "sign": "cancer",
                  "traditional_ruler": "moon", "modern_ruler": "moon", "co_ruler": null } ],
    "aspects": [ { "body1": "sun", "body2": "saturn", "aspect": "trine", "orb": "1.2345", "applying": true } ]
  }
}
```

- This is a serialisation of the existing `NatalChart`, `PlanetPosition`, `HouseCusp`, `HouseRuler` and `Aspect` types: ten planets plus the true and south nodes, in the order of `core/ephemeris/chart.py`.
- House rulers are included so the plugin never re-derives them.
- `time_known: false` (if 3.2 = B): `ascendant`, `midheaven`, `houses` and every `house` field are `null`, and aspects exclude angles. The Moon carries `"range": { "from": "…", "to": "…" }` across the local day, and the response sets `"subject.time_known": false`.

### 4.5 `POST /api/v1/charts/transits`

Request:

```json
{ "subject": { … }, "window": { "start_date": "2026-11-03", "end_date": "2027-11-03" } }
```

- **Window:** local dates in the subject's zone, half-open `[start, end)`, converted to one UTC interval. The maximum length is a config value (suggested 13 months) ⇒ `window_too_long`.
- **Response:** `meta`, `subject`, `window_utc { start, end }` and:
  - `aspects`: `TransitAspectEvent` (transiting_body, natal_point, aspect, perfected_at, never_perfected, orb_entry_at, orb_exit_at);
  - `stations`: body, direction, station_at, longitude;
  - `standing_retrogrades`: body, start, end;
  - `ingresses`: body, house_departed, house_entered, crossed_at;
  - `lunations`: kind, occurred_at, longitude, sign, natal_house.
- **Rules:** bodies, orb and the transiting-Moon exclusion are exactly as astro-report applies them today (`data/computation.toml`).
- **Events spanning a boundary:** an event that starts before the window and is still in orb is included with `orb_entry_at` before `window_utc.start`, and never dropped. The same deterministic rule applies at the end, and the rule chosen is stated in the SPEC.
- With `time_known: false`, ingresses and lunation houses are omitted and aspects to angles are excluded.
- **Performance:** the month scan has a 10 s upper bound (SPEC assumption). A 12-month window must finish inside the plugin's HTTP timeout. Target p90 ≤ 30 s for 12 months on the VPS; measure it. If it is slower, say so: the plugin can call per month and merge, or the API can become a job with polling. Pick one in correct-course.

### 4.6 `POST /api/v1/charts/synastry`

Request `{ "subject_a": { … }, "subject_b": { … } }`. Response:

```json
{
  "meta": { … },
  "subjects": [ { "label": "A", … }, { "label": "B", … } ],
  "natal_a": { …same shape as 4.4 chart… },
  "natal_b": { … },
  "inter_aspects": [ { "body_a": "venus", "body_b": "mars", "aspect": "trine", "orb": "2.1000" } ],
  "overlays": {
    "a_in_b": [ { "body": "sun", "house": 7 } ],
    "b_in_a": [ { "body": "moon", "house": 5 } ]
  },
  "composite": {
    "method": "midpoint",
    "planets": [ { "name": "sun", "longitude": "…", "sign": "…", "degree": "…", "house": 4 } ],
    "ascendant": { … }, "midheaven": { … },
    "houses": [ { "number": 1, "longitude": "…", "sign": "…" } ],
    "aspects": [ { "body1": "sun", "body2": "moon", "aspect": "square", "orb": "…", "applying": null } ]
  }
}
```

- **Inter-aspects:**
  - Every pair (A point, B point) over the ten planets, both nodes, ascendant and midheaven, using the five major aspects only.
  - The orb is a **new tunable `orbs.synastry`** in `data/computation.toml`, default equal to the natal orb. Changing it is a version bump, as with every tuning value.
  - `applying` has no meaning between two static charts, so it is omitted.
- **Overlays:** each person's planets placed in the other's Placidus houses. If one person's time is unknown, that person's houses (and so the overlays *into* them) are omitted.
- **Composite (decided on the alerenzi side: midpoint method):**
  - Each planet and node is the midpoint of the two positions on the **shorter arc**. For an exact opposition, take a documented deterministic rule, e.g. the midpoint nearer to A's position plus 90°, and test it.
  - Composite MC and ASC are midpoints of the two MCs and the two ASCs.
  - **House cusps:** astro-report's benchmark is Astro.com, so use whatever Astro.com's composite does and pin it with a conformance fixture. Make it a `[composite]` setting in `computation.toml`, `houses = "midpoint_cusps" | "derived_from_mc"`, so it is a data edit. The alerenzi documents say "houses derived from the composite angles"; if the Astro.com fixture shows midpoint cusps, the alerenzi side will align.
  - Composite aspects are computed within the natal orb.
  - The composite needs both birth times; if either is unknown, `composite.houses`, `ascendant`, `midheaven` and planet `house` are `null`.

### 4.7 `POST /api/v1/charts/solar-return`

Request:

```json
{ "subject": { … }, "year": 2026,
  "location": { "latitude": "…", "longitude": "…", "iana_zone": "…", "display_name": "…" } }
```

- `location` is optional and defaults to the birthplace. It is the place where the customer **spends the birthday** (the place-resolution flow is the same as §4.3).
- **Return instant:** the moment in `year`, nearest the birthday, when the transiting Sun's tropical longitude equals the natal Sun's longitude exactly (`swe.solcross_ut`). The result is UTC, and a test covers a birthday near New Year and one on 29 February.
- **Chart:** a full chart for that instant at `location`, Placidus, with the same shape as §4.4 (planets with RS houses, RS angles and cusps, RS aspects within the natal orb).
- **Comparison with the natal chart** (central to the Italian solar-return reading the product uses):
  - `rs_ascendant_in_natal_house`;
  - `rs_planets_in_natal_houses` [{ body, house }];
  - `rs_to_natal_aspects`, within the natal orb.
- Response: `meta`, `subject`, `return_instant_utc`, `location`, `chart`, `comparison`.
- The plugin gets the year's transits separately from §4.5, with window = birthday → next birthday.
- **Unknown birth time:** the natal Sun is barely affected, so the return instant is still valid. The natal-house comparison is not, so with `time_known: false` it is omitted. The RS chart itself still has houses: they come from the return instant and location, not from the birth time.

### 4.8 `GET /api/v1/vocabulary/it` (small, recommended)

Returns the Italian names for every id the chart responses use (bodies, signs, aspects, house ordinals, directions), taken from `core/gate/vocabulary.it.json` plus the aspect names. The plugin instructs its AI to use exactly these words, and the same file feeds astro-report's own Gate, so the two products speak the same vocabulary.

### 4.9 `GET /api/v1/style-guide/current` (optional)

Returns `{ "version": n, "body": "…" }`, the latest Style Guide row. Story 7.7 on the alerenzi side derives the astrology prompt from it, and recording the version tells Alessandro when a newer one exists. A manual export is acceptable instead: say which in correct-course.

## 5. Implementation notes from the alerenzi side

These are suggestions; astro-report's spine decides.

- **`core/` stays pure.** Synastry inter-aspects, overlays, composite and solar return are new pure functions under `core/` (e.g. `core/synastry/`, `core/returns/`), with types in `core/types/`. The boundary tests (`test_import_boundary`) cover them automatically.
- **Thread binding (known pitfall):** the Swiss Ephemeris path is process-global C state. Every API handler path that computes must call `bind_verified_ephemeris_path_to_current_thread()`, as `compute_natal_chart()` does. FastAPI runs sync handlers in its thread pool, so check this against `tests/test_concurrency_boundary.py`: handlers must not create threads or executors themselves, and must not touch the `RunDriver`.
- **Configuration:** `API_TOKEN_HASH` and any API limits go through `shell/config.py` and the README's variable table. `orbs.synastry`, `[composite]` and the transit window maximum go in `data/computation.toml` with a version bump.
- **Conformance (CAP-29):** add Astro.com reference fixtures for:
  - one synastry, with inter-aspects and both overlays;
  - one composite, including a near-opposition pair;
  - two solar returns: birthplace and relocated, one with a birthday near the year boundary;
  - one 12-month transit window crossing a retrograde station.

  Keep choosing them adversarially, as the existing set does.
- **Logging:** no request bodies, no birth data and no coordinates in logs. Log endpoint, status, duration and the computation version only.
- **No new storage,** therefore no migration. If a decision adds one, it is forward-only as usual.
- **Tests:** request validation (DST gap and fold, bad zone, window too long); auth (no token, wrong token, cookie on `/api`, token on HTML routes); byte-identical repeat responses; the time-unknown variants; error bodies in Italian.

## 6. What the alerenzi plugin will do with it (for context)

- **Birth data (Story 7.5):** parses the WooCommerce intake (date, time or "non so", place text; for the couple product both people; for the solar return the optional birthday place). It calls `places/resolve` and lets the operator pick and correct the candidate, then stores structured `birth_data`.
- **Chart data (Story 7.6):**
  - A PHP port `CM_Chart_Data_Port` with one HTTP adapter (Guzzle) calls the endpoints above with the bearer token (stored in WordPress options, never echoed).
  - Each response is stored frozen in the consultation's `chart_data` column, keyed by kind, with `meta`.
  - The AI tool `get_astro_data(kind)` returns the stored copy, and only the operator's "Ricalcola" refetches.
  - Timeouts and errors are shown to the operator and never invented around.
- **Astrology prompts (Story 7.7):** the voice is derived from astro-report's Style Guide and vocabulary. The AI may name only positions present in the stored data, mirroring astro-report's Gate rule.

## 7. Acceptance criteria (cross-repo)

1. With a valid token, `charts/natal` for a reference subject returns positions, cusps and aspects identical to the stored Natal Chart astro-report computes for the same birth data, and to the Astro.com fixture.
2. Repeating any request returns a byte-identical body.
3. `charts/transits` for a 12-month window returns every event the month-by-month Report pipeline would find for those months, with no duplicates or gaps at the month seams, within the agreed time budget.
4. `charts/synastry` and `charts/solar-return` match their new Astro.com fixtures within the harness's tolerances, and the composite uses the configured house method.
5. A request without a token, or with the session cookie only, gets `401` JSON. HTML routes ignore the bearer token.
6. Nothing about the subjects is written to the database or to logs; only the place cache may grow.
7. The time-unknown behaviour is the one chosen in §3.2, tested both ways.
8. The SPEC records the amended non-goal (§3.1), the decisions on §3.2-3.5, and the new capabilities. The spine records the API's ADs (authentication, statelessness, thread binding, versioning).

## 8. Decisions to take in astro-report's correct-course

1. §3.1: amend the non-goal for computed synastry, composite and solar return (recommended: yes).
2. §3.2: unknown birth time, (A) reject or (B) reduced chart (recommended: B, API only).
3. §3.3: service token versus "one principal", and the AGPL position.
4. §3.4: arbitrary transit windows for the API, and the maximum length.
5. §3.5: stateless API (recommended: yes).
6. §4.5: synchronous 12-month transits within budget, or per-month calls or an async job.
7. §4.6: composite house method, set by the Astro.com fixture.
8. §4.9: style-guide endpoint or manual export.
9. Network path: Coolify internal network or public HTTPS, and the hostname the plugin uses.

## 9. Suggested story split (for this repository)

1. **API skeleton and auth:** `/api/v1` router, bearer token (`API_TOKEN_HASH`), JSON errors, middleware branch, meta block, tests.
2. **Places and natal:** `places/resolve`, `charts/natal` (serialising existing types), local-time conversion with DST edge cases, time-unknown variant per decision 2.
3. **Transit windows:** `charts/transits` over arbitrary windows, seam rule, performance measurement on the VPS.
4. **Synastry and composite:** pure core functions, `orbs.synastry` and `[composite]` config, `charts/synastry`, Astro.com fixtures.
5. **Solar return:** pure core function with `solcross_ut`, relocation, natal comparison, `charts/solar-return`, fixtures (year boundary, leap day).
6. **Vocabulary (and style guide) endpoints,** API docs for the plugin team, deployment: token set in Coolify, network path verified from the WordPress container.

When this is deployed, the alerenzi side starts Story 7.6.
