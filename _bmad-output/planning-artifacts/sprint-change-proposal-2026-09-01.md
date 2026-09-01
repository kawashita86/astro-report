---
title: "Sprint Change Proposal: astro-report"
status: draft
created: 2026-09-01
trigger: "Persist and display the geocoded birthplace name"
---

# Sprint Change Proposal — astro-report

**Date:** 2026-09-01
**Prepared by:** Amelia (Developer agent), via `/bmad-correct-course`
**Mode:** Batch (single well-scoped change; see §6 for the one approval this proposal still needs)

---

## 1. Issue Summary

**Problem statement.** `Client` never stores the geocoded birthplace *name* — only the resolved
latitude, longitude and IANA zone. Two Client-facing consequences follow directly from that one gap:

1. **Anagrafica edit form** (`client_edit.html`, served by `client_edit_form` in
   `shell/http/routes/clients.py:481-500`) always renders the "Luogo di nascita" field blank on
   load. Francesco must retype the birthplace on every correction, even to reconfirm a place that
   never changed. The route handler's own docstring names this as deliberate: *"Birthplace has no
   stored free-text form to prefill from — only resolved lat/lon/zone are stored — so it starts
   blank and must be retyped even to reconfirm the same place."*
2. **SVG chart wheel** (`shell/http/chart_wheel.py:78-134`, `build_subject()`) hard-codes
   `city=""` and `nation=""` when building Kerykeion's subject model, so the wheel's "Location:"
   header always renders empty. The docstring is explicit: *"city/nation are placeholders...no
   birthplace name is stored."*

**How this was discovered.** Francesco flagged both symptoms directly (not surfaced by a story or
a test failure) and pointed at the exact code and docstrings that document the behavior as
intentional, tracing it to **AD-16** ("A Client cannot exist in a partial state," Story 2.7).

**Evidence.**
- `shell/adapters/postgres/client.py:67` — `Client` columns: `name`, `birth_date`, `birth_time`,
  `latitude`, `longitude`, `iana_zone`. No name/text field for the place.
- `shell/http/routes/clients.py:481-500` — `client_edit_form()`, `form["birthplace"] = ""`.
- `shell/http/chart_wheel.py:126-134` — `"city": "", "nation": ""` with the placeholder docstring.
- `tests/test_http_client_correction.py:410` —
  `test_the_edit_form_is_prefilled_from_the_client_row_and_birthplace_is_blank` pins the current
  behavior as a passing test; it will need to invert once this change lands.
- ARCHITECTURE-SPINE.md **AD-16**: *"The Client stores its own immutable snapshot of the resolved
  latitude, longitude and IANA zone"* — the rule that authorized dropping the name.
- Epics.md **Story 9.4** AC: *"on correction the birthplace field is never prefilled"* — the story
  AC that encodes the same rule at the UX layer.

**Issue category (checklist 1.2):** closest to *misunderstanding of original requirements*, not a
new requirement invented from nothing — see §3 below: the PRD's own Glossary already lists
`birthplace` as something a Client "holds," distinct from "a resolved geographic coordinate and
historical timezone." AD-16, written during architecture, collapsed that into coordinates-only and
no downstream story caught the narrowing. This proposal restores the PRD's original shape rather
than expanding scope beyond it.

---

## 2. Impact Analysis

### Epic impact

- **Epic 2 — Anagrafica e Tema Natale** (binds AD-16): Stories 2.1, 2.3 and 2.7 all state or imply
  the coordinates-only snapshot and need their ACs extended, not replaced. Story 2.6 (chart wheel)
  gets one added consequence. No epic is invalidated, resequenced, or added.
- **Epic 9 — UI rebuild** (Story 9.4): one AC is reversed (prefill instead of blank). This is the
  only AC in the epic set that actually contradicts the new requirement; everything else in Epic 9
  is unaffected.
- No other epic references birthplace storage or the chart wheel's header.

### Artifact conflicts

- **PRD:** no conflict — see §3, this change brings the implementation *into* alignment with PRD
  §3 Glossary rather than away from it. No FR text needs to change; **FR-2**'s "Consequences" gain
  one line, additive only.
