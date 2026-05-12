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

# Instalar Poetry
RUN pip install --no-cache-dir "poetry>=2.2.0,<3.0.0"

# Copiar archivos de dependencias
COPY pyproject.toml poetry.lock ./

# Instalar dependencias de producción
RUN poetry config virtualenvs.create false && \
    poetry install --only=main --no-interaction --no-ansi --no-cache

# Optional sandbox provider dependencies.  The backend image is built from
# pyproject/poetry.lock, while the legacy backend/requirements.txt is not used
# by this Dockerfile.  Keep these installed in the image so selecting the
# OpenSandbox provider does not fail at runtime.
RUN pip install --no-cache-dir \
    "opensandbox==0.1.7" \
    "opensandbox-code-interpreter==0.1.2" \
    "daytona==0.173.0" \
    "e2b-code-interpreter==2.5.0"

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
#   UVICORN_WORKERS              (default 2)
#   UVICORN_LIMIT_CONCURRENCY    (default 100 por worker)
CMD ["sh", "-c", "cd / && python -m alembic upgrade head && cd /aict_backend && python -m uvicorn main:app --host=0.0.0.0 --port=8000 --workers ${UVICORN_WORKERS:-2} --limit-concurrency ${UVICORN_LIMIT_CONCURRENCY:-100}"]
