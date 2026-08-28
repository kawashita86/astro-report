# A single-process image: one uvicorn worker serving FastAPI.
#
# Migrations run in the entrypoint, before the server is exec'd, so the process
# that accepts traffic is the same process the platform health-checks, and a
# failed migration exits non-zero before anything is served. See docker-entrypoint.sh.

FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir uv==0.10.0

# One apt transaction, two rationales, one list purge.
#
# build-essential (gcc/g++/make) -- deliberately not pkg-config or
# libsqlite3-dev. Without a compiler, pyswisseph's setup.py fails cleanly on a
# missing gcc; with only build-essential, it falls back deterministically to
# its own bundled libswe+sqlite3 sources. Adding pkg-config would make the
# build depend on whatever system libraries happen to be present -- strictly
# worse than the deterministic bundled path.
#
# libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation --
# WeasyPrint 69 dlopen's the Pango / GLib / HarfBuzz stack at *import* time, and
# shell/http/routes/report_runs.py imports html_to_pdf at module top level, so a
# missing native lib kills create_app() (uvicorn never serves), not just the PDF
# route. This is WeasyPrint's own Debian >=11 runtime list: libgobject-2.0-0
# (the symbol in the crash) comes in via libglib2.0-0 pulled by libpango-1.0-0;
# fontconfig + FreeType via libpangoft2-1.0-0; libharfbuzz-subset0 is a separate
# package doing PDF font subsetting. No cairo / gdk-pixbuf -- WeasyPrint >=53
# dropped the cairo backend and raster images go through Pillow's bundled libs.
# fonts-liberation because shell/http/templates/report_export.html asks for
# `Georgia, "Times New Roman", serif` and slim ships no fonts; Liberation Serif
# is metric-compatible with Times New Roman.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, from the committed lockfile only: --locked fails rather
# than resolving new versions, so the image matches the checkout exactly.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini docker-entrypoint.sh ./
COPY core/ ./core/
COPY shell/ ./shell/
COPY migrations/ ./migrations/
COPY data/ ./data/

RUN chmod +x /app/docker-entrypoint.sh \
    && useradd --create-home --uid 10001 astro \
    && chown -R astro:astro /app
USER astro

# PORT is deliberately NOT defaulted here. Nothing this application reads has a
# default: a missing variable aborts startup with a message naming it, and an
# image that quietly picked 8000 would make that contract false inside the
# container. Render injects PORT; compose.yaml sets it explicitly.
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# `exec` inside sh -c replaces the shell, so the container's only process is uvicorn.
CMD ["sh", "-c", "exec uvicorn shell.http.app:app --host 0.0.0.0 --port ${PORT} --workers 1"]
