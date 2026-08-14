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

| Variable | Required | Accepted values |
| --- | --- | --- |
| `ENVIRONMENT` | yes | `local`, `production` — there is no staging |
| `DATABASE_URL` | yes | a Postgres URL (`postgres`, `postgresql` or `postgresql+psycopg` scheme) |
| `PORT` | yes | 1–65535; hosting platforms supply this themselves |

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

Production is one Render web service (free plan, EU region, Docker runtime)
backed by one Neon Postgres project (free plan, Europe/Frankfurt). All durable
state is in Postgres; the container filesystem is ephemeral and nothing written
at runtime is read back after a restart.

`render.yaml` is the blueprint. `docker-entrypoint.sh` applies migrations and
only then `exec`s the server, so:

- migrations complete before the process accepts traffic;
- a failing migration exits non-zero, the health check never passes, the deploy
  is marked failed and the previous version keeps serving.

Render's `preDeployCommand` would express this more directly, but it is a
paid-instance feature and this project must cost nothing. Move the migration
step there if the service ever moves to a paid plan.

### First deploy (needs account access)

1. Create the Neon project in **Europe/Frankfurt**, free plan, Postgres 18.
2. Create the Render service from `render.yaml` (Blueprint), region
   **Frankfurt**, free plan.
3. Set `DATABASE_URL` on the Render service to the Neon connection string. It is
   marked `sync: false` in the blueprint so the secret stays out of the
   repository. `PORT` is supplied by Render; `ENVIRONMENT=production` is in the
   blueprint.
4. Deploy, then confirm over HTTPS that `/healthz` responds and that the deploy
   log shows migrations completing before the server starts.

## Running cost

At the target volume of 30–200 Reports per month:

| Component | Plan | Cost |
| --- | --- | --- |
| Render web service (EU, Docker) | Free | €0 |
| Neon Postgres 18 (Europe/Frankfurt) | Free (0.5 GB) | €0 |
| **Total** | | **€0/month** |

The free Render service spins down when idle and takes a few seconds to wake —
acceptable, because availability is best-effort with no SLA. A design that would
require paid infrastructure at this volume is raised, not absorbed.
