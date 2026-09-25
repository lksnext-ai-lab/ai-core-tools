#!/usr/bin/env bash
# Bootstrap for the "pdf" skill: install pypdf + pdfplumber.
# Both ship prebuilt manylinux wheels for their own code and for their
# transitive dependencies (pypdfium2, Pillow), so this installs from wheels
# only — no compilation — well inside the 120s bootstrap timeout.
# Versions are pinned above their respective fixed-CVE floors:
#   - pypdf>=6.16.2 (pypdf DoS/resource-exhaustion advisories)
#   - pdfplumber>=0.11.10 (resolves pdfminer.six past CVE-2025-64512 / GHSA-wf5f-4jwr-ppcp)
set -euo pipefail

python3 -m pip install --quiet --disable-pip-version-check \
  --only-binary=:all: --retries 2 --timeout 10 --no-cache-dir \
  --break-system-packages --root-user-action=ignore \
  "pypdf==6.16.2" "pdfplumber==0.11.10"

python3 -c "import pypdf, pdfplumber; print('pypdf/pdfplumber installed OK')"
