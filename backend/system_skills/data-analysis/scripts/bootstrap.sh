#!/usr/bin/env bash
# Bootstrap for the "data-analysis" skill: ensure pandas/numpy are present.
# pandas and numpy are common Jupyter-kernel dependencies and may already be
# installed in the sandbox image — `pip install` is a fast no-op in that case
# (pip checks the already-satisfied requirement and skips re-downloading),
# so pinning explicit versions here is safe and keeps behavior deterministic
# either way, well inside the 120s bootstrap timeout.
set -euo pipefail

# numpy is pinned to the same explicit 2.2.6 version as the "charts" skill's
# bootstrap (see charts/scripts/bootstrap.sh) — both skills install into the
# same shared sandbox site-packages, so whichever bootstraps second must not
# silently downgrade/upgrade the other's numpy.
python3 -m pip install --quiet --disable-pip-version-check \
  --only-binary=:all: --retries 2 --timeout 10 --no-cache-dir \
  --break-system-packages --root-user-action=ignore \
  "numpy==2.2.6" "pandas==2.2.3" \
  "python-dateutil==2.9.0.post0" "pytz==2026.4" "tzdata==2026.4" "six==1.17.0"

python3 -c "import numpy, pandas; print('numpy/pandas installed OK')"
