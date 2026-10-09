"""The ``/api/v1`` router: the single mount point for every chart data endpoint.

Kept empty in the skeleton on purpose -- shipping a placeholder endpoint would
publish a contract nobody asked for. Later stories attach their routes here, and
tests exercise the authenticated path with a probe router of their own.
"""

from __future__ import annotations

from fastapi import APIRouter

__all__ = ["API_PREFIX", "API_PATH_PREFIX", "router"]

#: The versioned mount point. A breaking change is ``/api/v2``, never an edit here.
API_PREFIX = "/api/v1"

#: Every path the API middleware, handlers and log line treat as the API
#: surface, whichever version it carries.
API_PATH_PREFIX = "/api/"

router = APIRouter(prefix=API_PREFIX, include_in_schema=False)
