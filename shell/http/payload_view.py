"""Localize a stored ``ReportPayload``'s UTC instants to a Client's local
time (Story 3.9, PRD FR-15, AD-12: "local-time conversion happens only in
``shell/http/``").

The one and only place any instant stored by ``core/payload/freeze.py`` is
converted out of UTC -- ``core/`` and every other ``shell/`` module keep
recording and reading UTC, unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

__all__ = ["localize_payload"]


def _localize_value(value: Any, zone: ZoneInfo) -> Any:
    """Deep-walk one value: a dict/list recurses into its items; a ``str``
    parseable via ``datetime.fromisoformat()`` *and* tz-aware is converted to
    ``zone`` and formatted; anything else (an id, an enum string like
    ``"trine"``, a number, a bool, ``None``) passes through unchanged.

    Every stored instant is ISO 8601 tz-aware (``core/payload/freeze.py``'s
    ``_json_safe``), so no key-name special-casing is needed here -- an id or
    enum string simply fails ``fromisoformat()`` and falls through. A naive
    (tzinfo-less) parseable string is never expected either, but is also
    passed through unchanged rather than converted: ``astimezone()`` on a
    naive ``datetime`` silently assumes the *server's* local time rather than
    UTC, which would produce a wrong, environment-dependent result instead of
    failing loudly -- this codepath exists purely as a defense against that
    invariant ever being violated upstream.
    """
    if isinstance(value, dict):
        return {key: _localize_value(item, zone) for key, item in value.items()}
    if isinstance(value, list):
        return [_localize_value(item, zone) for item in value]
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value
        if parsed.tzinfo is None:
            return value
        return parsed.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")
    return value


def localize_payload(payload: dict[str, Any], *, iana_zone: str) -> dict[str, Any]:
    """``payload`` (a stored ``ReportPayload.payload`` dict, verbatim) with
    every UTC instant inside it converted to ``iana_zone`` local time.

    Resolves ``ZoneInfo(iana_zone)`` once and deep-walks the whole dict/list
    structure -- no per-``sections``/``day_lists``-key branch, mirroring
    ``core/payload/freeze.py``'s own generic, kind-agnostic walk.
    """
    zone = ZoneInfo(iana_zone)
    return _localize_value(payload, zone)
