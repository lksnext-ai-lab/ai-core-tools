# Seeds development users into a running Docker deployment (FAKE login mode).
#
# Runs the backend's seeding module inside the already-running backend container,
# reusing its database configuration. No host Python or DB access required.
#
# Usage (from the docker/ directory or anywhere):
#   .\seed-users.ps1                       # built-in defaults or AICT_DEV_SEED_USERS
#   .\seed-users.ps1 --users "a@x.com:Ana,b@x.com:Bob"
#   .\seed-users.ps1 --list                # dry-run: show resolved users
#
# Any extra arguments are forwarded to `python -m utils.seed_dev_users`.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$running = docker compose ps --status running --services
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose is not available or this is not a compose project."
    exit 1
}
if ($running -notcontains "backend") {
    Write-Error "The 'backend' service is not running. Start the stack first: docker compose up -d"
    exit 1
}

docker compose exec -T backend python -m utils.seed_dev_users --yes @args
exit $LASTEXITCODE
