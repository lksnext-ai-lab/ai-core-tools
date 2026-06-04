#!/usr/bin/env bash
# Seeds development users into a running Docker deployment (FAKE login mode).
#
# Runs the backend's seeding module inside the already-running backend container,
# reusing its database configuration. No host Python or DB access required.
#
# Usage (from anywhere):
#   ./seed-users.sh                        # built-in defaults or AICT_DEV_SEED_USERS
#   ./seed-users.sh --users "a@x.com:Ana,b@x.com:Bob"
#   ./seed-users.sh --list                 # dry-run: show resolved users
#
# Any extra arguments are forwarded to `python -m utils.seed_dev_users`.
set -euo pipefail

cd "$(dirname "$0")"

if ! docker compose ps --status running --services | grep -qx backend; then
  echo "ERROR: the 'backend' service is not running. Start the stack first: docker compose up -d" >&2
  exit 1
fi

exec docker compose exec -T backend python -m utils.seed_dev_users --yes "$@"
