"""``/clients``: create a Client, or fail visibly (Story 2.3, AD-16).

Orchestrates birthplace resolution (Story 2.1's ``Geocoder``) and Natal Chart
computation (Story 2.2's ``compute_natal_chart()``) into a single persisted
Client -- or persists nothing, naming the step that failed.

``/clients/{id}/edit`` (Story 2.7) reuses the same resolve -> compute
orchestration to correct a Client's birth data, gated by an explicit
acknowledgment: the correction is shown back with a warning and persists
nothing until resubmitted with ``confirmed=1``, at which point the current
``StoredNatalChart`` row is marked superseded rather than overwritten.

No new error hierarchy: ``PlaceResolutionError`` (``.step``) and whatever
``compute_natal_chart()`` raises are caught and rendered as-is, mirroring
``login.html``'s error-banner pattern -- a wrapper error type would only
re-narrate a step name the domain errors already carry.

Authenticated by default: nothing here is named in ``shell.http.auth.ALLOWLIST``,
so ``AuthMiddleware`` guards both routes before a request ever reaches this
module.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from core.ephemeris.chart import compute_natal_chart
from core.errors import EphemerisIntegrityError, PlaceResolutionError
from core.types.place import PlaceCandidate
from shell.adapters.nominatim.geocoder import NominatimGeocoder
from shell.adapters.postgres.client import (
    Client,
    correct_client_and_chart,
    create_client_with_chart,
)
from shell.http.app import get_session
from shell.ports.geocoder import Geocoder

__all__ = ["get_geocoder", "router"]

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=_TEMPLATES_DIR)

#: The form fields every submission must carry, non-blank -- no partial
#: submission accepted (AC1).
_REQUIRED_FIELDS: tuple[str, ...] = ("name", "birth_date", "birth_time", "birthplace")

#: Errors raised while decoding a resubmitted candidate choice: malformed
#: JSON, a missing key, or a coordinate that is not a valid Decimal. All are
#: the same "the candidate selection is invalid" failure to the caller.
_CANDIDATE_DECODE_ERRORS: tuple[type[Exception], ...] = (
    json.JSONDecodeError,
    KeyError,
    TypeError,
    InvalidOperation,
)

#: A generous ceiling on the /clients POST body, mirroring
#: ``shell/http/app.py``'s ``_MAX_LOGIN_BODY_BYTES``. This form carries more
#: than a password -- name, date, time, birthplace, and a resubmitted
#: candidate's JSON -- so it is sized well above the login form's 4096, while
#: still rejecting a garbage-sized body before reading it.
_MAX_CLIENT_FORM_BODY_BYTES = 65536


class _FormTooLarge(Exception):
    """The declared or actual body size exceeds ``_MAX_CLIENT_FORM_BODY_BYTES``."""


class _FormNotUtf8(Exception):
    """The body could not be decoded as UTF-8."""


async def _parse_form(request: Request) -> dict[str, str]:
    """Hand-parsed, urlencoded body -- mirrors ``login_submit()`` in
    ``shell/http/app.py``, which reads the raw body rather than pulling in
    ``python-multipart`` for FastAPI's ``Form()``.

    Raises :class:`_FormTooLarge` for an oversized (or unstated) body and
    :class:`_FormNotUtf8` for a non-UTF-8 one -- both failing visibly with a
    422 rather than a 500, mirroring this story's own stated goal.
    """
    declared_length = request.headers.get("content-length")
    try:
        body_too_large = (
            declared_length is None or int(declared_length) > _MAX_CLIENT_FORM_BODY_BYTES
        )
    except ValueError:
        body_too_large = True
    if body_too_large:
        raise _FormTooLarge

    raw_body = await request.body()
    try:
        body = raw_body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _FormNotUtf8 from error
    return dict(parse_qsl(body))


def _missing_fields(fields: dict[str, str]) -> list[str]:
    return [name for name in _REQUIRED_FIELDS if not fields.get(name, "").strip()]


def _decode_candidate(raw: str) -> PlaceCandidate:
    payload: dict[str, Any] = json.loads(raw)
    return PlaceCandidate(
        display_name=payload["display_name"],
        latitude=Decimal(payload["latitude"]),
        longitude=Decimal(payload["longitude"]),
    )


def _candidate_context(candidates: list[PlaceCandidate] | None) -> list[dict[str, str]] | None:
    """Shared by ``/clients`` and ``/clients/{id}/edit``: each candidate's
    display name plus a single opaque ``value`` carrying everything
    ``resolve_candidate()`` needs back -- display_name plus the coordinates as
    strings (``Decimal(str(...))`` round-trips exactly; a raw float would
    not).
    """
    if not candidates:
        return None
    return [
        {
            "display_name": candidate.display_name,
            "value": json.dumps(
                {
                    "display_name": candidate.display_name,
                    "latitude": str(candidate.latitude),
                    "longitude": str(candidate.longitude),
                }
            ),
        }
        for candidate in candidates
    ]


def _render_form(
    request: Request,
    *,
    status_code: int,
    error: str | None = None,
    form: dict[str, str] | None = None,
    candidates: list[PlaceCandidate] | None = None,
) -> Response:
    return _templates.TemplateResponse(
        request,
        "client_new.html",
        {"error": error, "form": form or {}, "candidates": _candidate_context(candidates)},
        status_code=status_code,
    )


def _render_edit_form(
    request: Request,
    *,
    client_id: UUID,
    status_code: int,
    error: str | None = None,
    form: dict[str, str] | None = None,
    candidates: list[PlaceCandidate] | None = None,
    warning: bool = False,
) -> Response:
    return _templates.TemplateResponse(
        request,
        "client_edit.html",
        {
            "client_id": client_id,
            "error": error,
            "form": form or {},
            "candidates": _candidate_context(candidates),
            "warning": warning,
        },
        status_code=status_code,
    )


def get_geocoder(session: Session = Depends(get_session)) -> Geocoder:
    """The ``Geocoder`` this route resolves birthplaces through.

    A dependency of its own, not a bare call inline in the handler, so tests
    can substitute a fake without a real network call or the real timezone
    dataset (mirrors ``get_session`` itself). Depends on the same
    ``get_session`` the handler also depends on -- FastAPI's per-request
    dependency cache guarantees both resolve to the identical ``Session``, so
    a fresh unambiguous match's cache write and the Client/Natal Chart write
    share one transaction.
    """
    return NominatimGeocoder(session)


@router.get("/clients/new", include_in_schema=False)
def client_new_form(request: Request) -> Response:
    return _render_form(request, status_code=200)


@router.post("/clients", include_in_schema=False)
async def create_client(
    request: Request,
    session: Session = Depends(get_session),
    geocoder: Geocoder = Depends(get_geocoder),
) -> Response:
    try:
        fields = await _parse_form(request)
    except _FormTooLarge:
        return _render_form(request, status_code=422, error="the submitted form is too large.")
    except _FormNotUtf8:
        return _render_form(
            request, status_code=422, error="the submitted form is not valid UTF-8."
        )

    missing = _missing_fields(fields)
    if missing:
        return _render_form(
            request,
            status_code=422,
            error=f"Required: {', '.join(missing)}.",
            form=fields,
        )

    try:
        birth_date = date.fromisoformat(fields["birth_date"])
    except ValueError as error:
        return _render_form(
            request,
            status_code=422,
            error=f"birth_date is invalid: {error}",
            form=fields,
        )

    try:
        birth_time = datetime.strptime(fields["birth_time"], "%H:%M").time()
    except ValueError as error:
        return _render_form(
            request,
            status_code=422,
            error=f"birth_time is invalid: {error}",
            form=fields,
        )

    birth_local_time = datetime.combine(birth_date, birth_time)

    candidate_raw = fields.get("candidate")
    try:
        if candidate_raw:
            resolved = geocoder.resolve_candidate(
                _decode_candidate(candidate_raw), birth_local_time
            )
        else:
            resolution = geocoder.resolve(fields["birthplace"], birth_local_time)
            if isinstance(resolution, list):
                return _render_form(request, status_code=200, form=fields, candidates=resolution)
            resolved = resolution
    except PlaceResolutionError as error:
        return _render_form(request, status_code=422, error=str(error), form=fields)
    except _CANDIDATE_DECODE_ERRORS as error:
        return _render_form(
            request,
            status_code=422,
            error=f"the chosen birthplace candidate is invalid: {error}",
            form=fields,
        )

    birth_instant_utc = (birth_local_time - resolved.utc_offset).replace(tzinfo=UTC)

    computation_config = request.app.state.computation_config
    ephemeris_identity = request.app.state.ephemeris_identity

    try:
        natal_chart = compute_natal_chart(
            birth_instant_utc, resolved.latitude, resolved.longitude, computation_config
        )
    except (ValueError, EphemerisIntegrityError) as error:
        return _render_form(request, status_code=422, error=str(error), form=fields)

    client = create_client_with_chart(
        session,
        name=fields["name"],
        birth_date=birth_date,
        birth_time=birth_time,
        resolved_place=resolved,
        natal_chart=natal_chart,
        computation_config=computation_config,
        ephemeris_identity=ephemeris_identity,
    )
    session.commit()

    return Response(content=f"Client {client.id} created.", media_type="text/plain")


@router.get("/clients/{client_id}/edit", include_in_schema=False)
def client_edit_form(
    client_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """The correction form, prefilled from the stored Client row (Story 2.7).

    Birthplace has no stored free-text form to prefill from -- only resolved
    lat/lon/zone are stored -- so it starts blank and must be retyped even to
    reconfirm the same place; ``PLACE_CACHE`` makes that cheap.
    """
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404)

    form = {
        "name": client.name,
        "birth_date": client.birth_date.isoformat(),
        "birth_time": client.birth_time.strftime("%H:%M"),
        "birthplace": "",
    }
    return _render_edit_form(request, client_id=client_id, status_code=200, form=form)


@router.post("/clients/{client_id}/edit", include_in_schema=False)
async def correct_client(
    client_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    geocoder: Geocoder = Depends(get_geocoder),
) -> Response:
    """Correct a Client's birth data and Natal Chart (Story 2.7).

    Mirrors ``create_client``'s resolve -> compute sequence exactly, then adds
    a confirm gate before persistence: resolution and computation run on
    every submission (re-running resolution is cheap -- ``PLACE_CACHE``
    absorbs a repeat lookup), but nothing is written until the same fields
    are resubmitted with ``confirmed=1``. Only then does
    ``correct_client_and_chart()`` supersede the current chart, insert the
    new one, and update the Client row, all in one transaction.
    """
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404)

    try:
        fields = await _parse_form(request)
    except _FormTooLarge:
        return _render_edit_form(
            request,
            client_id=client_id,
            status_code=422,
            error="the submitted form is too large.",
        )
    except _FormNotUtf8:
        return _render_edit_form(
            request,
            client_id=client_id,
            status_code=422,
            error="the submitted form is not valid UTF-8.",
        )

    missing = _missing_fields(fields)
    if missing:
        return _render_edit_form(
            request,
            client_id=client_id,
            status_code=422,
            error=f"Required: {', '.join(missing)}.",
            form=fields,
        )

    try:
        birth_date = date.fromisoformat(fields["birth_date"])
    except ValueError as error:
        return _render_edit_form(
            request,
            client_id=client_id,
            status_code=422,
            error=f"birth_date is invalid: {error}",
            form=fields,
        )

    try:
        birth_time = datetime.strptime(fields["birth_time"], "%H:%M").time()
    except ValueError as error:
        return _render_edit_form(
            request,
            client_id=client_id,
            status_code=422,
            error=f"birth_time is invalid: {error}",
            form=fields,
        )

    birth_local_time = datetime.combine(birth_date, birth_time)

    candidate_raw = fields.get("candidate")
    try:
        if candidate_raw:
            resolved = geocoder.resolve_candidate(
                _decode_candidate(candidate_raw), birth_local_time
            )
        else:
            resolution = geocoder.resolve(fields["birthplace"], birth_local_time)
            if isinstance(resolution, list):
                return _render_edit_form(
                    request,
                    client_id=client_id,
                    status_code=200,
                    form=fields,
                    candidates=resolution,
                )
            resolved = resolution
    except PlaceResolutionError as error:
        return _render_edit_form(
            request, client_id=client_id, status_code=422, error=str(error), form=fields
        )
    except _CANDIDATE_DECODE_ERRORS as error:
        return _render_edit_form(
            request,
            client_id=client_id,
            status_code=422,
            error=f"the chosen birthplace candidate is invalid: {error}",
            form=fields,
        )

    birth_instant_utc = (birth_local_time - resolved.utc_offset).replace(tzinfo=UTC)

    computation_config = request.app.state.computation_config
    ephemeris_identity = request.app.state.ephemeris_identity

    try:
        natal_chart = compute_natal_chart(
            birth_instant_utc, resolved.latitude, resolved.longitude, computation_config
        )
    except (ValueError, EphemerisIntegrityError) as error:
        return _render_edit_form(
            request, client_id=client_id, status_code=422, error=str(error), form=fields
        )

    if fields.get("confirmed") != "1":
        # The acknowledgment gate (Story 2.7): the same fields that just
        # resolved and computed successfully are shown back with a warning,
        # nothing persisted, until resubmitted with `confirmed=1`.
        return _render_edit_form(
            request, client_id=client_id, status_code=200, form=fields, warning=True
        )

    correct_client_and_chart(
        session,
        client=client,
        name=fields["name"],
        birth_date=birth_date,
        birth_time=birth_time,
        resolved_place=resolved,
        natal_chart=natal_chart,
        computation_config=computation_config,
        ephemeris_identity=ephemeris_identity,
    )
    session.commit()

    return Response(content=f"Client {client.id} corrected.", media_type="text/plain")
