"""The API's JSON error envelope and the one place typed core errors become codes.

Every failure under ``/api/`` has the same shape -- ``{code, message, field}`` --
with an operator-readable Italian message, so the plugin branches on ``code`` and
shows ``message`` without parsing prose. Core raises typed domain errors and
never an HTTP status (AD-1); the mapping to status and code is kept here so no
handler invents its own.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.errors import LocalTimeError, PlaceResolutionError
from core.payload.freeze import canonical_json_bytes
from shell.http.api.router import API_PATH_PREFIX

__all__ = [
    "ApiError",
    "ErrorCode",
    "error_response",
    "handle_api_exception",
    "handle_http_exception",
    "handle_validation_error",
    "map_exception",
]


class ErrorCode(StrEnum):
    """The closed set of error codes (AD-22)."""

    INVALID_REQUEST = "invalid_request"
    BIRTH_TIME_REQUIRED = "birth_time_required"
    PLACE_UNRESOLVED = "place_unresolved"
    WINDOW_TOO_LONG = "window_too_long"
    EPHEMERIS_OUT_OF_RANGE = "ephemeris_out_of_range"
    UNAUTHORIZED = "unauthorized"
    INTERNAL_ERROR = "internal_error"


#: Status and Italian message per code. ``field`` varies per occurrence.
_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_REQUEST: 422,
    ErrorCode.BIRTH_TIME_REQUIRED: 422,
    ErrorCode.PLACE_UNRESOLVED: 422,
    ErrorCode.WINDOW_TOO_LONG: 422,
    ErrorCode.EPHEMERIS_OUT_OF_RANGE: 422,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.INTERNAL_ERROR: 500,
}

_MESSAGE: dict[ErrorCode, str] = {
    ErrorCode.INVALID_REQUEST: "Richiesta non valida.",
    ErrorCode.BIRTH_TIME_REQUIRED: "L'ora di nascita è necessaria per questo calcolo.",
    ErrorCode.PLACE_UNRESOLVED: "Non è stato possibile risolvere il luogo indicato.",
    ErrorCode.WINDOW_TOO_LONG: "La finestra richiesta supera la durata massima consentita.",
    ErrorCode.EPHEMERIS_OUT_OF_RANGE: "La data richiesta è fuori dall'intervallo delle effemeridi.",
    ErrorCode.UNAUTHORIZED: "Autenticazione richiesta: token mancante o non valido.",
    ErrorCode.INTERNAL_ERROR: "Errore interno durante il calcolo.",
}


class ApiError(Exception):
    """A deliberate API failure: the code, and the JSON path it concerns."""

    def __init__(self, code: ErrorCode, field: str | None = None) -> None:
        self.code = code
        self.field = field
        super().__init__(code.value)


def error_response(
    code: ErrorCode, field: str | None = None, *, status_code: int | None = None
) -> Response:
    """The envelope as a canonical-JSON response."""
    body = canonical_json_bytes({"code": code.value, "message": _MESSAGE[code], "field": field})
    # RFC 6750: a 401 must say which scheme would have worked.
    headers = {"WWW-Authenticate": "Bearer"} if code is ErrorCode.UNAUTHORIZED else None
    return Response(
        body,
        status_code=status_code if status_code is not None else _STATUS[code],
        media_type="application/json",
        headers=headers,
    )


def map_exception(exc: BaseException) -> tuple[ErrorCode, str | None]:
    """The single mapping from an exception to ``(code, field)``."""
    if isinstance(exc, ApiError):
        return exc.code, exc.field
    if isinstance(exc, LocalTimeError):
        # A DST gap or fold is the caller's input, never silently guessed.
        return ErrorCode.INVALID_REQUEST, "subject.birth_time"
    if isinstance(exc, PlaceResolutionError):
        return ErrorCode.PLACE_UNRESOLVED, None
    return ErrorCode.INTERNAL_ERROR, None


def handle_api_exception(request: Request, exc: Exception) -> Response:
    """Any exception that escaped a handler, as its envelope. Called only by
    :class:`~shell.http.api.boundary.ApiBoundaryMiddleware`, i.e. on ``/api/``."""
    code, field = map_exception(exc)
    return error_response(code, field)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
    """Body or query validation: ``invalid_request`` on ``/api/``, FastAPI's own 422 elsewhere."""
    if not request.url.path.startswith(API_PATH_PREFIX):
        return await request_validation_exception_handler(request, exc)
    errors = exc.errors()
    location = errors[0].get("loc", ()) if errors else ()
    # Drop the leading "body"/"query" marker so the field is a JSON path into the request.
    path = [str(part) for part in location[1:]]
    return error_response(ErrorCode.INVALID_REQUEST, ".".join(path) or None)


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
    """404/405 and friends: an ``invalid_request`` envelope on ``/api/``, the default elsewhere."""
    if not request.url.path.startswith(API_PATH_PREFIX):
        return await http_exception_handler(request, exc)
    return error_response(ErrorCode.INVALID_REQUEST, None, status_code=exc.status_code)
