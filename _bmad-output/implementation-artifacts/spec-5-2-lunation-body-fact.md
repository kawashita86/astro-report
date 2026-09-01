---
title: 'Story 5.2 amendment — a Lunation citation grounds "luna"'
type: 'fix'
created: '2026-09-01'
status: 'done'
review_loop_iteration: 0
route: 'one-shot'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/spec-5-2-check-every-claim-against-the-payload.md'
---

## Intent

**Problem:** Story 5.2's frozen Design Notes category table never listed `lunation` as a kind
asserting a body/sign fact (only `aspect`/`station`/`standing_retrogade`/`ingress` do), and
`core/types/transits.py::Lunation` carries no `body` field at all -- so `core/gate/run.py::
_body_sign_facts()` gathered nothing for a cited Lunation. Every well-formed, non-hallucinated
sentence describing a New/Full Moon by its natural Italian name ("Luna Nuova"/"Luna Piena")
therefore failed the Groundedness Gate as `"invented_fact"` for the word "luna" -- not
occasionally, but on every Report carrying a Lunation, since one occurs most months and Italian
has no natural way to name it without the word. Confirmed live against a real October 2026
Report generation and its Payload during manual testing with Francesco (2026-09-01); he asked for
this frozen decision to be renegotiated and fixed.

**Approach:** `_body_sign_facts()` now treats every cited `"kind": "lunation"` entry as asserting
`"moon"` -- a Lunation *is* the Moon by definition (Delta-lambda between Moon and Sun crossing
0/180 degrees), which is exactly why `Lunation` never stored a redundant `body` field; the category
table omitted it by oversight, not by intent. No sign fact is added for the same entry: deriving a
sign from a Lunation's raw `longitude` would be re-deriving astronomy from a degree, which AD-1's
Never section still forbids -- a sign-naming Claim citing only a Lunation still correctly fails,
now as `"contradicted_fact"` (the entry does assert a body/sign-category fact, "moon", it is just
not the claimed sign) rather than `"invented_fact"` (nothing asserted at all).

**Consequence surfaced by this fix:** since every one of the five real Payload entry kinds
`_body_sign_facts()` recognizes now asserts *some* body/sign fact, a Claim naming a body/sign the
cited entry(ies) do not support is always `"contradicted_fact"` going forward -- `"invented_fact"`
for this category is only reachable when a Claim's cited id(s) resolve to no entry at all. This is
a correctness improvement (a fact-bearing entry that simply doesn't match is a contradiction, not
an absence), not a scope change to what the Gate checks.

## Suggested Review Order

**The fact-extraction fix**

- `_body_sign_facts()` gains a `"lunation"` branch asserting `"moon"` unconditionally, with the
  reasoning against re-deriving a sign spelled out inline.
  [`run.py:252`](../../core/gate/run.py#L252)

**Tests**

- The Design Notes' own golden example (`"La luna piena illumina la tua quinta casa."`) no longer
  double-fails on body/sign, only on its deliberate wrong-house claim; a new companion test proves
  the positive case (a correct "Luna Nuova" sentence with no other Claim now passes outright).
  [`test_gate_run.py:202`](../../tests/test_gate_run.py#L202)
- Every other test citing a Lunation with a *different* body/sign word (Saturn, Leone, Marte) is
  updated from `"invented_fact"` to `"contradicted_fact"`, per the Consequence above; one test is
  added/adjusted to still exercise the `"invented_fact"` branch via an unresolvable cited id, since
  no real entry kind can demonstrate it anymore.
  [`test_gate_run.py:249`](../../tests/test_gate_run.py#L249)

## Spec Change Log

- Renegotiates Story 5.2's frozen Design Notes body/sign category table (human-authorized directly
  by Francesco, not routed through a separate sprint-change-proposal document, given the narrow,
  single-function scope). The original `spec-5-2-check-every-claim-against-the-payload.md` is left
  unmodified as the historical record of what was originally approved; this file is the amendment.
