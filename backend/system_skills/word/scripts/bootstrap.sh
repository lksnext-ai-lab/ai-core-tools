#!/usr/bin/env bash
# Bootstrap for the "word" skill: install python-docx into the sandbox.
# Kept to a single, small, pure-Python (no compiled extensions) dependency so
# this installs from a prebuilt wheel in a few seconds, well inside the
# SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S (120s) budget.
set -euo pipefail

python3 -m pip install --quiet --disable-pip-version-check \
  --only-binary=:all: --retries 2 --timeout 10 --no-cache-dir \
  --break-system-packages --root-user-action=ignore \
  "python-docx==1.2.0"

python3 -c "import docx; print('python-docx installed OK')"
