# Manual browser checks — Epic 2 (2.6 / 2.7 / 2.8) and Epic 3 (3.9)

Stories 2.6, 2.7, 2.8 and 3.9 each prescribe a manual browser check in their
own spec's **Verification → Manual checks** section, because their acceptance
criteria are partly visual / behavioural and the automated suite cannot fully
stand in for them. Every epic-2 and epic-3 retrospective recorded that these
checks had **never been run against a reachable Postgres** — `epic-2-retro`
action item 18 and `epic-3-retro` action item 22 exist only to get them run
and recorded.

This file is that record.

**Status: run 2026-08-28 against the full `docker compose` stack (production
image + Postgres 18), driven through Chrome. Stories 2.6 / 2.7 / 2.8 — pass.
Story 3.9 — the poll view was exercised and behaves correctly; the Payload
view was initially blocked by a real defect in the report pipeline's transit
stage (the "Blocker" section below), which was root-caused, fixed, and
re-verified the same day (the "Resolution" section) — the Payload view now
renders.**

- **checked:** 2026-08-28
- **environment:** `docker compose up -d --build` — `astro-report-app`
  (uvicorn, `--workers 1`, production image) + `postgres:18-alpine`, both
  healthy; `ENVIRONMENT=local`, so `get_generator()` returns
  `RecordedResponseGenerator` (no Gemini quota spent).
- **driven by:** Claude (Claude-in-Chrome browser automation), with a
  logged-in Astro.com session already open in the same browser for the 2.6
  chart-wheel comparison.
- **recording:** `item18-stories-2.6-2.7-2.8-browser-checks.gif` (saved to the
  operator's browser Downloads on 2026-08-28) captures the 2.6 → 2.7 → 2.8
  run end to end.

---

## Story 2.6 — see the chart wheel and check it against Astro.com — **PASS**

**Prescribed check** (`spec-2-6`): create a Client via `/clients/new`, open
`/clients/{id}/chart`, compare the rendered wheel's planet signs / houses and
Aspects against Astro.com for the same birth data.

**Steps run:**

1. Signed in at `/login`.
2. `/clients/new` → created **Case1 LeapDay** (2024-02-29, 05:12,
   "Durham, North Carolina, USA"). The ambiguous-birthplace candidate picker
   appeared (real Nominatim resolution, two candidates); selected
   *"Durham, Durham County, North Carolina, United States"*. Client
   `01a0496f-8644-7d1e-ae11-80b38aa9d996` created; the success page carried
   the **"View chart"** link (epic-2-retro item 14).
3. Opened `/clients/{id}/chart`. Kerykeion SVG wheel + data table rendered.
   No config-stale banner (chart just written under the running
   `computation.toml`; epic-2-retro item 11 banner path not triggered).
4. Compared the app's data table against the **live** Astro.com "Free
   Astrology Chart" for the saved *Case1 LeapDay* profile (Placidus, logged
   in), which is also the source of `tests/conformance/fixtures/leap-day-birth.toml`.

**Result — exact agreement** (app vs. Astro.com, to the displayed arcminute):

| Point | App (`/chart`) | Astro.com |
|---|---|---|
| Sun | 10°18'44" Pisces | 10 Pis 18'44" |
| Moon | 3°31'43" Scorpio | 3 Sco 31'43" |
| Mercury | 11°14'20" Pisces | 11 Pis 14'20" |
| Venus | 15°46'53" Aquarius | 15 Aqu 46'53" |
| Mars | 12°28'19" Aquarius | 12 Aqu 28'19" |
| Jupiter | 11°12'59" Taurus | 11 Tau 12'59" |
| Saturn | 9°50'34" Pisces | 9 Pis 50'35" (1" display rounding) |
| Uranus | 19°33'47" Taurus | 19 Tau 33'47" |
| Neptune | 26°43'10" Pisces | 26 Pis 43'10" |
| Pluto | 1°12'03" Aquarius | 1 Aqu 12'3" |
| True Node | 15°59'16" Aries | 15 Ari 59'16" |
| Ascendant | 6°11'12" Aquarius | 6 Aqu 11' |
| MC | 25°10'04" Scorpio | 25 Sco 10' |
| Cusp 2 | 20°07'22" Pisces | 20 Pis 7' |
| Cusp 3 | 27°22'31" Aries | 27 Ari 23' |
| Cusp 11 | 17°55'08" Sagittarius | 17 Sag 55' |
| Cusp 12 | 9°56'06" Capricorn | 9 Cap 56' |

