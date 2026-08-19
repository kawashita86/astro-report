"""Resolves a Client's requested month (``"YYYY-MM"``) to the half-open UTC
interval ``[month_start_utc, month_end_utc)`` Story 3.1-3.4's four scan
functions take as an already-resolved fact (Story 3.5).

Deriving that interval was explicitly deferred by every one of those
stories -- each takes ``[month_start_utc, month_end_utc)`` as a plain
argument and knows nothing about a Client's local calendar. This is the one
place that conversion happens, against ``Client.iana_zone`` (AD-16's
immutable birthplace snapshot resolved once at Client creation), never a
request-time input.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shell.adapters.postgres.client import Client

__all__ = ["client_month_interval_utc"]

#: The wire format `client_month_interval_utc` accepts -- a plain
#: `datetime.strptime` round trip rather than a hand-rolled regex, so the
#: same standard-library parser that rejects "2026-13" or "2026-1" (missing
#: zero-pad) also rejects everything else malformed in one place.
_MONTH_FORMAT = "%Y-%m"


def client_month_interval_utc(client: Client, month: str) -> tuple[datetime, datetime]:
    """The half-open UTC interval covering ``month`` (``"YYYY-MM"``) in
    ``client``'s local calendar (``client.iana_zone``).

    Local midnight on the 1st of ``month`` through local midnight on the 1st
    of the following month, both resolved against ``client.iana_zone`` via
    ``zoneinfo``. A month boundary that a zone's DST transition falls on
    still resolves to a single, unambiguous UTC pair rather than raising:
    per PEP 495, ``zoneinfo`` always picks one well-defined UTC offset for a
    local wall-clock time a fold (repeated) or gap (skipped) makes
    ambiguous, using the pre-transition offset by default (``fold=0``, never
    overridden here) -- it never leaves the question open.

    Raises:
        ValueError: ``month`` is not ``"YYYY-MM"``, or ``client.iana_zone``
            names a zone :mod:`zoneinfo` cannot find.
    """
    try:
        parsed = datetime.strptime(month, _MONTH_FORMAT)
    except ValueError as error:
        raise ValueError(f"month must be 'YYYY-MM', got {month!r}.") from error

    # `ZoneInfoNotFoundError` is a `KeyError` subclass -- re-raised as
    # `ValueError` so both of this function's failure modes (a malformed
    # `month`, an unresolvable `client.iana_zone`) are the same exception
    # type to a caller, matching how the rest of this codebase never lets a
    # bare stdlib exception escape a public function uncaught.
    try:
        zone = ZoneInfo(client.iana_zone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            f"client.iana_zone names an unknown zone: {client.iana_zone!r}."
        ) from error
    start_local = datetime(parsed.year, parsed.month, 1, tzinfo=zone)
    if parsed.month == 12:
        end_local = datetime(parsed.year + 1, 1, 1, tzinfo=zone)
    else:
        end_local = datetime(parsed.year, parsed.month + 1, 1, tzinfo=zone)

    return start_local.astimezone(UTC), end_local.astimezone(UTC)
