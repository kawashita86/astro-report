"""``GET /api/v1/vocabulary/it``: the Italian words the plugin must use.

Ids elsewhere in the API are the glossary's English ids; this endpoint is the
only place their Italian names come from, together with the Gate words, so the
plugin's drafted text and this application's Groundedness Gate agree. It reads
the vocabulary loaded at startup, stores nothing and is byte-stable.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response

from core.payload.freeze import canonical_json_bytes
from core.types.gate import GateVocabulary
from shell.http.api.router import router
from shell.vocabulary import vocabulary_body

__all__ = ["italian_vocabulary"]


@router.get("/vocabulary/it")
def italian_vocabulary(request: Request) -> Response:
    gate: GateVocabulary = request.app.state.gate_vocabulary
    return Response(canonical_json_bytes(vocabulary_body(gate)), media_type="application/json")
