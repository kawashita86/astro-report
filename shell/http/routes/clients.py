"""``/clients``: create a Client, or fail visibly (Story 2.3, AD-16).

Orchestrates birthplace resolution (Story 2.1's ``Geocoder``) and Natal Chart
computation (Story 2.2's ``compute_natal_chart()``) into a single persisted
Client -- or persists nothing, naming the step that failed.

``/clients/{id}/edit`` (Story 2.7) reuses the same resolve -> compute
orchestration to correct a Client's birth data, gated by an explicit
acknowledgment: the correction is shown back with a warning and persists
nothing until resubmitted with ``confirmed=1``, at which point the current
``StoredNatalChart`` row is marked superseded rather than overwritten.

``/clients/{id}/delete`` (Story 2.8) hard-deletes a Client and every
``StoredNatalChart`` row for it (current and superseded), gated by the same
confirm-then-act shape as the correction route: nothing is deleted until the
confirmation page's form is resubmitted with ``confirmed=1``.

No new error hierarchy: ``PlaceResolutionError`` (``.step``) and whatever
``compute_natal_chart()`` raises are caught and rendered as-is, mirroring
``login.html``'s error-banner pattern -- a wrapper error type would only
re-narrate a step name the domain errors already carry. Deletion has no
resolution or computation step to fail once the client is found -- a 404 for
an unknown id and a 422 for a malformed body (``parse_form``'s own two
failure modes) are its only error paths.

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
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from core.ephemeris.chart import compute_natal_chart
from core.errors import EphemerisIntegrityError, PlaceResolutionError
from core.types.place import PlaceCandidate
from shell.adapters.nominatim.geocoder import NominatimGeocoder
from shell.adapters.postgres.backup_record import backup_is_stale
from shell.adapters.postgres.client import (
    Client,
    StoredNatalChart,
    correct_client_and_chart,
    create_client_with_chart,
    delete_client_and_derived,
    list_clients,
)
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_run import ReportRun
from shell.http.app import get_session
from shell.http.auth import log_client_deleted
from shell.http.flash import _flash_context_processor
from shell.http.form import FormNotUtf8, FormTooLarge, parse_form
from shell.ports.geocoder import Geocoder

__all__ = ["get_geocoder", "router"]

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(
    directory=_TEMPLATES_DIR, context_processors=[_flash_context_processor]
)

#: The form fields every submission must carry, non-blank -- no partial
#: submission accepted (AC1).
_REQUIRED_FIELDS: tuple[str, ...] = ("name", "birth_date", "birth_time", "birthplace")

#: Derived from ``Client.name``'s own ``Field(max_length=200)``
#: (deferred-work item 41) rather than a second hardcoded number, so the two
#: bounds cannot drift apart. Rejected here, before resolution or
#: computation runs, since ``name`` is the only one of the three
#: newly-bounded columns a caller submits as raw text
#: (``iana_zone``/``computation_config_content_hash`` are never user-typed).
_MAX_NAME_LENGTH: int = Client.__table__.c.name.type.length

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

#: Fixed Italian copy for every error/field-error site below (Story 9.9,
#: EXPERIENCE.md's Voice and Tone). None of these ever interpolate a raw
#: exception's own message or a parser's own text: ``PlaceResolutionError``,
#: the candidate-decode errors, and ``compute_natal_chart()``'s own
#: ``ValueError``/``EphemerisIntegrityError`` all originate in ``core``/
#: adapter code and stay English there by the architecture's naming rule --
#: translating that text at the source would violate it, so each catch site
#: here substitutes one of these fixed messages instead (this story's Design
#: Notes). ``date.fromisoformat()``/``strptime()``'s own parser messages are
#: dropped the same way, per this story's I/O & Edge-Case Matrix ("no raw
#: parser text").
_ERROR_FORM_TOO_LARGE = "Il modulo inviato è troppo grande."
_ERROR_FORM_NOT_UTF8 = "Il modulo inviato non è in una codifica UTF-8 valida."

_FIELD_REQUIRED_MESSAGES: dict[str, str] = {
    "name": "Il nome è obbligatorio.",
    "birth_date": "La data di nascita è obbligatoria.",
    "birth_time": "L'ora di nascita è obbligatoria.",
    "birthplace": "Il luogo di nascita è obbligatorio.",
}
_ERROR_NAME_TOO_LONG = f"Il nome non può superare {_MAX_NAME_LENGTH} caratteri."
_ERROR_BIRTH_DATE_INVALID = "La data di nascita non è valida. Usa il formato AAAA-MM-GG."
_ERROR_BIRTH_TIME_INVALID = "L'ora di nascita non è valida. Usa il formato HH:mm."
#: Covers every ``PlaceResolutionError`` -- not only "no match for the typed
#: text" (``shell/adapters/nominatim/geocoder.py``'s ``_geocode``) but also a
#: cache-read failure, a geocoding-service error and a timezone-resolution
#: failure (its ``_lookup_cache``/``_geocode``/``_zone_for``/
#: ``_historical_offset`` raise sites). Deliberately does not suggest
#: retyping the birthplace -- that would be misleading when the real cause is
#: an infra failure the operator's own text had nothing to do with.
_ERROR_BIRTHPLACE_UNRESOLVED = (
    "Non è stato possibile verificare il luogo di nascita indicato. Riprova."
)
_ERROR_CANDIDATE_INVALID = (
    "La selezione del luogo non è valida. Ricomincia la ricerca del luogo di nascita."
)
_ERROR_CHART_COMPUTATION_FAILED = (
    "Impossibile calcolare il tema natale con i dati forniti. "
    "Verifica data, ora e luogo di nascita."
)


def _correction_summary(action: str, field_count: int) -> str:
    """The form-summary sentence at the top of the error banner (Voice and
    Tone: "cosa è successo" + "cosa fare"), pluralized by how many fields are
    flagged below it. Matches EXPERIENCE.md's own example verbatim at
    ``field_count == 2``: "Impossibile creare il cliente. Correggi i 2 campi
    segnalati qui sotto."
    """
    if field_count == 1:
        return f"Impossibile {action}. Correggi il campo segnalato qui sotto."
    return f"Impossibile {action}. Correggi i {field_count} campi segnalati qui sotto."


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
    field_errors: dict[str, str] | None = None,
) -> Response:
    return _templates.TemplateResponse(
        request,
        "client_new.html",
        {
            "error": error,
            "form": form or {},
            "candidates": _candidate_context(candidates),
            "field_errors": field_errors,
        },
        status_code=status_code,
    )


def _render_edit_form(
    request: Request,
    *,
    client: Client,
    session: Session,
    status_code: int,
    error: str | None = None,
    form: dict[str, str] | None = None,
    candidates: list[PlaceCandidate] | None = None,
    warning: bool = False,
    field_errors: dict[str, str] | None = None,
) -> Response:
    return _templates.TemplateResponse(
        request,
        "client_edit.html",
        {
            "client": client,
            "client_id": client.id,
            "active_tab": "anagrafica",
            "error": error,
            "form": form or {},
            "candidates": _candidate_context(candidates),
            "warning": warning,
            "field_errors": field_errors,
            # Presentation-only (Story 9.4): decides whether the delete modal
            # and the no-JS confirm page name the retained superseded chart.
            "has_superseded_chart": _has_superseded_chart(session, client.id),
        },
        status_code=status_code,
    )


def _render_delete_form(
    request: Request,
    *,
    client_id: UUID,
    client_name: str,
    status_code: int,
    has_superseded_chart: bool,
    error: str | None = None,
) -> Response:
    return _templates.TemplateResponse(
        request,
        "client_delete.html",
        {
            "client_id": client_id,
            "client_name": client_name,
            "has_superseded_chart": has_superseded_chart,
            "error": error,
        },
        status_code=status_code,
    )


def _has_superseded_chart(session: Session, client_id: UUID) -> bool:
    return (
        session.exec(
            select(StoredNatalChart).where(
                StoredNatalChart.client_id == client_id,
                StoredNatalChart.superseded_at.is_not(None),
            )
        ).first()
        is not None
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


@router.get("/clients", include_in_schema=False)
def list_clients_view(request: Request, session: Session = Depends(get_session)) -> Response:
    """The Client roster (Story 9.3): every Client in ``list_clients`` order
    (``name`` then ``id``), each row carrying its birth date/time pre-formatted
    ``dd/MM/yyyy`` / ``HH:mm`` and a flag for whether any ``StoredNatalChart``
    for that Client has been superseded.

    Presentation only -- ``list_clients(session)`` is reused verbatim for
    ordering, there is no new query shape, no pagination, and no server-side
    filtering (the name filter is entirely client-side). The superseded-chart
    set is one batched ``distinct`` query -- the set-valued form of
    :func:`_has_superseded_chart`, never that predicate called in a loop.
    """
    clients = list_clients(session)

    superseded_client_ids: set[UUID] = set(
        session.exec(
            select(StoredNatalChart.client_id)
            .where(StoredNatalChart.superseded_at.is_not(None))
            .distinct()
        ).all()
    )

    rows = [
        {
            "id": client.id,
            "name": client.name,
            "birth_date": client.birth_date.strftime("%d/%m/%Y"),
            "birth_time": client.birth_time.strftime("%H:%M"),
            "has_superseded_chart": client.id in superseded_client_ids,
        }
        for client in clients
    ]

    return _templates.TemplateResponse(request, "client_list.html", {"clients": rows})


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
        fields = await parse_form(request, max_bytes=_MAX_CLIENT_FORM_BODY_BYTES)
    except FormTooLarge:
        return _render_form(request, status_code=422, error=_ERROR_FORM_TOO_LARGE)
    except FormNotUtf8:
        return _render_form(request, status_code=422, error=_ERROR_FORM_NOT_UTF8)

    missing = _missing_fields(fields)
    if missing:
        return _render_form(
            request,
            status_code=422,
            error=_correction_summary("creare il cliente", len(missing)),
            form=fields,
            field_errors={field: _FIELD_REQUIRED_MESSAGES[field] for field in missing},
        )

    if len(fields["name"]) > _MAX_NAME_LENGTH:
        return _render_form(
            request,
            status_code=422,
            error=_correction_summary("creare il cliente", 1),
            form=fields,
            field_errors={"name": _ERROR_NAME_TOO_LONG},
        )

    try:
        birth_date = date.fromisoformat(fields["birth_date"])
    except ValueError:
        return _render_form(
            request,
            status_code=422,
            error=_correction_summary("creare il cliente", 1),
            form=fields,
            field_errors={"birth_date": _ERROR_BIRTH_DATE_INVALID},
        )

    try:
        birth_time = datetime.strptime(fields["birth_time"], "%H:%M").time()
    except ValueError:
        return _render_form(
            request,
            status_code=422,
            error=_correction_summary("creare il cliente", 1),
            form=fields,
            field_errors={"birth_time": _ERROR_BIRTH_TIME_INVALID},
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
    except PlaceResolutionError:
        return _render_form(
            request,
            status_code=422,
            error=_correction_summary("creare il cliente", 1),
            form=fields,
            field_errors={"birthplace": _ERROR_BIRTHPLACE_UNRESOLVED},
        )
    except _CANDIDATE_DECODE_ERRORS:
        return _render_form(
            request,
            status_code=422,
            error=_correction_summary("creare il cliente", 1),
            form=fields,
            field_errors={"birthplace": _ERROR_CANDIDATE_INVALID},
        )

    birth_instant_utc = (birth_local_time - resolved.utc_offset).replace(tzinfo=UTC)

    computation_config = request.app.state.computation_config
    ephemeris_identity = request.app.state.ephemeris_identity

    try:
        natal_chart = compute_natal_chart(
            birth_instant_utc, resolved.latitude, resolved.longitude, computation_config
        )
    except (ValueError, EphemerisIntegrityError):
        # Not field-attributable: no field on this form maps to "the
        # ephemeris computation itself failed" -- stays a form-level-only
        # message. Never the raw exception text (this story's Design Notes):
        # core/adapter exception messages stay English by the architecture's
        # naming rule, so a fixed Italian message substitutes for it here.
        return _render_form(
            request, status_code=422, error=_ERROR_CHART_COMPUTATION_FAILED, form=fields
        )

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

    # A real template, not a bare fragment (Story 9.8 closes Story 9.4's
    # deferral): Italian success wording (Story 9.9, EXPERIENCE.md's Voice
    # and Tone) and the same link straight to the new Client's
    # chart-verification view (epic-2-retro-item-14) -- still a 200, not a
    # redirect (a 303 to the SVG page would be followed and lose the
    # outcome) -- now delivered inside base.html's chrome, with the success
    # message riding as `flash`
    # in the template context rather than a fourth, bespoke delivery path.
    # `flash.message` is plain text, escaped like any other Jinja variable;
    # the chart link is `client_action_result.html`'s own markup, driven by
    # `chart_href`, never HTML smuggled through the flash message.
    return _templates.TemplateResponse(
        request,
        "client_action_result.html",
        {
            "flash": {"kind": "success", "message": f"Cliente {client.id} creato."},
            "chart_href": f"/clients/{client.id}/chart",
            "heading": "Clienti",
        },
        status_code=200,
    )


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
    return _render_edit_form(request, client=client, session=session, status_code=200, form=form)


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
        fields = await parse_form(request, max_bytes=_MAX_CLIENT_FORM_BODY_BYTES)
    except FormTooLarge:
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_ERROR_FORM_TOO_LARGE,
        )
    except FormNotUtf8:
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_ERROR_FORM_NOT_UTF8,
        )

    missing = _missing_fields(fields)
    if missing:
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_correction_summary("salvare la correzione", len(missing)),
            form=fields,
            field_errors={field: _FIELD_REQUIRED_MESSAGES[field] for field in missing},
        )

    if len(fields["name"]) > _MAX_NAME_LENGTH:
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_correction_summary("salvare la correzione", 1),
            form=fields,
            field_errors={"name": _ERROR_NAME_TOO_LONG},
        )

    try:
        birth_date = date.fromisoformat(fields["birth_date"])
    except ValueError:
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_correction_summary("salvare la correzione", 1),
            form=fields,
            field_errors={"birth_date": _ERROR_BIRTH_DATE_INVALID},
        )

    try:
        birth_time = datetime.strptime(fields["birth_time"], "%H:%M").time()
    except ValueError:
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_correction_summary("salvare la correzione", 1),
            form=fields,
            field_errors={"birth_time": _ERROR_BIRTH_TIME_INVALID},
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
                    client=client,
                    session=session,
                    status_code=200,
                    form=fields,
                    candidates=resolution,
                )
            resolved = resolution
    except PlaceResolutionError:
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_correction_summary("salvare la correzione", 1),
            form=fields,
            field_errors={"birthplace": _ERROR_BIRTHPLACE_UNRESOLVED},
        )
    except _CANDIDATE_DECODE_ERRORS:
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_correction_summary("salvare la correzione", 1),
            form=fields,
            field_errors={"birthplace": _ERROR_CANDIDATE_INVALID},
        )

    # Commit right after a successful resolve (via `resolve()` or
    # `resolve_candidate()`) and before `compute_natal_chart()` is even
    # attempted, so a fresh place's PLACE_CACHE write-through (nested
    # transaction, `store_resolved_place()`) survives this request's
    # session closing -- `get_session`'s own docstring: closing a session
    # without an explicit commit rolls back any pending work, including a
    # nested PLACE_CACHE write. This covers every early-return path between
    # here and the confirm gate uniformly (a `compute_natal_chart()`
    # failure below, or the warning-branch return further down), not only
    # the warning branch. Nothing else is pending on this session at this
    # point (no Client/Chart write happens before the confirm gate), so
    # this commit only ever durably persists that cache write, never a
    # partial correction.
    session.commit()

    birth_instant_utc = (birth_local_time - resolved.utc_offset).replace(tzinfo=UTC)

    computation_config = request.app.state.computation_config
    ephemeris_identity = request.app.state.ephemeris_identity

    try:
        natal_chart = compute_natal_chart(
            birth_instant_utc, resolved.latitude, resolved.longitude, computation_config
        )
    except (ValueError, EphemerisIntegrityError):
        # Not field-attributable, mirrors create_client's own chart-
        # computation failure -- stays a form-level-only message, never the
        # raw exception text (this story's Design Notes).
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=422,
            error=_ERROR_CHART_COMPUTATION_FAILED,
            form=fields,
        )

    if fields.get("confirmed") != "1":
        # The acknowledgment gate (Story 2.7): the same fields that just
        # resolved and computed successfully are shown back with a warning,
        # nothing persisted, until resubmitted with `confirmed=1`.
        return _render_edit_form(
            request,
            client=client,
            session=session,
            status_code=200,
            form=fields,
            warning=True,
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

    # See create_client: a real template with Italian success wording plus
    # the same link to the chart view (epic-2-retro-item-14), still a 200,
    # not a redirect.
    return _templates.TemplateResponse(
        request,
        "client_action_result.html",
        {
            "flash": {"kind": "success", "message": f"Cliente {client.id} corretto."},
            "chart_href": f"/clients/{client.id}/chart",
            "heading": "Clienti",
        },
        status_code=200,
    )


@router.get("/clients/{client_id}/delete", include_in_schema=False)
def client_delete_form(
    client_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """The deletion confirmation page (Story 2.8). Nothing is deleted on GET."""
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404)

    return _render_delete_form(
        request,
        client_id=client_id,
        client_name=client.name,
        status_code=200,
        has_superseded_chart=_has_superseded_chart(session, client_id),
    )


@router.post("/clients/{client_id}/delete", include_in_schema=False)
async def delete_client(
    client_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Delete a Client and everything derived from it (Story 2.8).

    Mirrors ``correct_client``'s confirm gate: the form must carry
    ``confirmed=1`` or nothing is deleted and the same confirmation page is
    re-rendered. Deletion takes no new input beyond that flag, so the only
    error paths here are the 404 for an unknown client and a 422 for a
    malformed body -- too large or not valid UTF-8 -- mirroring
    ``create_client``/``correct_client``'s own handling of ``parse_form``'s
    two failure modes (no external resolution or computation runs that could
    fail once the client is found and the body parses).
    """
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404)

    try:
        fields = await parse_form(request, max_bytes=_MAX_CLIENT_FORM_BODY_BYTES)
    except FormTooLarge:
        return _render_delete_form(
            request,
            client_id=client_id,
            client_name=client.name,
            status_code=422,
            has_superseded_chart=_has_superseded_chart(session, client_id),
            error=_ERROR_FORM_TOO_LARGE,
        )
    except FormNotUtf8:
        return _render_delete_form(
            request,
            client_id=client_id,
            client_name=client.name,
            status_code=422,
            has_superseded_chart=_has_superseded_chart(session, client_id),
            error=_ERROR_FORM_NOT_UTF8,
        )

    if fields.get("confirmed") != "1":
        return _render_delete_form(
            request,
            client_id=client_id,
            client_name=client.name,
            status_code=200,
            has_superseded_chart=_has_superseded_chart(session, client_id),
        )

    delete_client_and_derived(session, client=client)
    session.commit()
    log_client_deleted(client_id)

    # See create_client: a real template with Italian success wording, still
    # a 200, not a redirect. No chart link -- the Client (and every chart it
    # had) no longer exists to link to.
    return _templates.TemplateResponse(
        request,
        "client_action_result.html",
        {
            "flash": {"kind": "success", "message": f"Cliente {client_id} eliminato."},
            "chart_href": None,
            "heading": "Clienti",
        },
        status_code=200,
    )


