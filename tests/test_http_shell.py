"""Story 9.1 — the application shell.

One ``base.html`` now carries the ``<html lang="it">`` document, the vendored
token stylesheet and the vendored HTMX, and a persistent Italian sidebar; every
operator template extends it (or ``_bare.html`` for an HTMX fragment). These
tests walk the story's I/O & Edge-Case Matrix: the shell is present and
singular on a migrated route, the fragment/full-page split holds for the run
poll, ``/login`` renders through the same base with its chrome suppressed, the
vendored assets load anonymously while the bare ``/static`` mount stays behind
auth, and ``tokens.css`` carries every DESIGN.md colour token.

Two guard helpers (``exactly_one_html`` / ``htmx_loaded_once_no_cdn``) back the
positive assertions; each ships a negative ``*_detects_*`` counterpart per the
repo convention that a syntactic guard proves it can fail.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from shell.adapters.postgres.style_guide import create_style_guide_version
from shell.config import Environment as AppEnvironment
from shell.config import Settings
from shell.http.app import create_app, get_session
from shell.http.auth import ALLOWLIST, ALLOWLIST_PREFIXES, SESSION_COOKIE_NAME, sign_session

AUTH_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
)
SESSION_SECRET_KEY = "test-session-secret-key-at-least-32-chars-long"

LOCAL = Settings(
    environment=AppEnvironment.LOCAL,
    database_url="postgresql://astro:astro@localhost:5432/astro_report",
    port=8000,
    auth_password_hash=AUTH_PASSWORD_HASH,
    session_secret_key=SESSION_SECRET_KEY,
    gemini_api_key="test-gemini-api-key",
    gemini_data_terms_verified_at="2026-01-15",
)

_SHELL_DIR = Path(__file__).resolve().parent.parent / "shell" / "http"
_TEMPLATES_DIR = _SHELL_DIR / "templates"
_STATIC_DIR = _SHELL_DIR / "static"
_DESIGN_MD = (
    Path(__file__).resolve().parent.parent
    / "_bmad-output"
    / "planning-artifacts"
    / "ux-designs"
    / "ux-astro-report-2026-08-28"
    / "DESIGN.md"
)

#: Migrated operator routes that render the shell with no domain seeding beyond
#: an empty database (``/style-guide*`` needs the version-1 row the fixture
#: seeds; the other operator routes need per-route fixtures and stay covered by
#: their own ``tests/test_http_*.py`` suites).
_MIGRATED_ROUTES = (
    "/clients",
    "/clients/new",
    "/corpus",
    "/corpus/new",
    "/style-guide",
    "/style-guide/edit",
)

_SIDEBAR_LABELS = (
    "Home",
    "Clienti",
    "Guida di stile",
    "Corpus",
    "Backup",
    "Tema chiaro / scuro",
    "Esci",
)


# --- Guard helpers (each with a negative counterpart below) -------------------


def exactly_one_html(markup: str) -> bool:
    """True when ``markup`` opens exactly one ``<html`` element."""
    return markup.lower().count("<html") == 1


#: Substrings that only ever appear in a real CDN <script>/<link> src — not in
#: ordinary page prose. A bare "cdn" is deliberately excluded (it misfires on
#: any content word containing it).
_CDN_MARKERS = ("unpkg.com", "cdnjs", "jsdelivr", "cdn.tailwind", "htmx.org")


def htmx_loaded_once_no_cdn(markup: str) -> bool:
    """True when the vendored HTMX is referenced exactly once and no CDN
    script/link marker survives."""
    lowered = markup.lower()
    referenced_once = lowered.count("/static/htmx.min.js") == 1
    no_cdn = not any(marker in lowered for marker in _CDN_MARKERS)
    return referenced_once and no_cdn


# --- Fixtures ---------------------------------------------------------------------


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def app_instance() -> FastAPI:
    return create_app(LOCAL)


@pytest.fixture
def client(app_instance: FastAPI, db_session: Session) -> TestClient:
    app_instance.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app_instance)


@pytest.fixture
def authenticated_client(client: TestClient, db_session: Session) -> TestClient:
    expires_at = int(time.time()) + 3600
    client.cookies.set(SESSION_COOKIE_NAME, sign_session(expires_at, LOCAL.session_secret_key))
    create_style_guide_version(db_session, "Version 1 content.")
    db_session.commit()
    return client


# --- The shell is present and singular on every migrated route -------------------


@pytest.mark.parametrize("route", _MIGRATED_ROUTES)
def test_a_migrated_route_renders_exactly_one_it_shell_with_landmarks(
    authenticated_client: TestClient, route: str
) -> None:
    """I/O Matrix — "Authenticated GET of a migrated operator route": 200, one
    ``<html>``, ``lang="it"``, the skip link before ``<nav>``, ``<nav>`` and
    ``<main>`` landmarks, and the five Italian nav areas + theme toggle + Esci."""
    response = authenticated_client.get(route)

    assert response.status_code == 200
    body = response.text
    assert exactly_one_html(body)
    assert '<html lang="it">' in body

    skip_at = body.find('class="skip-link"')
    nav_at = body.find("<nav")
    main_at = body.find("<main")
    assert skip_at != -1, "no skip-to-content link"
    assert nav_at != -1 and main_at != -1, "missing nav/main landmarks"
    assert skip_at < nav_at, "skip link must precede the sidebar nav"
    assert 'href="#main-content"' in body
    assert 'id="main-content"' in body

    for label in _SIDEBAR_LABELS:
        assert label in body, f"sidebar label missing: {label!r}"


@pytest.mark.parametrize("route", _MIGRATED_ROUTES)
def test_a_migrated_route_links_tokens_css_and_vendored_htmx_once(
    authenticated_client: TestClient, route: str
) -> None:
    """AC — ``/static/tokens.css`` linked once, ``/static/htmx.min.js`` the only
    htmx ``<script>``, no template references a CDN."""
    body = authenticated_client.get(route).text

    assert body.count('href="/static/tokens.css"') == 1
    assert htmx_loaded_once_no_cdn(body)


def test_the_active_sidebar_item_is_marked_from_the_request_path(
    authenticated_client: TestClient,
) -> None:
    """AC — the sidebar carries an active-item marker matching the path."""
    body = authenticated_client.get("/corpus").text

    marked = re.search(r'href="/corpus"[^>]*\bclass="is-active"[^>]*aria-current="page"', body)
    assert marked is not None, "the Corpus nav item is not marked active on /corpus"
    # Another area is not simultaneously active.
    assert not re.search(r'href="/style-guide"[^>]*\bclass="is-active"', body)


# --- report_run_poll: the fragment / full-page split ----------------------------


def _render_poll(*, hx_request: bool) -> str:
    from shell.http.stage_view import build_stage_track, stage_caption

    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

    headers = {"hx-request": "true"} if hx_request else {}
    fake_request = type(
        "_Request",
        (),
        {"headers": headers, "url": type("_Url", (), {"path": "/report-runs/abc"})()},
    )()
    fake_run = type(
        "_Run",
        (),
        {
            "id": "abc",
            "month": "2026-01",
            "stage": "transits_ready",
            "failed_at": None,
            "regeneration_count": 0,
            "failure_reason": None,
        },
    )()
    stage_track = build_stage_track(fake_run.stage, failed=False, gate_failed=False)
    caption = stage_caption(fake_run.stage, failed=False, gate_failed=False, failure_reason=None)
    return env.get_template("report_run_poll.html").render(
        request=fake_request,
        run=fake_run,
        stage_track=stage_track,
        stage_caption=caption,
        gate_failed=False,
        poll_active=True,
    )


def test_an_htmx_poll_renders_only_the_fragment_no_document_skeleton() -> None:
    """I/O Matrix — "HTMX poll of a running run": fragment only, no ``<html>``,
    no ``<head>``, no htmx ``<script>``; still carries the stage track."""
    fragment = _render_poll(hx_request=True)

    assert "<html" not in fragment.lower()
    assert "<head" not in fragment.lower()
    assert "htmx.min.js" not in fragment
    assert "Assemblaggio del Payload" in fragment  # transits_ready's own caption
    assert "stage-track" in fragment
    assert 'id="run-status"' in fragment


def test_a_full_page_poll_renders_through_base_html() -> None:
    """I/O Matrix — "Full-page load of the run stage view": the full shell via
    ``base.html``, exactly one ``<html>``."""
    full_page = _render_poll(hx_request=False)

    assert exactly_one_html(full_page)
    assert '<html lang="it">' in full_page
    assert "/static/htmx.min.js" in full_page
    assert "Assemblaggio del Payload" in full_page  # transits_ready's own caption


# --- report_run_poll: the backoff/Riprova wiring (Story 9.8) -------------------


def test_the_poll_region_carries_the_extended_trigger_and_the_riprova_button() -> None:
    """Code Map — ``report_run_poll.html`` gains ``poll-retry from:body`` on
    the existing ``hx-trigger`` (the ``every 2s`` cadence itself is untouched)
    and a hidden ``[data-poll-retry]`` button beside ``[data-poll-error]``."""
    fragment = _render_poll(hx_request=True)

    assert 'hx-trigger="every 2s, poll-retry from:body"' in fragment
    assert "data-poll-retry" in fragment
    retry_at = fragment.index("data-poll-retry")
    assert "hidden" in fragment[retry_at : retry_at + 80]
    assert "Riprova" in fragment


# --- tokens.css / shell.js: the toast/skeleton/spinner primitives (Story 9.8) --


def test_tokens_css_defines_the_toast_skeleton_and_spinner_primitives() -> None:
    """Code Map — the ``PROVISIONAL — Story 9.8`` block defines
    ``.toast-region``/``.toast``, ``.skeleton``, ``.spinner``,
    ``.banner__dismiss`` and a ``.banner--success`` variant."""
    css = (_STATIC_DIR / "tokens.css").read_text(encoding="utf-8")

    for selector in (
        ".toast-region",
        ".toast {",
        ".toast--success",
        ".toast--warning",
        ".toast--danger",
        ".toast__close",
        ".skeleton {",
        ".spinner {",
        ".banner__dismiss",
        ".banner--success",
    ):
        assert selector in css, f"tokens.css is missing {selector!r}"


def test_reduced_motion_also_kills_the_toast_skeleton_and_spinner_animations() -> None:
    """Boundaries — the existing ``prefers-reduced-motion`` block
    (tokens.css:491-504 before this story) is extended to disable the new
    toast slide-in, skeleton shimmer, and spinner spin animations."""
    css = (_STATIC_DIR / "tokens.css").read_text(encoding="utf-8")

    rm_block = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    rm_block = rm_block.split("\n}\n", 1)[0]
    assert ".toast {" in rm_block
    assert ".skeleton::after {" in rm_block
    assert ".spinner {" in rm_block
    assert rm_block.count("animation: none;") >= 4  # stage-track dot + the 3 new ones


def test_shell_js_wires_the_poll_backoff_and_manual_retry() -> None:
    """AC — the backoff gate (5s/15s) and the manual ``Riprova`` retry are
    wired client-side only: a veto on ``htmx:beforeRequest`` for the
    already-present ``every 2s`` trigger, never a change to that trigger's
    own cadence or to any server route."""
    js = (_STATIC_DIR / "shell.js").read_text(encoding="utf-8")

    assert "5000" in js
    assert "15000" in js
    assert "poll-retry" in js
    assert "pollBackoff" in js
    assert "[data-poll-retry]" in js
    assert 'new CustomEvent("poll-retry")' in js
    assert "htmx:beforeRequest" in js


def test_shell_js_wires_the_toast_queue_and_flash_promotion() -> None:
    """AC — the toast queue (FIFO cap 3, success auto-dismiss ~5s with
    hover-pause, warning/danger persist with a close control) and the
    ``[data-flash]`` -> toast promotion on load."""
    js = (_STATIC_DIR / "shell.js").read_text(encoding="utf-8")

    assert "function showToast(" in js
    assert "TOAST_MAX = 3" in js
    assert "mouseenter" in js and "mouseleave" in js
    assert "[data-flash]" in js
    assert "data-toast-region" in js
    assert ".banner__dismiss" in js


def test_shell_js_wires_the_submit_lock_without_the_native_disabled_attribute() -> None:
    """Boundaries — form-lock never sets the native ``disabled`` attribute on
    a field (it would drop that field's value from the submission); only the
    submit ``<button>`` is actually disabled, fields are locked via
    ``aria-disabled`` + CSS ``pointer-events``."""
    js = (_STATIC_DIR / "shell.js").read_text(encoding="utf-8")

    assert "[data-submit-lock]" in js
    assert "submitButton.disabled = true" in js
    assert 'field.setAttribute("aria-disabled", "true")' in js
    assert "field.disabled" not in js


# --- login renders through base.html, chrome suppressed -------------------------


def test_login_renders_through_base_html_with_no_sidebar_nav(client: TestClient) -> None:
    """I/O Matrix — "Login page render": 200, extends ``base.html``, one
    ``<html>``, ``tokens.css`` linked, sidebar/nav chrome suppressed."""
    response = client.get("/login")

    assert response.status_code == 200
    body = response.text
    assert exactly_one_html(body)
    assert '<html lang="it">' in body
    assert 'href="/static/tokens.css"' in body
    assert "<nav" not in body.lower()
    assert 'href="/clients"' not in body
    assert "Guida di stile" not in body


# --- Static assets vs. the auth middleware -------------------------------------


@pytest.mark.parametrize(
    ("asset", "type_prefix"),
    (
        ("/static/tokens.css", "text/css"),
        ("/static/htmx.min.js", ("text/javascript", "application/javascript")),
    ),
)
def test_a_static_asset_is_served_anonymously(
    client: TestClient, asset: str, type_prefix: str | tuple[str, ...]
) -> None:
    """I/O Matrix — "Anonymous GET of a static asset": 200 with the file bytes
    and the right MIME type, auth bypassed via the ``/static/`` prefix."""
    response = client.get(asset)

    assert response.status_code == 200
    assert response.content == (_STATIC_DIR / asset.removeprefix("/static/")).read_bytes()
    assert response.headers["content-type"].split(";")[0].strip().startswith(type_prefix)


def test_an_unknown_static_path_is_404_not_401(client: TestClient) -> None:
    """I/O Matrix — "unknown ``/static/nope.css`` → 404, not 401"."""
    assert client.get("/static/nope.css").status_code == 404


@pytest.mark.parametrize(
    "attack",
    (
        "/static/../shell/http/app.py",
        "/static/..%2f..%2fapp.py",
        "/static/%2e%2e/%2e%2e/shell/http/app.py",
    ),
)
def test_a_path_traversal_under_the_static_prefix_cannot_escape_the_dir(
    authenticated_client: TestClient, attack: str
) -> None:
    """The ``/static/`` auth bypass must not become a source-code read: a
    traversal attempt resolves outside the mount and is rejected (never 200)
    and never leaks Python source — whether httpx normalises the dot-segments
    away (→ an unrouted 404) or they reach StaticFiles' own guard (→ 404).
    Uses an authenticated client so a normalised path is judged by routing,
    not the anonymous 401. Pins the mount/prefix against regression."""
    response = authenticated_client.get(attack)

    assert response.status_code != 200
    assert response.status_code in {400, 401, 404}
    assert "create_app" not in response.text
    assert "def create_app" not in response.text


@pytest.mark.parametrize("path", ("/static", "/nope"))
def test_the_bare_mount_and_unknown_paths_stay_401_empty_anonymously(
    client: TestClient, path: str
) -> None:
    """I/O Matrix — "Anonymous GET of the bare mount path / a non-static unknown
    path": 401, empty body (the prefix match needs ``/static/`` + a segment)."""
    response = client.get(path)

    assert response.status_code == 401
    assert response.content == b""


def test_the_allowlist_is_unchanged_and_the_prefix_is_declared_separately() -> None:
    """AC — ``ALLOWLIST`` is still exactly ``{"/healthz", "/login"}``; the
    static bypass is a separately-declared prefix tuple."""
    assert frozenset({"/healthz", "/login"}) == ALLOWLIST
    assert ALLOWLIST_PREFIXES == ("/static/",)


def test_slash_serves_the_dashboard_for_an_authenticated_caller(
    authenticated_client: TestClient,
) -> None:
    """AC — Story 9.2 registers ``GET /``: past the auth checkpoint it is a
    200 dashboard rendering through ``base.html`` (one ``<html``), with the
    single ``<h1>Home</h1>``."""
    response = authenticated_client.get("/")

    assert response.status_code == 200
    assert exactly_one_html(response.text)
    assert "<h1>Home</h1>" in response.text


def test_slash_is_401_empty_body_for_an_anonymous_caller(client: TestClient) -> None:
    """AC — ``/`` anonymous is the same empty-body 401 as any non-allowlisted
    path; the shell adds no new anonymous surface beyond ``/static/``."""
    anon = client.get("/")
    assert anon.status_code == 401
    assert anon.content == b""


# --- tokens.css carries every DESIGN.md colour token --------------------------


def _design_colour_keys() -> list[str]:
    text = _DESIGN_MD.read_text(encoding="utf-8")
    block = re.search(r"\ncolors:\n(.*?)\ntypography:\n", text, re.DOTALL)
    assert block is not None, "DESIGN.md frontmatter has no colors: block"
    keys: list[str] = []
    for line in block.group(1).splitlines():
        match = re.match(r"  ([A-Za-z0-9-]+):\s*'#", line)
        if match:
            keys.append(match.group(1))
    assert keys, "no colour keys parsed from DESIGN.md"
    return keys


def test_tokens_css_defines_a_custom_property_for_every_design_colour_key() -> None:
    """AC — ``tokens.css`` defines a CSS custom property for every token in
    DESIGN.md's ``colors:`` map, light values and their ``-dark`` counterparts."""
    css = (_STATIC_DIR / "tokens.css").read_text(encoding="utf-8")

    missing = [key for key in _design_colour_keys() if f"--{key}:" not in css]
    assert not missing, f"tokens.css is missing custom properties: {missing}"


def test_tokens_css_swaps_dark_values_under_media_and_data_theme() -> None:
    """Design Notes — dark values are re-bound under both
    ``@media (prefers-color-scheme: dark)`` and ``:root[data-theme="dark"]``,
    and no token is defined only inside a media/attribute block."""
    css = (_STATIC_DIR / "tokens.css").read_text(encoding="utf-8")

    assert "@media (prefers-color-scheme: dark)" in css
    assert ':root[data-theme="dark"]' in css
    assert ':root:not([data-theme="light"])' in css

    # Every token must have a definition on a bare ``:root {`` block, never
    # only inside a media/attribute block. Check a representative sample by
    # scanning only the bare-:root rule bodies.
    bare_root_bodies = "".join(re.findall(r"(?<!\S):root\s*\{([^}]*)\}", css))
    for token in ("--surface-base", "--ink-primary", "--primary-700", "--focus-ring", "--danger"):
        assert f"{token}:" in bare_root_bodies, f"{token} is not defined on a bare :root"


# --- The <900px drawer and the reduced-motion kill switch (static level) --------


def test_the_sub_900px_drawer_is_wired_in_both_css_and_script() -> None:
    """I/O Matrix — "Viewport < 900px": the sidebar leaves the flow below 900px
    and the header control opens a focus-trapped drawer that closes on Esc and
    restores focus to the trigger. The behaviour itself needs a browser; this
    pins the wiring that makes it possible."""
    css = (_STATIC_DIR / "tokens.css").read_text(encoding="utf-8")
    js = (_STATIC_DIR / "shell.js").read_text(encoding="utf-8")

    assert "@media (max-width: 899px)" in css
    assert "is-drawer-open" in css

    assert "[data-nav-toggle]" in js
    assert '"Escape"' in js
    assert "menuButton.focus()" in js, "drawer close must restore focus to the trigger"
    assert 'setAttribute("aria-expanded"' in js


def test_reduced_motion_disables_the_shell_transitions() -> None:
    """I/O Matrix — "``prefers-reduced-motion`` set": the drawer slide (and any
    theme transition) is disabled. The drawer rule declares a transition that
    the reduced-motion block overrides to ``none``."""
    css = (_STATIC_DIR / "tokens.css").read_text(encoding="utf-8")

    assert "@media (prefers-reduced-motion: reduce)" in css
    rm_block = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "transition: none" in rm_block


# --- The vendored HTMX is the pinned build ---------------------------------------


def test_the_vendored_htmx_is_the_pinned_2_0_4_build() -> None:
    """Boundaries — the vendored ``static/htmx.min.js`` is the 2.0.4 build that
    matches the removed ``htmx.org@2.0.4`` CDN pin."""
    js = (_STATIC_DIR / "htmx.min.js").read_text(encoding="utf-8")

    assert 'version:"2.0.4"' in js


# --- report_export.html is untouched ----------------------------------------------


def test_report_export_html_keeps_its_own_document_and_does_not_extend_base() -> None:
    """Boundaries — ``report_export.html`` (the WeasyPrint client document)
    keeps its standalone ``<html>``, Georgia serif, and never ``{% extends %}``."""
    source = (_TEMPLATES_DIR / "report_export.html").read_text(encoding="utf-8")

    assert "{% extends" not in source
    assert "<html" in source
    assert "Georgia" in source
    assert 'href="/static/tokens.css"' not in source


def test_no_template_but_base_and_report_export_carries_its_own_html_skeleton() -> None:
    """Verification — ``grep '<html' templates/`` matches only ``base.html`` and
    ``report_export.html``; nothing references ``unpkg`` / a CDN htmx."""
    offenders_html: list[str] = []
    offenders_cdn: list[str] = []
    for template in _TEMPLATES_DIR.glob("*.html"):
        text = template.read_text(encoding="utf-8")
        if "<html" in text.lower() and template.name not in {"base.html", "report_export.html"}:
            offenders_html.append(template.name)
        if "unpkg" in text.lower() or "htmx.org" in text.lower():
            offenders_cdn.append(template.name)
    assert not offenders_html, f"templates still shipping their own <html>: {offenders_html}"
    assert not offenders_cdn, f"templates still referencing a CDN: {offenders_cdn}"


# --- Negative counterparts for the two guards --------------------------------------


def test_the_one_html_guard_detects_a_second_html_element() -> None:
    """``exactly_one_html`` must fail markup that opens ``<html`` twice — the
    whole point of the guard on the migrated routes."""
    one = '<!doctype html><html lang="it"><body></body></html>'
    two = '<html lang="it"></html><html lang="en"></html>'
    assert exactly_one_html(one) is True
    assert exactly_one_html(two) is False, "a second <html> slipped past the guard"


def test_the_htmx_once_guard_detects_a_duplicate_or_cdn_script() -> None:
    """``htmx_loaded_once_no_cdn`` must fail both a duplicated vendored script
    and a surviving CDN ``<script>``."""
    ok = '<script src="/static/htmx.min.js" defer></script>'
    assert htmx_loaded_once_no_cdn(ok) is True

    duplicated = ok + ok
    assert htmx_loaded_once_no_cdn(duplicated) is False, "duplicate htmx <script> not caught"

    cdn = ok + '<script src="https://unpkg.com/htmx.org@2.0.4"></script>'
    assert htmx_loaded_once_no_cdn(cdn) is False, "CDN htmx <script> not caught"

    jsdelivr = ok + '<script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.4"></script>'
    assert htmx_loaded_once_no_cdn(jsdelivr) is False, "jsdelivr CDN <script> not caught"

    # A page whose prose merely contains the letters "cdn" must NOT trip it.
    assert htmx_loaded_once_no_cdn(ok + "<p>vedi il cdn interno</p>") is True
