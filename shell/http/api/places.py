"""``POST /api/v1/places/resolve``: turn place text into candidates with zones.

The plugin shows the candidates to its operator, who confirms one; the chosen
candidate is then sent back as a subject's ``place``. Every match is listed with
its IANA zone, the place cache is consulted first, and no match at all is
``place_unresolved``. The only write is ``PLACE_CACHE`` (an unambiguous match,
as in the operator UI); the query text is never logged.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from sqlmodel import Session

from core.payload.freeze import canonical_json_bytes
from core.types.place import ZonedPlaceCandidate
from shell.adapters.nominatim.geocoder import NominatimGeocoder
from shell.http.api.router import router
from shell.http.api.subject import quantize_coordinate

__all__ = ["ResolveRequest", "get_api_session", "get_place_geocoder", "resolve_place"]

_MAX_QUERY_LENGTH = 200


class ResolveRequest(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def _query_must_be_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped or len(stripped) > _MAX_QUERY_LENGTH:
            raise ValueError("expected 1-200 characters")
        return stripped


def get_api_session(request: Request) -> Iterator[Session]:
    """The request-scoped session, from the app's own ``get_session``.

    Imported at call time because ``shell.http.app`` imports this package while
    it is itself still loading; tests override this dependency.
    """
    from shell.http.app import get_session

    yield from get_session(request)


def get_place_geocoder(session: Session = Depends(get_api_session)) -> NominatimGeocoder:
    """The geocoder this endpoint resolves through, a dependency so tests can
    substitute a fake. It shares the request's session with the handler, so a
    cache write and the commit below are one transaction."""
    return NominatimGeocoder(session)


def _candidate_json(candidate: ZonedPlaceCandidate) -> dict[str, str]:
    return {
        "display_name": candidate.display_name,
        "iana_zone": candidate.iana_zone,
        "latitude": quantize_coordinate(candidate.latitude),
        "longitude": quantize_coordinate(candidate.longitude),
    }


@router.post("/places/resolve")
def resolve_place(
    body: ResolveRequest,
    session: Session = Depends(get_api_session),
    geocoder: NominatimGeocoder = Depends(get_place_geocoder),
) -> Response:
    candidates = geocoder.list_candidates(body.query)
    # `store_resolved_place` only flushes; this endpoint owns the transaction.
    session.commit()
    return Response(
        canonical_json_bytes({"candidates": [_candidate_json(item) for item in candidates]}),
        media_type="application/json",
    )