Zodiac Tropical, Domification Placidus, Apparent Geocentric — matches
Astro.com's "Web Style / Placidus". Aspects were **not** diffed 1:1: the wheel
recomputes natal aspects at this project's `orbs.natal` (7.0°), whereas
Astro.com's grid uses its own per-planet orbs (see
`memory/reference_astro_com_access.md`); the aspect lines render and are
qualitatively consistent with the position set. The house cusps and every
body's sign and degree match exactly, which is what "eyeball it against
Astro.com" is for.

---

## Story 2.7 — correct birth data and know what it invalidates — **PASS**

**Prescribed check** (`spec-2-7`): open `/clients/{id}/edit`, submit a changed
birth time **without confirming** — verify the warning appears and
`/clients/{id}/chart` still shows the original chart. Confirm, then reload
`/chart` and verify it now reflects the corrected time.

**Steps run** (same Client `01a0496f…`):

1. `/clients/{id}/edit` — form prefilled from the stored row, birthplace
   blank ("never prefilled — retype it").
2. Changed birth time **05:12 → 18:30**, re-entered the birthplace, clicked
   **Review correction**. The ambiguous-place candidate picker appeared first
   (mirrors create; nothing persisted, warning not yet shown — matches the
   spec's I/O matrix). Selected the same candidate, clicked **Review
   correction** again.
3. **Warning page shown**: *"Applying this correction will supersede the
   current chart. The previous chart is kept, marked superseded, and stays
   queryable — but any work already generated against it may no longer match.
   Confirm to apply."* Nothing persisted.
4. In a separate tab, reloaded `/clients/{id}/chart` — **still the original**:
   birth line `2024-02-29 05:12`, Asc 6°11'12" Aquarius, MC 25°10'04"
   Scorpio, Sun 10°18'44" Pisces. Unchanged.
5. Clicked **Confirm and apply** → *"Client … corrected. View chart"* (link
   present).
6. Reloaded `/clients/{id}/chart` — **now the corrected chart**: birth line
   `2024-02-29 18:30`; Asc **15°49'08" Virgo**, MC **14°12'31" Gemini**;
   Sun advanced to 10°52'07" Pisces (≈ +33', consistent with ~13.3 h of
   solar motion), Moon to 10°13'45" Scorpio (≈ +6°42', consistent with the
   Moon's ~13°/day); all house cusps recomputed.

The corrected chart's live-Astro.com re-check was **not** done — it would
require mutating the operator's saved *Case1 LeapDay* profile on Astro.com.
The 05:12 comparison in 2.6 already validates the computation engine against
Astro.com; 2.7's check is about the warn/confirm gate and that `/chart`
reflects the change, both demonstrated.

---

## Story 2.8 — delete a client and everything derived from them — **PASS**

**Prescribed check** (`spec-2-8`): create a Client, correct its birth data
once (2.7) so it has a superseded chart, then open `/clients/{id}/delete`,
confirm, and verify `/clients/{id}/chart` now 404s.

**Steps run** (same Client `01a0496f…`, which now has a superseded chart from
the 2.7 correction above):

1. `/clients/{id}/delete` — confirmation page: *"This will permanently delete
   this Client and its Natal Chart, **including the superseded chart kept from
   an earlier correction**. This cannot be undone."* (copy correctly names the
   superseded chart).
2. Clicked **Confirm delete** → *"Client … deleted."*
3. `GET /clients/{id}/chart` → **404** (`{"detail":"Not Found"}`), confirmed
   both in the browser and by status code in the server log
   (`GET …/chart HTTP/1.1" 404 Not Found`).
