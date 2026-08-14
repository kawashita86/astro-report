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

# Dependencies first, from the committed lockfile only: --locked fails rather
# than resolving new versions, so the image matches the checkout exactly.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini docker-entrypoint.sh ./
COPY core/ ./core/
COPY shell/ ./shell/
COPY migrations/ ./migrations/

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
