#!/bin/sh
# Migrations complete before traffic is accepted.
#
# Render's pre-deploy command is a paid-instance feature, and this project must
# stay inside the free tier. So the ordering is enforced here instead: migrations
# run first, a non-zero exit aborts the container before it can serve (the deploy
# then fails its health check and the previous version keeps running), and the
# server replaces this shell via exec so the container runs a single process.
#
# Everything that can fail cheaply is checked BEFORE the migration, because the
# migration is the irreversible step. Aborting after it has run would leave the
# schema ahead of any code that is actually serving.

set -eu

# A missing CMD would make `exec "$@"` a silent no-op: migrations would run, the
# script would exit 0, and nothing would ever serve.
if [ "$#" -eq 0 ]; then
    echo "docker-entrypoint.sh: no command given; refusing to migrate and then serve nothing." >&2
    exit 64
fi

# The server needs PORT, but only dereferences it after the migration. Check it
# here so an unset or malformed value fails before the database is touched.
if [ -z "${PORT:-}" ]; then
    echo "docker-entrypoint.sh: PORT is not set. It is required and has no default;" >&2
    echo "  hosting platforms supply it, and compose.yaml sets it explicitly." >&2
    exit 78
fi

case "${PORT}" in
    *[!0-9]*)
        echo "docker-entrypoint.sh: PORT is invalid: '${PORT}' is not a positive integer." >&2
        exit 78
        ;;
esac

echo "Applying database migrations..."
alembic upgrade head

echo "Migrations complete; starting the server on port ${PORT}."
exec "$@"
