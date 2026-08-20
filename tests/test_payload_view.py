"""``localize_payload()`` (Story 3.9, PRD FR-15): the one place any instant
stored by ``core/payload/freeze.py`` is converted out of UTC.

Each test below mirrors one row of the story's I/O & Edge-Case Matrix that
concerns ``localize_payload`` itself. The matrix's two 404 rows ("No
ReportPayload for run_id" / "Unknown run_id") are about the new route, not
this pure function -- they are covered in ``tests/test_http_report_runs.py``
instead.
"""

from __future__ import annotations

from shell.http.payload_view import localize_payload


def test_a_never_perfected_aspect_shows_no_perfection_time_but_localizes_its_window() -> None:
    """Matrix row: "Aspect never perfected" -- `perfected_at: null`, window
    fields set -> no perfection time shown, window still localized."""
    payload = {
        "sections": {
            "amore": {
                "aspects": [
                    {
                        "id": "deadbeef",
                        "kind": "aspect",
                        "transiting_body": "mars",
                        "natal_point": "venus",
                        "aspect": "trine",
                        "perfected_at": None,
                        "never_perfected": True,
                        "orb_entry_at": "2026-01-05T12:00:00+00:00",
                        "orb_exit_at": "2026-01-20T18:00:00+00:00",
                    }
                ]
            }
        }
    }

    localized = localize_payload(payload, iana_zone="America/Chicago")

    entry = localized["sections"]["amore"]["aspects"][0]
    assert entry["perfected_at"] is None
    assert entry["orb_entry_at"] == "2026-01-05 06:00:00 CST"
    assert entry["orb_exit_at"] == "2026-01-20 12:00:00 CST"


def test_an_aspect_still_in_orb_at_month_end_shows_no_exit_time() -> None:
    """Matrix row: "Aspect still open at month end" -- `orb_exit_at: null` ->
    no exit time shown."""
    payload = {
        "sections": {
            "amore": {
                "aspects": [
                    {
                        "id": "deadbeef",
                        "orb_entry_at": "2026-01-28T00:00:00+00:00",
                        "orb_exit_at": None,
                    }
                ]
            }
        }
    }

    localized = localize_payload(payload, iana_zone="America/Chicago")

    entry = localized["sections"]["amore"]["aspects"][0]
    assert entry["orb_entry_at"] == "2026-01-27 18:00:00 CST"
    assert entry["orb_exit_at"] is None


def test_a_non_datetime_string_field_passes_through_unchanged() -> None:
    """Matrix row: "Non-datetime string field" -- e.g. `id` (sha256), `aspect`
    ("trine") -> passes through unchanged."""
    payload = {
        "sections": {
            "amore": {
                "aspects": [
                    {
                        "id": "3f5c9a2b1e7d4f6a8c0b2d4e6f8a0c2e4f6a8c0b2d4e6f8a0c2e4f6a8c0b2d4e",
                        "aspect": "trine",
                    }
                ]
            }
        }
    }

    localized = localize_payload(payload, iana_zone="America/Chicago")

    entry = localized["sections"]["amore"]["aspects"][0]
    assert entry["id"] == "3f5c9a2b1e7d4f6a8c0b2d4e6f8a0c2e4f6a8c0b2d4e6f8a0c2e4f6a8c0b2d4e"
    assert entry["aspect"] == "trine"


def test_localizing_a_payload_from_a_run_months_ago_is_identical_to_a_fresh_one() -> None:
    """Matrix row: "Payload from a run months ago" -- any stored ReportPayload
    row renders identically to a fresh one. ``localize_payload`` consults no
    clock, so it is deterministic given the same two arguments regardless of
    when the payload was originally frozen."""
    payload = {
        "sections": {
            "amore": {"aspects": [{"id": "abc", "orb_entry_at": "2026-01-05T12:00:00+00:00"}]}
        },
        "day_lists": {"giorni_favorevoli": [], "giorni_di_attenzione": []},
    }

    first = localize_payload(payload, iana_zone="America/Chicago")
    second = localize_payload(payload, iana_zone="America/Chicago")

    assert first == second


def test_ids_hashes_and_enum_strings_at_any_depth_pass_through_unchanged() -> None:
    """No key-name special-casing: an id/enum string nested inside a Domain
    Profile block (not just an event dict) also fails ``fromisoformat()`` and
    passes through unchanged."""
    payload = {"sections": {"amore": {"profile": {"venus": {"sign": "leo", "house": 5}}}}}

    localized = localize_payload(payload, iana_zone="America/Chicago")

    assert localized["sections"]["amore"]["profile"]["venus"]["sign"] == "leo"
    assert localized["sections"]["amore"]["profile"]["venus"]["house"] == 5


def test_a_naive_iso_string_passes_through_unchanged_instead_of_assuming_server_time() -> None:
    """Defense-in-depth: every stored instant is tz-aware by construction
    (``core/payload/freeze.py``'s ``_json_safe``), so this should never occur
    on the real path -- but a naive (tzinfo-less) ``fromisoformat()``-
    parseable string must still pass through unconverted rather than being
    silently interpreted as the *server's* local time by ``astimezone()``,
    which would produce a wrong, environment-dependent result."""
    payload = {"sections": {"amore": {"aspects": [{"orb_entry_at": "2026-01-05T12:00:00"}]}}}

    localized = localize_payload(payload, iana_zone="America/Chicago")

    assert localized["sections"]["amore"]["aspects"][0]["orb_entry_at"] == "2026-01-05T12:00:00"
