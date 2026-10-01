#!/usr/bin/env bash
# Bootstrap for the "charts" skill: install matplotlib.
# matplotlib and its dependencies (numpy, Pillow, contourpy, kiwisolver,
# fonttools, cycler, pyparsing) all ship prebuilt manylinux wheels, so this
# installs from wheels only — well inside the 120s bootstrap timeout.
set -euo pipefail

# numpy is pinned explicitly to 2.2.6 here to match the "data-analysis"
# skill's pin (see data-analysis/scripts/bootstrap.sh) — both skills install
# into the same shared sandbox site-packages. matplotlib==3.11.2 only
# requires numpy>=1.25, so without an explicit pin a charts-only agent (one
# that never triggers data-analysis's bootstrap) would float to whatever
# numpy is newest on a given day, with no protection against a future numpy
# release breaking matplotlib's ABI compatibility. Pinning the same exact
# version in both scripts keeps this deterministic regardless of bootstrap
# order, rather than relying on "convergence" (data-analysis silently
# downgrading/upgrading whatever numpy charts alone would have floated to).
python3 -m pip install --quiet --disable-pip-version-check \
  --only-binary=:all: --retries 2 --timeout 10 --no-cache-dir \
  --break-system-packages --root-user-action=ignore \
  "matplotlib==3.11.2" "numpy==2.2.6"

python3 -c "
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
print('matplotlib installed OK, backend', matplotlib.get_backend())
"
