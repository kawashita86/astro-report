# astro-report

Natal charts, monthly transits and grounded eight-section Italian reports, for a
single operator.

This repository currently holds the deployable skeleton: dependency management,
the container, the configuration reader, the migration chain and the liveness
route. The astronomy arrives with later stories.

## Layout

```text
core/         PURE. no I/O, no clock, no network, no randomness
shell/        IMPERATIVE. everything that touches the world
  config.py   the only reader of the environment
  http/       FastAPI routes, Jinja2 templates, HTMX
migrations/   Alembic, forward-only
tests/
```

`shell/` imports `core/`. `core/` never imports `shell/`.

## Requirements

- Python 3.13 (`uv` installs it; the version is pinned in `.python-version`)
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose, for the container and the local database

## Configuration

Every environment variable is read in exactly one place, `shell/config.py`, and
validated into a frozen settings object at startup. No other module reads
`os.environ` — `tests/test_env_access_is_centralized.py` fails if one starts to.

All but the optional ones below are required; none has a default.

| Variable | Required | Accepted values |
| --- | --- | --- |
| `ENVIRONMENT` | yes | `local`, `production` — there is no staging |
| `DATABASE_URL` | yes | a Postgres URL (`postgres`, `postgresql` or `postgresql+psycopg` scheme) with a host |
| `PORT` | yes | 1–65535; hosting platforms supply this themselves |
| `AUTH_PASSWORD_HASH` | yes | Argon2 hash of the single sign-in password — never the plaintext |
| `SESSION_SECRET_KEY` | yes | random string, at least 32 characters; signs the session cookie |
| `GEMINI_API_KEY` | yes | Gemini API key for the Generator adapter; never sent under `ENVIRONMENT=local` |
| `GEMINI_MODEL` | no | Gemini model the Generator calls; default `gemini-2.5-flash` |
| `GENERATION_CONCURRENCY` | no | Section generations in flight at once, integer 1–32; default `11` |
| `API_TOKEN_HASH` | no | Argon2 hash of the bearer token the chart data API (`/api/v1`) accepts; unset ⇒ every `/api/` request answers `401`; present but malformed aborts startup |
| `GEMINI_DATA_TERMS_VERIFIED_AT` | yes | ISO date (`YYYY-MM-DD`), not in the future — when the Gemini data terms were verified (NFR-17) |

Nothing is defaulted. A missing or invalid variable aborts startup with a
non-zero exit and a message naming the offender and why it was rejected; the
application never serves in a degraded configuration.

Astronomical tuning values — orbs, house system, body sets, ruler tables — are
**not** environment variables. They live in `data/computation.toml` and are
passed explicitly as a `ComputationConfig`. Keep the two homes separate.

Nothing loads a `.env` file implicitly — `shell/config.py` reads only the process
environment, and a dotenv dependency would be a second reader. Copy
`.env.example` to `.env` and pass it explicitly with `uv run --env-file .env …`
for the non-Docker path; `compose.yaml` supplies its own values inline and
ignores `.env` entirely. `.env` is never committed.

## Running locally

The whole stack, in the production image, against a local Postgres:

```bash
docker compose up -d --build
curl -fsS localhost:8000/healthz    # 204 No Content
docker compose logs -f app
docker compose down                 # add -v to discard the database
```

Without Docker (needs a Postgres you supply through `DATABASE_URL`):

```bash
uv sync --locked
uv run --env-file .env alembic upgrade head
uv run --env-file .env uvicorn shell.http.app:app --host 0.0.0.0 --port 8000
```

## Checks

```bash
uv sync --locked      # no lockfile drift
uv run pytest
uv run ruff check .
docker build -t astro-report .
```

## Migrations

Alembic, **forward-only**. Every `downgrade()` raises, including in the template
new revisions are generated from — a mistake is corrected with a new forward
migration, never by reversing one. Migrations are applied at deploy before the
application accepts traffic.

```bash
uv run alembic revision -m "what this migration does"
uv run alembic upgrade head
```

## Deployment

Two environments only: local (above) and production. There is no staging.

Production is one Docker container on Coolify, on a Netcup VPS in Vienna, AT,
backed by a Postgres 18 on the same VPS. Hosting and storage location:
**Vienna, AT** (EU). All durable state is in Postgres; the container
filesystem is ephemeral and nothing written at runtime is read back after a
restart. Coolify takes scheduled backups of the production Postgres and
stores them off the VPS in a Backblaze B2 bucket in EU Central (Amsterdam); the operator export from
`GET /backup` (AD-17) is a second, operator-held copy.

Gemini's EEA data terms are re-verified in
`docs/release-validation/gemini-data-terms.md` (NFR-17); when the provider,
model, terms or hosting location change, follow that file's *Next
re-verification trigger* section.

Deploys are driven from CI only. The `deploy` job in
`.github/workflows/ci.yml` runs on pushes to `main` after the `test` job
passes and POSTs to the Coolify deploy webhook; Coolify's own auto-deploy is
off, so a red build never reaches production. `docker-entrypoint.sh` applies
migrations and only then `exec`s the server, so:

- migrations complete before the process accepts traffic;
- a failing migration exits non-zero, the Dockerfile `HEALTHCHECK` on
  `/healthz` never passes, the deploy is marked failed and the previous
  container keeps serving.

### First deploy (needs account access)

1. On the Coolify instance, create a Postgres 18 database and an application
   built from this repository's `Dockerfile`. Turn Coolify's auto-deploy and
   its own health probe off (the image ships neither curl nor wget; Coolify
   falls back to the Dockerfile `HEALTHCHECK`).
2. Set the application's environment: `ENVIRONMENT=production`, `PORT`,
   `DATABASE_URL` (the VPS Postgres), `AUTH_PASSWORD_HASH`,
   `SESSION_SECRET_KEY`, `GEMINI_API_KEY`, `GEMINI_DATA_TERMS_VERIFIED_AT`.
   See `.env.example` for each one and how to generate the secrets.
3. Add the `COOLIFY_DEPLOY_WEBHOOK` and `COOLIFY_API_TOKEN` repository secrets
   on GitHub; until both exist the `deploy` job is skipped with a notice.
4. Push to `main`, then confirm over HTTPS that `/healthz` responds and that
   the deploy log shows migrations completing before the server starts.

## Running cost

At the target volume of 30–200 Reports per month:

| Component | Plan | Cost |
| --- | --- | --- |
| Netcup VPS 1000 G12 (Vienna, AT): Coolify, app container, Postgres 18 | VPS 1000 G12 (256 GB disk) | €12 |
| Gemini API (`gemini-2.5-flash`, paid tier) | Pay per use | usage-based |
| **Total** | | **€12/month + Gemini usage** |

Payload growth is a few hundred MB a year, so the disk is not a constraint
(RGD-3, `docs/release-validation/storage-growth.md`).