def _backup_is_stale(session: Session) -> bool:
    """Whether the newest ``Report`` anywhere in the system postdates the
    last recorded backup (Story 6.6) -- computed globally, not scoped to any
    one Client, since one un-backed-up Report anywhere is the durability gap
    this warns about.

    No ``Report`` at all -> never stale, even with no ``backup_record`` row
    yet: there is nothing new a backup could be missing. Otherwise, no
    ``backup_record`` row at all -> stale (the safe default for a freshly
    restored database, per this story's Boundaries).

    The logic itself now lives in
    ``shell/adapters/postgres/backup_record.py::backup_is_stale`` (Story
    9.2), read by both this page and the Home dashboard. This name is kept
    as a one-line delegate so ``tests/test_http_backup.py``'s existing
    import stays valid.
    """
    return backup_is_stale(session)


@router.get("/clients/{client_id}/reports", include_in_schema=False)
def list_client_reports(
    client_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """List every Gate-passed Report for ``client_id``, by month, most
    recent first (Story 6.4, FR-27) -- Francesco's way into a Client's
    history when a month is only known by having already been generated,
    not by an already-known ``run_id``. Two passed ``Report`` rows for the
    same month are broken by ``Report.created_at`` then ``Report.id``, both
    descending, so the listing order is deterministic.

    404s if ``client_id`` names no ``Client`` -- mirrors every other route
    in this module. A ``Client`` with no passed Report simply renders an
    empty list, not an error.

    Each row joins ``Report`` (a passed Gate outcome) to its ``ReportRun``
    for ``month`` -- a ``ReportRun`` that never reached ``gate_passed``
    never has a ``Report`` row and so never appears. For each, the
    ``StoredNatalChart`` ``run.natal_chart_id`` names (``None``-safe: unset
    for a run driven before this story, or one that never reached
    ``natal_ready``) decides whether the entry is marked as belonging to a
    since-superseded chart -- reopening it still works identically either
    way, straight into the existing, untouched ``/report-runs/{run_id}/report``
    route.

    Also passes ``backup_stale`` (Story 6.6) -- whether the newest ``Report``
    across every Client postdates the last recorded backup -- computed by
    :func:`_backup_is_stale`, chosen as this page's Design Notes explain
    Francesco returns here repeatedly during a batch and this app has no
    shared layout or home page today.
    """
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404)

    rows = session.exec(
        select(Report, ReportRun)
        .join(ReportRun, Report.report_run_id == ReportRun.id)
        .where(Report.client_id == client_id)
        .order_by(ReportRun.month.desc(), Report.created_at.desc(), Report.id.desc())
    ).all()

    chart_ids = {
        run.natal_chart_id for _stored_report, run in rows if run.natal_chart_id is not None
    }
    charts_by_id = {
        chart.id: chart
        for chart in session.exec(
            select(StoredNatalChart).where(StoredNatalChart.id.in_(chart_ids))
        ).all()
    }

    entries = []
    for _stored_report, run in rows:
        chart = charts_by_id.get(run.natal_chart_id) if run.natal_chart_id is not None else None
        superseded = chart is not None and chart.superseded_at is not None
        entries.append({"run_id": run.id, "month": run.month, "superseded": superseded})

    return _templates.TemplateResponse(
        request,
        "client_reports.html",
        {
            "client_id": client_id,
            "client": client,
            "active_tab": "report",
            "entries": entries,
            "backup_stale": _backup_is_stale(session),
        },
    )
