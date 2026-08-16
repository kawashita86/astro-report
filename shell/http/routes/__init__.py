"""HTTP route modules.

``healthz``/``login`` stay inline in ``shell/http/app.py``'s ``create_app()``;
``clients`` (Story 2.3) is the first module here, since a second real feature
route is exactly when that split earns its keep, not before.
"""

from __future__ import annotations
