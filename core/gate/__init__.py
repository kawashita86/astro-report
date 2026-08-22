"""Groundedness Gate: Claim classification and verification against a Report Payload.

Every Claim in a generated Report will be checked against the Report
Payload before export -- Story 5.3 wires ``run_gate()`` in as the sole path
to an exportable Report; this package provides the check itself, not that
wiring. It holds both halves that make the check possible:
``vocabulary.it.json`` and ``classify.py``'s ``is_claim()`` (Story 5.1)
decide what counts as a Claim; ``run.py``'s ``run_gate()`` (Story 5.2)
checks every Claim it finds for citation presence and factual agreement
with the Payload entries it cites, plus the unconditional Section 6/7
date-token check. Both are pure: no I/O, no model call, no clock.
"""
