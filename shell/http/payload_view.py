"""Localize a stored ``ReportPayload``'s UTC instants to a Client's local
time (Story 3.9, PRD FR-15, AD-12: "local-time conversion happens only in
``shell/http/``").

The one and only place any instant stored by ``core/payload/freeze.py`` is
converted out of UTC -- ``core/`` and every other ``shell/`` module keep
recording and reading UTC, unchanged.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from core.types.payload import SectionPayload

__all__ = ["FIELD_TITLES", "SECTION_PAYLOAD_FIELD_NAMES", "localize_payload"]

#: Every ``SectionPayload`` field name, in the dataclass's own fixed order --
#: introspected rather than hand-listed, mirroring ``shell/http/draft_view
#: .py``'s own ``SECTION_ORDER`` (a future ``SectionPayload`` field is picked
#: up here automatically, so ``FIELD_TITLES``' parity test below cannot
#: silently pass a field with no Italian heading).
SECTION_PAYLOAD_FIELD_NAMES: tuple[str, ...] = tuple(
    field.name for field in dataclass_fields(SectionPayload)
)

#: The Italian display heading for each ``SectionPayload`` field name (Story
#: 9.9) -- mirrors ``shell/http/draft_view.py``'s ``SECTION_TITLES`` shape:
#: an explicit dict, not a generic transform, since these are read by
#: ``report_payload.html`` as a bare heading (``<h3>{{ field_name }}</h3>``
#: previously rendered the raw snake_case key, including for the untranslated
#: ``profile`` field this story fixes). Keyed by ``core.types.payload
#: .SectionPayload``'s own field names -- exactly ``SECTION_PAYLOAD_FIELD_NAMES``,
#: bound by ``tests/test_payload_view.py``.
FIELD_TITLES: dict[str, str] = {
    "profile": "Profilo",
    "aspects": "Aspetti",
    "stations": "Stazionamenti",
    "standing_retrogrades": "Retrogradazioni in corso",
    "ingresses": "Ingressi",
    "lunations": "Lunazioni",
}


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
        return parsed.astimezone(zone).strftime("%d/%m/%Y %H:%M")
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
