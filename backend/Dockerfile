# Multi-stage build para reducir tamaño final
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependencias de compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libmariadb-dev \
    libpq-dev \
    python3-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar Poetry con la versión que funciona
RUN pip install --no-cache-dir "poetry>=1.4.0,<2.0.0"

# Copiar archivos de dependencias (están en el directorio padre)
COPY ../pyproject.toml ../poetry.lock ./

# Generar requirements.txt usando Poetry y crear ambiente virtual limpio
RUN poetry config virtualenvs.create false && \
    poetry install --only=main --no-interaction --no-ansi --no-cache

# Imagen final más pequeña
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/aict_backend

ENV AICT_MODE=SELF-HOSTED \
    DEVELOPMENT_MODE=false \
    JWT_ALGORITHM=HS256 \
    JWT_EXPIRATION_HOURS=24 \
    FRONTEND_URL=http://localhost:5173

WORKDIR /aict_backend

# Instalar solo dependencias de runtime necesarias (ordenadas alfabéticamente)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libmariadb3 \
    libpq5 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copiar dependencias Python desde builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copiar código de la aplicación (excluding .env files via .dockerignore)
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

EXPOSE 8000

# Healthcheck más eficiente
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

WORKDIR /aict_backend

CMD ["sh", "-c", "cd / && python -m alembic upgrade head && cd /aict_backend && python -m uvicorn main:app --host=0.0.0.0 --port=8000"]
