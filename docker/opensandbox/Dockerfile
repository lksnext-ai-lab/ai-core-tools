# Custom Mattin OpenSandbox server image.
#
# Based on the upstream OpenSandbox server Dockerfile shape:
# https://github.com/alibaba/OpenSandbox/blob/main/server/Dockerfile
#
# The upstream image currently bakes a Kubernetes example config as its default.
# This image installs the released server package and bakes a Docker-runtime
# config by default, while still allowing operators to override configuration
# at container instantiation time with:
#
#   - SANDBOX_CONFIG_PATH=/path/to/config.toml
#   - a bind mount over /etc/opensandbox/sandbox.toml
#   - docker compose command: ["--config", "/path/to/config.toml"]

FROM python:3.10-slim AS runtime

ARG OPENSANDBOX_SERVER_VERSION=0.1.11

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SANDBOX_CONFIG_PATH=/etc/opensandbox/sandbox.toml \
    DOCKER_HOST=unix:///var/run/docker.sock

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "opensandbox-server==${OPENSANDBOX_SERVER_VERSION}"

COPY sandbox.toml /etc/opensandbox/sandbox.toml

RUN mkdir -p /var/lib/opensandbox

EXPOSE 8080

ENTRYPOINT ["opensandbox-server"]
CMD ["--config", "/etc/opensandbox/sandbox.toml"]
