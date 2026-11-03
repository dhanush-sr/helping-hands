#!/bin/sh
# Container entry point (HH-19): bring the database up to date, optionally load the
# demo data, then start the API. The host sets PORT; 8000 when run locally.
set -e

alembic upgrade head

# Test environment only: HH_SEED_DEMO=true loads the demo data into an empty database.
# It is skipped when the data is already there, so restarts keep what testers entered.
if [ "${HH_SEED_DEMO:-false}" = "true" ]; then
  python -m app.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
