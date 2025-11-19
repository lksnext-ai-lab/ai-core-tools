#!/bin/sh
# Generate runtime configuration for the frontend
# This script reads environment variables and creates a config.js file
# that will be loaded by the frontend application

cat <<EOF > /usr/share/nginx/html/config.js
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

echo "Runtime configuration generated:"
cat /usr/share/nginx/html/config.js

# Start nginx
exec "$@"
