#!/usr/bin/env bash
# ============================================================================
# Run tests with automatic test database lifecycle management.
#
# Usage:
#   ./scripts/test.sh                    # Run all tests
#   ./scripts/test.sh -m unit            # Run only unit tests (no DB needed)
#   ./scripts/test.sh -m integration     # Run only integration tests
#   ./scripts/test.sh -k test_agents     # Run tests matching a pattern
#   ./scripts/test.sh --cov=backend      # Run with coverage
#
# The script starts the ephemeral test PostgreSQL container (port 5433),
# waits for it to be healthy, runs pytest, and stops the container.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="docker-compose.yaml"
PROFILE="test"
DB_SERVICE="db_test"
DB_CONTAINER="mattin-postgres-test"

# --- Start test database ---------------------------------------------------
echo "[test.sh] Starting test database..."
docker compose --profile "$PROFILE" up -d "$DB_SERVICE"

echo "[test.sh] Waiting for test database to be healthy..."
RETRIES=30
until docker exec "$DB_CONTAINER" pg_isready -U test_user -d test_db > /dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ "$RETRIES" -le 0 ]; then
        echo "[test.sh] ERROR: Test database did not become ready in time."
        docker compose --profile "$PROFILE" stop "$DB_SERVICE"
        exit 1
    fi
    sleep 1
done
echo "[test.sh] Test database ready."

# --- Run tests -------------------------------------------------------------
echo "[test.sh] Running pytest..."
set +e
pytest "$@"
EXIT_CODE=$?
set -e

# --- Cleanup ---------------------------------------------------------------
echo "[test.sh] Stopping test database..."
docker compose --profile "$PROFILE" stop "$DB_SERVICE"

exit $EXIT_CODE
