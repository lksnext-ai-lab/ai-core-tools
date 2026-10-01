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
#   JavaScript, TypeScript) and create stable /usr/local/bin/jupyter and
#   /usr/local/bin/tslab symlinks so runtime startup does not depend on
#   versioned language paths.
#
#   RUNTIME: Replace /usr/bin/tail with init.sh, a thin wrapper that detects
#   the "tail -f /dev/null" invocation, starts Jupyter (with XSRF disabled so
#   execd's POST /sessions succeeds), waits until it is reachable, and then
#   exec's the real tail to keep the container alive.

FROM opensandbox/code-interpreter:v1.0.2

# System tools commonly needed by document-processing Skills and code runs:
# - poppler-utils: pdftoppm/pdfinfo for PDF rendering/extraction workflows.
# - libreoffice: headless Office document conversion.
RUN apt-get update -qq && \
    apt-get install -y -qq poppler-utils libreoffice && \
    rm -rf /var/lib/apt/lists/*

# Pre-install kernel specs and create stable runtime symlinks.
#
# code-interpreter-env.sh sets up PATH for each language (Python, Java, etc.).
# We source it to get the right binary paths, run the kernel install steps
# that code-interpreter.sh would normally run at container start, and then
# create stable symlinks so init.sh and Jupyter kernels can call their binaries
# without needing the versioned language paths.
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
    ln -sf "$(which jupyter)" /usr/local/bin/jupyter       && \
    ln -sf "$(which tslab)" /usr/local/bin/tslab           && \
    jupyter kernelspec list                                && \
    test -f /usr/local/share/jupyter/kernels/jslab/kernel.json && \
    test -f /usr/local/share/jupyter/kernels/tslab/kernel.json \
'

# Replace the /usr/bin/tail binary with init.sh.
# The opensandbox-server starts sandbox containers with ENTRYPOINT=["tail"],
# so this wrapper is the first thing that runs inside every new sandbox.
RUN mv /usr/bin/tail /usr/bin/tail.real
COPY init.sh /usr/bin/tail
RUN chmod +x /usr/bin/tail
