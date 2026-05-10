#!/bin/bash
# Jupyter bootstrap wrapper for opensandbox sandbox containers.
#
# The opensandbox-server bootstraps every sandbox container by overriding its
# image ENTRYPOINT with:
#
#   ["tail", "-f", "/dev/null"]
#
# and then injecting the execd binary into the running container.  execd
# expects a Jupyter notebook server listening on JUPYTER_PORT (default 44771)
# using JUPYTER_TOKEN for auth, with XSRF checking disabled.
#
# Because the image ENTRYPOINT is replaced, the upstream code-interpreter.sh
# that normally installs kernel specs and starts Jupyter never runs.  This
# script intercepts the "tail -f /dev/null" call, starts Jupyter with the
# settings execd requires, waits until Jupyter is accepting authenticated
# connections, and then exec's the real tail binary to keep the container alive.
#
# Kernel specs (Python, Java, Bash, Go, JavaScript, TypeScript) are
# pre-installed at image build time by the Dockerfile so they are available
# immediately. Stable /usr/local/bin symlinks are also created at build time so
# Jupyter and tslab can be found even when OpenSandbox replaces the image
# entrypoint.

JUPYTER_PORT="${JUPYTER_PORT:-44771}"
JUPYTER_TOKEN="${JUPYTER_TOKEN:-opensandboxcodeinterpreterjupyter}"

case "$*" in
  "-f /dev/null")
    if [ -f /opt/opensandbox/code-interpreter-env.sh ]; then
      # Give Jupyter kernels the same language PATH setup as the upstream
      # code-interpreter entrypoint, including Node for jslab/tslab.
      . /opt/opensandbox/code-interpreter-env.sh python >/dev/null 2>&1 || true
      . /opt/opensandbox/code-interpreter-env.sh node >/dev/null 2>&1 || true
      . /opt/opensandbox/code-interpreter-env.sh go >/dev/null 2>&1 || true
    fi

    jupyter notebook \
        --ip=127.0.0.1 \
        --port="${JUPYTER_PORT}" \
        --NotebookApp.token="${JUPYTER_TOKEN}" \
        --NotebookApp.password='' \
        --ServerApp.disable_check_xsrf=True \
        --no-browser \
        --allow-root \
        --notebook-dir=/workspace \
        2>&1 &

    # Wait until Jupyter is accepting authenticated connections (up to 30 s).
    # Use the token as a query parameter so the health-check request succeeds
    # even though Jupyter requires authentication.
    i=0
    while [ $i -lt 30 ]; do
      if curl -sf -o /dev/null \
          "http://127.0.0.1:${JUPYTER_PORT}/api/kernelspecs?token=${JUPYTER_TOKEN}" \
          2>/dev/null; then
        break
      fi
      sleep 1
      i=$((i + 1))
    done
    ;;
esac

exec /usr/bin/tail.real "$@"
