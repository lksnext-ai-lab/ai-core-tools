#!/bin/sh
# ============================================================================
# MATTIN AI - Runtime Configuration Generator
# ============================================================================
# Este script genera la configuración de runtime para el frontend
# Se ejecuta al iniciar el contenedor de Docker (antes de Nginx)
# ============================================================================

set -e

CONFIG_FILE="/usr/share/nginx/html/config.js"

echo "=========================================="
echo "Generating runtime configuration..."
echo "=========================================="

# Generar archivo de configuración
cat > "$CONFIG_FILE" <<EOF
// Auto-generated runtime configuration
// Generated at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
window.__RUNTIME_CONFIG__ = {
  VITE_API_BASE_URL: "${VITE_API_BASE_URL:-http://localhost:8000}",
  VITE_OIDC_ENABLED: "${VITE_OIDC_ENABLED:-false}",
  VITE_OIDC_AUTHORITY: "${VITE_OIDC_AUTHORITY:-}",
  VITE_OIDC_CLIENT_ID: "${VITE_OIDC_CLIENT_ID:-}",
  VITE_OIDC_REDIRECT_URI: "${VITE_OIDC_REDIRECT_URI:-}",
  VITE_OIDC_SCOPE: "${VITE_OIDC_SCOPE:-openid profile email}",
  VITE_OIDC_AUDIENCE: "${VITE_OIDC_AUDIENCE:-}"
};
EOF

echo "Runtime configuration:"
echo "  - API URL: ${VITE_API_BASE_URL:-http://localhost:8000}"
echo "  - OIDC Enabled: ${VITE_OIDC_ENABLED:-false}"

if [ "${VITE_OIDC_ENABLED:-false}" = "true" ]; then
  echo "  - OIDC Authority: ${VITE_OIDC_AUTHORITY:-NOT SET}"
  echo "  - OIDC Client ID: ${VITE_OIDC_CLIENT_ID:-NOT SET}"
  
  # Validar configuración OIDC
  if [ -z "$VITE_OIDC_AUTHORITY" ] || [ -z "$VITE_OIDC_CLIENT_ID" ]; then
    echo ""
    echo "⚠️  WARNING: OIDC is enabled but VITE_OIDC_AUTHORITY or VITE_OIDC_CLIENT_ID is not set!"
    echo "    Authentication may not work correctly."
  fi
fi

echo "=========================================="
echo "Configuration saved to: $CONFIG_FILE"
echo "=========================================="
