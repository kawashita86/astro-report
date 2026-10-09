"""The outermost layer of every ``/api/`` call: one log line, and no leaked failure.

An API call carries birth dates, times and coordinates; the product promise is
that none of it is stored or logged (AD-22). Writing the single log line from a
middleware that never touches the request body makes that a property of one
function instead of every handler's discipline, and a test proves it.

The same layer turns an unhandled exception into the ``internal_error``
envelope. An exception handler alone is not enough: under ``debug=True`` (the
local environment) Starlette bypasses it for a plaintext traceback, which an API
client must never receive.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from shell.http.api.errors import handle_api_exception
from shell.http.api.router import API_PATH_PREFIX

__all__ = ["ApiBoundaryMiddleware"]

_logger = logging.getLogger("shell.http.api.access")


class ApiBoundaryMiddleware(BaseHTTPMiddleware):
    """Log endpoint, status, duration and the ComputationConfig version; answer
    an unhandled exception with the ``internal_error`` envelope."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(API_PATH_PREFIX):
            return await call_next(request)
        started = time.perf_counter()
        status_code = 500
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Type only, never the message: an exception message can carry
                # the request's own values.
                _logger.error("api unhandled %s", type(exc).__name__)
                response = handle_api_exception(request, exc)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000)
            _logger.info(
                "api %s %s -> %d in %d ms (computation v%d)",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                request.app.state.computation_config.version,
            )
