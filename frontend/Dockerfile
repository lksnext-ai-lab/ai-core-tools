# ============================================================================
# MATTIN AI - Frontend Dockerfile
# ============================================================================
# Multi-stage build para optimizar el tamaño de la imagen
# ============================================================================

# ----------------------------------------------------------------------------
# Stage 1: Build
# ----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copiar archivos de dependencias primero (mejor cache de capas)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

# Copiar código fuente del frontend
COPY frontend .

# Variables de build-time para Vite
# Estas se embeben en el bundle durante la compilación
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# Build de producción
ENV NODE_ENV=production
RUN echo "Building with VITE_API_BASE_URL=${VITE_API_BASE_URL}" && \
    npm run build:production

# ----------------------------------------------------------------------------
# Stage 2: Production (Nginx)
# ----------------------------------------------------------------------------
FROM nginx:alpine

# Metadatos
LABEL maintainer="LKS Next"
LABEL description="Mattin AI Frontend"

# Copiar archivos compilados
COPY --from=builder /app/dist /usr/share/nginx/html

# Copiar configuración de Nginx
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copiar script de configuración de runtime
COPY frontend/generate-config.sh /docker-entrypoint.d/40-generate-config.sh
RUN chmod +x /docker-entrypoint.d/40-generate-config.sh

# Puerto expuesto
EXPOSE 80

# Comando por defecto (Nginx ya tiene su propio entrypoint que ejecuta los scripts)
CMD ["nginx", "-g", "daemon off;"]