- **Architecture (ARCHITECTURE-SPINE.md):** **AD-16** needs a textual amendment (not a new AD, not
  a superseding decision) — its Rule paragraph gains the geocoded name as a fourth immutable
  snapshot field, alongside lat/lon/zone. The invariant AD-16 exists to protect — *no partial
  Client state, immutability of the snapshot, `PLACE_CACHE` never a source of truth after
  creation* — is unchanged and, if anything, reinforced (one more field enters the same
  once-resolved-never-rewritten snapshot). **AD-1** (purity boundary) and **AD-3** (Payload is the
  Generator's only channel) are unaffected: the name never reaches the Generator or the Report
  Payload, only the Client record and the internal-only chart wheel.
- **UX (EXPERIENCE.md/DESIGN.md):** no layout change. `client_edit.html`'s birthplace field already
  exists and is already wired to `form.birthplace` — only the *value supplied* to that template
  variable changes (from `""` to the stored name on GET). No new field, no new screen state beyond
  what Story 9.4 already built for the ambiguous-candidate sub-state.
- **Spec / computation contract:** none. The Report Payload, Domain Profiles and Generator inputs
  are untouched — this is Client-record and internal-verification-tool data only, never Client- or
  Report-facing astronomy.

### Technical impact (for the implementing developer — informational, not prescriptive)

This is additive data capture along an existing seam (`Geocoder` → `PLACE_CACHE` → `Client`), not a
new subsystem:

- `core/types/place.py` — `ResolvedPlace` gains a `display_name: str` field (mirroring
  `PlaceCandidate.display_name`, which already exists for the ambiguous-match case).
- `shell/adapters/nominatim/*.py` — `resolve()` populates `display_name` from the geocoder match
  (`match.address`) on the unambiguous path; `resolve_candidate()` populates it from the chosen
  `PlaceCandidate.display_name` (already available, currently discarded after the candidate is
  chosen).
- `shell/adapters/postgres/place_cache.py` — `PlaceCache`/`CachedPlace` gain the same field so a
  cache hit still returns a name without re-querying Nominatim; `store_resolved_place()` and
  `lookup_cached_place()` extend accordingly. Forward-only Alembic migration required (new
  `place_cache.display_name` column) — repo policy (`AGENTS.md`) forbids a `downgrade()` body.
- `shell/adapters/postgres/client.py` — `Client` gains a `birthplace_name: str` column (bounded
  length, mirroring the existing `name`/`iana_zone` pattern); `create_client_with_chart()` and
  `correct_client_and_chart()` accept and persist it. Second forward-only migration (or the same
  one).
- `shell/http/routes/clients.py` — `create_client` persists `resolved.display_name`;
  `client_edit_form()` prefills `form["birthplace"] = client.birthplace_name` instead of `""`;
  `correct_client`/`correct_client_and_chart()` persist the newly resolved name on confirm.
- `shell/http/chart_wheel.py` — `build_subject()` sets `city`/`nation` from
  `client.birthplace_name` instead of `""`. **Open implementation decision, flagged rather than
  silently resolved:** Kerykeion's SVG renders the header as literally
  `f"{city}, {nation}"` (`kerykeion/charts/chart_drawer.py:567`, third-party, not ours to edit).
  Putting the whole geocoded name in `city` and leaving `nation` empty renders a trailing `, `.
  Two acceptable options for the developer to choose between, since this is a Francesco-only
  cosmetic detail: (a) accept the trailing `, ` — simplest, functionally correct; (b) split
  `birthplace_name` on its last comma into `city`/`nation` for a clean label. Recommend (a) unless
  it looks wrong once actually rendered — don't build (b) speculatively.
- Tests needing updates (found, not fixed, by this proposal): `tests/test_geocoder_nominatim.py`'s
  `ResolvedPlace(...)` equality assertions (lines ~254-326) need a `display_name` argument;
  `tests/test_http_client_correction.py:410`'s
  `test_the_edit_form_is_prefilled_from_the_client_row_and_birthplace_is_blank` inverts to assert
  prefill instead of blank; `tests/test_client_store.py` and `tests/test_http_chart_wheel.py` gain
  coverage for the new field/rendering.

No AD-1 (purity), AD-2 (ephemeris identity), AD-9 (single Generator adapter), AD-11 (no durable
host-filesystem state), or AD-20 (poll-driven advance) implication anywhere in this change — it
never touches the report-run pipeline.

---

## 3. Recommended Approach

**Selected: Option 1 — Direct Adjustment.** Extend the existing birthplace-resolution seam with one
new field, carried through `Geocoder` → `PLACE_CACHE` → `Client`, and surface it in the two places
Francesco named. No rollback, no MVP re-scoping.

**Rationale:**
- **Effort:** Low. One conceptual field threaded through five files plus two small forward-only
  migrations; no new port, no new architectural pattern, no new epic.
- **Risk:** Low. Purely additive — no existing column is removed or repurposed, no existing route
  contract changes shape (only the *value* prefilled), and the immutable-snapshot guarantee AD-16
  protects is preserved, just widened by one field.
- **PRD alignment, not scope creep:** PRD §3 Glossary already states a Client "holds... birthplace,
  and a resolved geographic coordinate and historical timezone" as two distinct things. The current
  implementation only kept the second. This change makes the stored data match what the PRD always
  said a Client holds — it is corrective, not additive scope.
- **Rollback (Option 2) is not viable:** there is nothing to roll back to — the gap has existed
  since Story 2.7 shipped Epic 2, and no later story depends on birthplace staying unstored.
- **MVP review (Option 3) is not warranted:** nothing here touches §9 MVP scope, a Non-Goal, or a
  Success Metric.

---

## 4. Detailed Change Proposals

### 4.1 Architecture — `ARCHITECTURE-SPINE.md`, AD-16

**OLD:**
> **Rule:** the `Client` type has no optional birth fields and no partial constructor. Birthplace
> resolution and historical-offset resolution complete before a Client is persisted; failure means
> no Client row. There is no noon chart, no solar-house fallback and no house-less path anywhere in
> the codebase. The Client stores its **own immutable snapshot** of the resolved latitude,
> longitude and IANA zone; `PLACE_CACHE` is a lookup accelerator consulted before geocoding and
> never a source of truth afterwards, so a later geocoder correction can never silently alter a
> chart already computed.

**NEW:**
> **Rule:** the `Client` type has no optional birth fields and no partial constructor. Birthplace
> resolution and historical-offset resolution complete before a Client is persisted; failure means
> no Client row. There is no noon chart, no solar-house fallback and no house-less path anywhere in
> the codebase. The Client stores its **own immutable snapshot** of the resolved latitude,
> longitude, IANA zone, **and the geocoded place name that produced them** (amended 2026-09-01:
> the name is captured at resolution time from the same `Geocoder` call, so it never requires a
> separate lookup or a second source of truth); `PLACE_CACHE` is a lookup accelerator consulted
> before geocoding and never a source of truth afterwards, so a later geocoder correction can never
> silently alter a chart already computed.

**Rationale:** widens the immutable snapshot by one field without touching what the invariant
prevents (partial Client state, PLACE_CACHE-as-truth-after-creation). No new AD needed.

### 4.2 Story 2.1 — `epics.md`, "Resolve a birthplace to coordinates and the offset in force at birth"

**OLD (Acceptance Criteria, first block):**
> **Given** a `Geocoder` port and a Nominatim adapter
> **When** a free-text birthplace and a birth date and time are supplied
> **Then** resolution returns latitude and longitude to at least four decimal places
> **And** it returns the IANA zone and the UTC offset in force at that instant at that location,
> derived from `timezonefinder` and `zoneinfo`, including historical DST rules
> **And** the offset is never the present-day offset for that location

**NEW (append one line):**
> **Given** a `Geocoder` port and a Nominatim adapter
> **When** a free-text birthplace and a birth date and time are supplied
> **Then** resolution returns latitude and longitude to at least four decimal places
> **And** it returns the IANA zone and the UTC offset in force at that instant at that location,
> derived from `timezonefinder` and `zoneinfo`, including historical DST rules
> **And** the offset is never the present-day offset for that location
> **And** it returns the geocoder's own place name for the match — the same field already returned
> for an ambiguous candidate — so the resolved place can be shown back to Francesco later without
> a second lookup
>
> *(Amended 2026-09-01, correct-course: closes the gap where an unambiguous match discarded its own
> place name while an ambiguous one already carried it as `PlaceCandidate.display_name`.)*

**Rationale:** the ambiguous path already proves the geocoder can name a match; the unambiguous
path just needs to keep what it already receives.

### 4.3 Story 2.3 — `epics.md`, "Create a Client, or fail visibly"

**OLD:**
> **Given** a successfully created Client
> **When** the row is written
> **Then** it stores its own immutable snapshot of the resolved latitude, longitude and IANA zone
> **And** the Natal Chart is computed once and stored with it
> **And** both use UUIDv7 primary keys

**NEW:**
> **Given** a successfully created Client
> **When** the row is written
> **Then** it stores its own immutable snapshot of the resolved latitude, longitude, IANA zone, and
> the geocoded place name that produced them
> **And** the Natal Chart is computed once and stored with it
> **And** both use UUIDv7 primary keys
>
> *(Amended 2026-09-01, correct-course: the place name enters the same immutable snapshot as
> lat/lon/zone — see AD-16's amendment — so it is captured here, at creation, not derived later.)*

### 4.4 Story 2.6 — `epics.md`, "See the chart wheel and check it against Astro.com"

**OLD:**
> **Given** a Client with a stored Natal Chart
> **When** Francesco opens the chart wheel
> **Then** the wheel shows planetary positions, house cusps and natal Aspects

**NEW (append one Given/When/Then):**
> **Given** a Client with a stored Natal Chart
> **When** Francesco opens the chart wheel
> **Then** the wheel shows planetary positions, house cusps and natal Aspects
> **And** the wheel's Location header shows the Client's stored geocoded place name, not a blank
> field
>
> *(Amended 2026-09-01, correct-course: `city`/`nation` were placeholders only because no place
> name was stored anywhere in the system; that gap is closed by Story 2.3's amendment.)*

### 4.5 Story 2.7 — `epics.md`, "Correct birth data, and know what it invalidates"

**OLD:**
> **Given** a correction that changes the birthplace
> **When** it is applied
> **Then** the birthplace is re-resolved and the Client's immutable coordinate and zone snapshot is
> replaced as part of the same change

**NEW:**
> **Given** a correction that changes the birthplace
> **When** it is applied
> **Then** the birthplace is re-resolved and the Client's immutable coordinate, zone and place-name
> snapshot is replaced as part of the same change

### 4.6 Story 9.4 — `epics.md`, "Client create, correct and delete — restyled, with a real delete guard"

**OLD:**
> **Given** an ambiguous birthplace
> **When** the geocoder returns candidates
> **Then** the choice appears as an in-form sub-state that preserves the typed input; on correction
> the birthplace field is never prefilled

**NEW:**
> **Given** an ambiguous birthplace
> **When** the geocoder returns candidates
> **Then** the choice appears as an in-form sub-state that preserves the typed input
>
> **Given** the correction form for a Client with a stored place name
> **When** it renders
> **Then** the birthplace field is prefilled with that stored name, exactly like every other field
> on the form; Francesco can leave it as-is to reconfirm the same place or replace it to correct it
>
> *(Amended 2026-09-01, correct-course: reverses the original AC. It existed only because no place
> name was ever stored to prefill from (AD-16 as originally written) — that constraint is gone.
> `tests/test_http_client_correction.py`'s
> `test_the_edit_form_is_prefilled_from_the_client_row_and_birthplace_is_blank` inverts along with
> it.)*

---

## 5. Implementation Handoff

**Scope classification: Minor.** Single additive field threaded through an existing seam, two
forward-only migrations, five story/AD text amendments already drafted above (§4) — no epic
restructuring, no PRD change, no MVP re-scoping. This is implementable directly by a Developer
agent following the amendment pattern already established in this repo's `epics.md` (see the
2026-08-31 amendments to Stories 9.2/9.3).

**Route to:** Developer agent (`bmad-build` / Amelia).

**Deliverables for the Developer agent:**
1. Apply the five edit proposals in §4 to `ARCHITECTURE-SPINE.md` and `epics.md` verbatim.
2. Implement per §2's technical-impact notes: `core/types/place.py`, the Nominatim adapter,
   `place_cache.py`, `client.py`, `clients.py`'s three handlers, `chart_wheel.py`. Two forward-only
   Alembic migrations (`place_cache.display_name`, `client.birthplace_name`), no `downgrade()` body.
3. Update the tests named in §2 (`test_geocoder_nominatim.py`, `test_http_client_correction.py:410`)
   and add coverage for the new field's round-trip through creation, correction, and the chart
   wheel.
4. Resolve the one open, explicitly-flagged implementation decision in §2 (chart-wheel
   `city`/`nation` split) by inspection of the rendered SVG, not by speculative code.
5. Run `uv run pytest` locally before pushing (repo policy: work lands directly on `main`, no PR).

**Success criteria:** `client_edit.html`'s "Luogo di nascita" field is prefilled with the stored
place on every correction load; the chart wheel's Location header shows that same name; both
migrations are forward-only and pass `tests/test_migration_chain_on_postgres.py` against a real
Postgres per `AGENTS.md`'s standing warning; `uv run pytest` is green.

---

## 6. Approval

This proposal makes one schema change (two additive columns) and one architecture-invariant text
amendment (AD-16). Per this workflow's own gate, it needs your explicit sign-off before an
implementation pass begins:

**Do you approve this Sprint Change Proposal for implementation?**
