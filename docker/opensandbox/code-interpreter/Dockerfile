# Custom Mattin AI sandbox image for opensandbox integration.
#
# Root cause: the opensandbox-server (via the SDK default) overrides the
# container ENTRYPOINT with ["tail", "-f", "/dev/null"], which prevents
# code-interpreter.sh from running.  Consequences:
#
#   1. Jupyter is never started  -> execd gets "connection refused"
#   2. Kernel specs are never installed  -> even a manually started Jupyter
#      would return "no kernel specs found"
#   3. The jupyter binary is not on PATH  -> calling it by name fails
#
# This image fixes all three issues:
#
#   BUILD TIME: Pre-install all kernel specs (Python, Java, Bash, Go,
#   TypeScript) and create a stable /usr/local/bin/jupyter symlink so the
#   binary is on the default PATH.
#
#   RUNTIME: Replace /usr/bin/tail with init.sh, a thin wrapper that detects
#   the "tail -f /dev/null" invocation, starts Jupyter (with XSRF disabled so
#   execd's POST /sessions succeeds), waits until it is reachable, and then
#   exec's the real tail to keep the container alive.

FROM opensandbox/code-interpreter:v1.0.2

# Pre-install kernel specs and create a stable jupyter symlink.
#
# code-interpreter-env.sh sets up PATH for each language (Python, Java, etc.).
# We source it to get the right binary paths, run the kernel install steps
# that code-interpreter.sh would normally run at container start, and then
# create /usr/local/bin/jupyter so init.sh can call it by name without needing
# the versioned Python path.
RUN bash -c '\
    source /opt/opensandbox/code-interpreter-env.sh python && \
    source /opt/opensandbox/code-interpreter-env.sh java  && \
    source /opt/opensandbox/code-interpreter-env.sh node  && \
    source /opt/opensandbox/code-interpreter-env.sh go    && \
    export PATH="$(go env GOPATH)/bin:$PATH"              && \
    python3 -m ipykernel install --name python --display-name "Python" && \
    python3 /opt/ijava/install.py --sys-prefix             && \
    python3 -m bash_kernel.install                         && \
    gonb --install                                         && \
    npm install -g tslab                                   && \
    tslab install                                          && \
    ln -sf "$(which jupyter)" /usr/local/bin/jupyter \
'

# Replace the /usr/bin/tail binary with init.sh.
# The opensandbox-server starts sandbox containers with ENTRYPOINT=["tail"],
# so this wrapper is the first thing that runs inside every new sandbox.
RUN mv /usr/bin/tail /usr/bin/tail.real
COPY init.sh /usr/bin/tail
RUN chmod +x /usr/bin/tail
