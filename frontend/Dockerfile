FROM node:20-alpine AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

# Copy frontend source code (excluding .env files via .dockerignore)
COPY frontend .

# Build-time API base URL - using build argument instead of .env files
ARG VITE_API_BASE_URL=https://aict-desa.lksnext.com
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# OIDC Configuration - map OIDC_ENABLED to VITE_OIDC_ENABLED for Vite
ARG OIDC_ENABLED=true
ENV VITE_OIDC_ENABLED=${OIDC_ENABLED}

# Set environment variables for Vite build
ENV NODE_ENV=production

RUN echo "Using VITE_API_BASE_URL=${VITE_API_BASE_URL} and VITE_OIDC_ENABLED=${VITE_OIDC_ENABLED}" && npm run build:production

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