4. Extra, for the spec's "unknown client id" matrix rows: `GET
   /clients/00000000-0000-0000-0000-000000000000/{chart,edit,delete}` → all
   **404**.

---

## Story 3.9 — read the facts behind a month entry, entry by entry — **poll view PASS; Payload view blocked**

**Prescribed check** (`spec-3-9` / `epic-3-retro` item 22): manually exercise
the Payload view `GET /report-runs/{run_id}/payload` and the runner
driver / poll view in a browser.

**Steps run:**

1. Created a fresh Client (*Case1 LeapDay* again,
   `01a04972-9bdc-7726-ac3c-f3b2665489f3`).
2. Started a run: `POST /clients/{id}/report-runs` with `month=2026-09` →
   303 to `/report-runs/{run_id}`.
3. **Poll view** (`GET /report-runs/{run_id}`) rendered: *"Report run —
   2026-09 · Stage: natal_ready"*. Reloading drove the run forward
   (`_drive_run` runs synchronously on each poll).
4. After the transit stage failed 5 consecutive times, the poll view
   switched to a **terminal-failure message** —
   *"Failed: stage 'transits_ready' failed 5 consecutive times: Refusing to
   compute: body 0 was not computed via the Swiss Ephemeris (calc_ut returned
   flags 260); a Moshier fallback is never acceptable."* — instead of
   polling silently forever. This is the epic-3-retro **item 20** signal
   (stuck / permanently-failing run), working as intended.
5. **Payload view** (`GET /report-runs/{run_id}/payload`) → **404**
   (`{"detail":"Not Found"}`) — correct for a run that never reached
   `payload_ready` (the spec's "un-payload-ready → 404" matrix row), but it
   means the Payload view's own rendering (`report_payload.html`,
   `localize_payload`) could **not** be exercised, because no run in the
   running server can produce a `ReportPayload`.

Tried `month` = `2024-03`, `2023-08`, `2022-12` (the conformance-fixture
months) and a freshly restarted app process — **every** run fails identically
at `transits_ready`.

### Blocker — the report pipeline's ephemeris path is not set on the threads that run it

Root-caused during this check (full write-up appended to
`deferred-work.md`):

- `verify_ephemeris_identity()` calls `swe.set_ephe_path(data/ephemeris)`
  **once, at module import, on the main thread** (`shell/http/app.py`).
- In this build of `pyswisseph`, `swe_set_ephe_path()` state is **not shared
  across threads**. Confirmed in-container: `_calc_body(...)` for the same
  date succeeds on the main thread and raises the exact
  `EphemerisIntegrityError` above on a worker thread; calling
  `swe.set_ephe_path()` inside the worker thread fixes it.
- FastAPI runs **sync** route handlers in an anyio worker threadpool.
  `poll_report_run` / `start_report_run` are `def` (sync) → the whole runner
  (`drive()` → `find_transit_aspects` → `_calc_body`) executes on a
  threadpool thread with **no ephemeris path**, so `swe.calc_ut` silently
  falls back to Moshier and `_calc_body` correctly refuses.
- The natal chart works only because `create_client` is `async def` — it runs
  on the event-loop (main) thread, which *does* have the path. Same reason
  the test suite is green: pytest runs everything on the main thread.

Net: **the entire monthly-report pipeline (Epic 3 onward) cannot run in the
deployed application** as currently wired. `epic-3-retro` item 22's original
wording ("record that it has *not* been checked") is now superseded — it has
been checked, and the check found this.

Suggested fix (small, not applied here — needs its own spec/review):
set the ephemeris path on the thread that computes, e.g. call
`swe.set_ephe_path(str(ident.directory))` at the top of `_calc_body`
(cheap, idempotent), or make `poll_report_run` / `start_report_run` `async`
and run `drive()` via `anyio.to_thread` with a path-setting initializer, or
make the runner explicitly (re-)establish the verified path before its first
`swe` call.

### Resolution — 2026-08-28

Fixed by `spec-epic-3-retro-item-22-bind-ephemeris-path-per-thread.md`
(branch `fix/epic-3-retro-item-22-ephemeris-thread-path`).
`core/ephemeris/identity.py` now records the last-verified directory and
exposes `bind_verified_ephemeris_path_to_current_thread()` — a `threading.local`
guard that re-applies the already-verified path to the calling thread once
(no `.se1` reopen per call), and still raises `EphemerisIntegrityError` if
`verify_ephemeris_identity()` never ran in the process. `_calc_body` (the sole
`swe.calc_ut` chokepoint) and `compute_natal_chart` (for `swe.houses`) call it
first.

Re-checked against a rebuilt `docker compose` stack: `POST
/clients/{id}/report-runs` with `month=2026-09` now advances past
`transits_ready` to `gate_passed`, and `GET /report-runs/{run_id}/payload`
returns **200** rendering the Story 3.9 Payload view in full (transit aspects,
stations, EDT-localised times) — previously a hard `transits_ready` Moshier
failure. (`draft_ready`/`report_ready` are not reached in `ENVIRONMENT=local`
because `RecordedResponseGenerator` has no recording for an arbitrary
client/month — a separate, expected local-mode limit, not this bug.)

New worker-thread regression tests: `tests/test_ephemeris_identity.py`
(bind behaviour + `_calc_body` on a `ThreadPoolExecutor` worker),
`tests/test_transit_aspects.py` and `tests/test_natal_chart.py` (end-to-end
off the main thread). Confirmed these fail with the exact
`calc_ut returned flags 260` error when the `_calc_body` bind is removed.
Full suite: 1413 passed, 4 skipped, 2 xfailed; `ruff` clean.

---

## What was not covered

- The Payload view's own template / localisation (`report_payload.html`,
  `localize_payload`) — blocked by the above; covered only by
  `tests/test_payload_view.py` at present.
- The `draft` / `report` / `export` views downstream of `payload_ready` —
  same blocker.
- Live-Astro.com re-check of the 2.7 *corrected* (18:30) chart — deliberately
  skipped to avoid mutating the operator's saved Astro.com profile.
