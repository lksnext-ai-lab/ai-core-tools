# ============================================================================
# MATTIN AI - Backend Dockerfile
# ============================================================================
# Multi-stage build para optimizar el tamaño de la imagen
# ============================================================================

# ----------------------------------------------------------------------------
# Stage 1: Builder (instalar dependencias)
# ----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependencias de compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libmariadb-dev \
    libpq-dev \
    pkg-config \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar Poetry: versión fijada y verificada por hash, solo wheels (no se
# ejecutan scripts de instalación de paquetes en código fuente).
COPY backend/requirements-poetry.txt ./
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements-poetry.txt

# Copiar archivos de dependencias
COPY pyproject.toml poetry.lock ./

# Instalar dependencias de producción — includes the optional sandbox
# provider SDKs (opensandbox, daytona, e2b-code-interpreter), now managed
# directly in pyproject.toml/poetry.lock rather than a separate ad-hoc `pip
# install` step, so their transitive dependencies are pinned and reproducible.
# (e2b is pinned explicitly in pyproject.toml because e2b-code-interpreter
# only declares a loose `e2b>=2.7.0,<3.0.0` — an unpinned resolve previously
# picked up a newer e2b release that broke `create_code_context()`/
# `run_code()` with `AttributeError: 'Sandbox' object has no attribute
# '_transport'`.)
# POETRY_INSTALLER_ONLY_BINARY: every dependency is installed from a wheel,
# so no package setup script runs during the build.
RUN poetry config virtualenvs.create false && \
    POETRY_INSTALLER_ONLY_BINARY=:all: poetry install --only=main --no-interaction --no-ansi --no-cache

# ----------------------------------------------------------------------------
# Stage 2: Production
# ----------------------------------------------------------------------------
FROM python:3.11-slim

# Metadatos
LABEL maintainer="LKS Next"
LABEL description="Mattin AI Backend API"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/aict_backend

WORKDIR /aict_backend

# Instalar dependencias de runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libmariadb3 \
    libpq5 \
    ffmpeg \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copiar dependencias Python desde builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copiar código de la aplicación
COPY backend/ /aict_backend/
COPY alembic /alembic/
COPY alembic.ini /alembic.ini
COPY pyproject.toml /aict_backend/pyproject.toml

# Crear directorios necesarios
RUN mkdir -p /aict_backend/data/repositories \
             /aict_backend/data/temp/uploads \
             /aict_backend/data/temp/downloads \
             /aict_backend/data/temp/images \
             /aict_backend/logs && \
    # Limpiar archivos innecesarios
    find /aict_backend -name "*.pyc" -delete && \
    find /aict_backend -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Puerto expuesto
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Comando de inicio: ejecutar migraciones y luego la aplicación.
# Workers y concurrencia parametrizables via env vars para poder ajustar el
# consumo de memoria por despliegue sin rebuild. Cada worker uvicorn carga
# FastAPI + SQLAlchemy + LangChain en su propio proceso (~0.5–1.5 GB RSS),
# asi que en hosts pequeños conviene bajarlo a 1.
#   UVICORN_WORKERS                     (default 2)
#   UVICORN_LIMIT_CONCURRENCY           (default 100 por worker; ver también
#                                        A2A_MAX_CONCURRENT_STREAMS_WORKER,
#                                        que se auto-clampa por debajo de
#                                        este valor, backend/utils/a2a_config.py)
#   UVICORN_GRACEFUL_SHUTDOWN_SECONDS   (default 20; step_021, RB-15)
#   UVICORN_FORWARDED_ALLOW_IPS         (default el rango RFC1918 completo;
#                                        step_021, RB-9/RB-16 — ver más abajo)
#
# `exec` en el `uvicorn` final (no en el `alembic upgrade head` previo, que sí
# debe terminar y devolver el control al shell) es obligatorio: sin él, `sh`
# queda como PID 1 y no reenvía SIGTERM a sus hijos, así que `docker stop`
# esperaría el grace period completo y luego mataría con SIGKILL sin que el
# lifespan de FastAPI llegue a ejecutarse nunca (RB-1's close_runtime jamás
# correría). Con `exec`, uvicorn sustituye a `sh` como PID 1 y recibe el
# SIGTERM directamente.
#
# --timeout-graceful-shutdown: tras SIGTERM, uvicorn deja de aceptar
# conexiones nuevas y da hasta este margen a las conexiones en curso (incluye
# los streams SSE de A2A — sse-starlette 3.0.2 no cierra solo sus streams
# abiertos al recibir la señal) antes de cerrarlas a la fuerza. El lifespan
# `shutdown` (incluido `close_runtime`, timeout interno de 10s,
# backend/services/a2a_server/runtime.py) corre DESPUES de esta ventana.
# docker-compose.yaml fija `stop_grace_period` del servicio backend por
# encima de este valor (con margen para close_runtime y el resto de pasos del
# lifespan) para que Docker no SIGKILL-ee antes de que uvicorn termine su
# propio apagado ordenado.
#
# --proxy-headers --forwarded-allow-ips: necesario para que
# `request.client.host` sea la IP real del cliente (y no la de Caddy) en el
# limitador de descubrimiento A2A (FR-21) y en cualquier otro uso de la IP
# del cliente. NUNCA '*' (RB-9/RB-16): uvicorn confía en el X-Forwarded-For
# entrante sin verificarlo contra ningún rango si se usa '*', lo que permite a
# cualquier cliente spoofear su propia IP.
#
# Modelo de confianza (fix round 1, H1/M1): backend:8000 NUNCA se publica al
# host (solo Caddy publica un puerto, ver docker-compose.yaml) y solo otros
# peers de `mattin-network` pueden alcanzarlo — en la práctica, solo Caddy la
# usa para llegar al backend. Caddy reemplaza el X-Forwarded-For del cliente
# por su propia IP real (trusted_proxies sin configurar, ver docker/Caddyfile)
# antes de reenviar, así que confiar en cualquier peer de la red docker
# equivale a confiar únicamente en Caddy. Por eso el valor por defecto es el
# rango RFC1918 completo (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) en vez de
# una subred fija: fijar una subred exigía recrear la red (y por tanto el
# stack entero) en cada arranque con `ipam.config`, lo que chocaba con
# despliegues multi-entorno en el mismo host y con cualquier daemon Docker
# cuyo rango de direcciones por defecto ya caiga en 172.16/12 (habitual en
# redes corporativas). El rango RFC1918 completo sigue excluyendo cualquier
# IP pública, que es lo que de verdad importa aquí.
#
# Si el daemon Docker (o, en K8s, el CIDR de pods/servicios del clúster) usa
# un rango fuera de RFC1918 — p. ej. el pool de direcciones por defecto de
# Docker puede extenderse a 100.64.0.0/10 en algunas instalaciones, o el CIDR
# de pods de tu clúster K8s — fija UVICORN_FORWARDED_ALLOW_IPS explícitamente
# a ese rango (o al CIDR real del Service/Ingress que hace de proxy).
CMD ["sh", "-c", "cd / && python -m alembic upgrade head && cd /aict_backend && exec python -m uvicorn main:app --host=0.0.0.0 --port=8000 --workers \"${UVICORN_WORKERS:-2}\" --limit-concurrency \"${UVICORN_LIMIT_CONCURRENCY:-100}\" --timeout-graceful-shutdown \"${UVICORN_GRACEFUL_SHUTDOWN_SECONDS:-20}\" --proxy-headers --forwarded-allow-ips \"${UVICORN_FORWARDED_ALLOW_IPS:-10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}\""]
