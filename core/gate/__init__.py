"""Groundedness Gate: Claim classification and verification against a Report Payload.

Every Claim in a generated Report will be checked against the Report Payload
before export (Story 5.2). This package currently holds the Story 5.1 half of
that: ``vocabulary.it.json``, the versioned closed Italian vocabulary that
decides what counts as a Claim, and ``classify.py``'s ``is_claim()``, the pure
function that applies it, per sentence.
"""
