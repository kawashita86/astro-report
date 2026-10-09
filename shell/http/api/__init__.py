"""The chart data API surface (AD-22): a stateless, versioned JSON interface for
one machine client, the alerenzi consultation plugin.

It exists as its own package so everything that makes the surface different from
the operator UI -- bearer authentication, the JSON error envelope, the absence
of any stored subject data -- lives in one place that ``shell/http/routes`` never
has to know about. Endpoints are added by later stories on top of this skeleton.
"""

from __future__ import annotations

from shell.http.api.router import API_PREFIX, router

__all__ = ["API_PREFIX", "router"]
