# Conformance fixtures

This directory ships empty. It is the only content until **Story 1.7**
("Reference charts chosen to break the computation, not to flatter it")
transcribes the first reference charts from Astro.com — that story's actual
audience is this file, not a developer. Until then, `tests/test_conformance.py`
runs against zero fixtures and reports that count rather than failing (AC2).

## What a fixture is

One `*.toml` file per reference chart. `tests/conformance/runner.py` discovers
every `*.toml` file here (`discover_fixtures()`), sorted for determinism, and
loads each one (`load_fixture()`) into three required tables:

```toml
[metadata]
name = "leap-day-birth"
adversarial_case = "birth on 29 February"
source = "https://astro.com/... (or however the reference value was obtained)"

[birth_data]
date = "2000-02-29"
time = "14:30:00"
timezone = "Europe/Rome"
latitude = "41.9028"
longitude = "12.4964"

[expected]
# See "The expected table" below.
```

- **`[metadata]`** — free-form. At minimum, record which adversarial case
  this fixture targets (leap-day birth, a birth minutes either side of a
  historical DST switch, a near-midnight birth, a month containing a
  retrograde station, a month with two lunations of one kind and one with
  none, ...) and where the expected values were transcribed from. The runner
  never reads `metadata` itself — it exists for the human maintaining this
  directory. The fixture's stable identity for test IDs and mismatch reports
  is always the filename (its stem), not anything inside `metadata`.
- **`[birth_data]`** — whatever a chart computation needs: date, time,
  timezone, coordinates, and so on. Not validated by the runner; whatever the
  eventual computation call site (Epic 2/3) requires.
- **`[expected]`** — the transcribed Astro.com values this fixture is
  checked against. See below.

## The `expected` table

`expected` is compared against computed output as a plain nested
dict/list — **not** a schema-typed comparison against a fixed shape. This is
deliberate (see Story 1.6's Design Notes): Epic 2/3 haven't defined
`NatalChart`/`TransitEvent` shapes yet, so the fixture format stays whatever
shape the real computation eventually produces, described here loosely. A
natal fixture is expected to record:

- Planetary positions (e.g. `expected.planets = [{ name = "sun", longitude =
  "312.83", ... }, ...]`)
- House cusps (e.g. `expected.houses = [...]`)
- Natal Aspects (e.g. `expected.aspects = [...]`)

A **month fixture** (one covering a calendar month, not just a birth moment)
additionally records expected Transit Events for that month, e.g.
`expected.transit_events = [...]`.

Comparison walks `expected` field by field against the equivalent path in
computed output, building a dotted path for every field — arrays index with
`[N]`, e.g. `expected.planets[0].longitude`. A field present in `expected`
but missing, or differing, in computed output is a mismatch; it names the
fixture, the field's dotted path, the expected value and the computed value.
Extra fields present only in computed output are not reported — conformance
means computed output *contains* the expected values, not that it contains
nothing else.

Angles, orbs and similar numeric values should be recorded as TOML strings
(e.g. `longitude = "312.83"`), not bare floats — this project represents
angles as `Decimal` everywhere, never binary float, and a fixture is the
external boundary where that convention starts.

## Wiring in real computation

`tests/test_conformance.py` calls a single function, `compute_output_for()`,
to turn a `Fixture`'s `birth_data` into computed output shaped like
`expected`. It raises `NotImplementedError` until Epic 2/3 exist. Once they
do, making this harness real is that one function, not a redesign.
