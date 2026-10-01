#!/usr/bin/env bash
# Bootstrap for the "pptx" skill: install python-pptx.
# python-pptx and its dependencies (lxml, Pillow, XlsxWriter) all ship
# prebuilt manylinux wheels, so this installs from wheels only.
set -euo pipefail

python3 -m pip install --quiet --disable-pip-version-check \
  --only-binary=:all: --retries 2 --timeout 10 --no-cache-dir \
  --break-system-packages --root-user-action=ignore \
  "python-pptx==1.0.2"

python3 -c "import pptx; print('python-pptx installed OK')"
