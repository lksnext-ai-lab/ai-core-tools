import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Backend path prefixes served by the API. Kept in sync with docker/Caddyfile
// so local terminal dev (Vite proxy below) and the Docker deployment (Caddy)
// route requests to the backend identically — both present a single origin.
const BACKEND_PATHS = [
  '/internal',
  '/public',
  '/mcp',
  '/a2a',
  '/.well-known/agent-card.json',
  '/static',
  '/docs',
  '/scalar',
  '/health',
  '/openapi-internal.json',
  '/openapi-public.json',
];

export default defineConfig(({ mode }) => {
  // Default dev/build config
  const env = loadEnv(mode, process.cwd(), '');
  // Backend target for the dev-server proxy (local terminal dev only).
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000';

  // Mirror the Caddy reverse proxy: forward every backend path prefix to the
  // backend so the frontend can use same-origin relative paths (/internal, …)
  // in terminal dev exactly as it does behind Caddy in Docker. No CORS needed.
  const proxy = Object.fromEntries(
    BACKEND_PATHS.map((prefix) => [
      prefix,
      { target: proxyTarget, changeOrigin: true, ws: true },
    ])
  );

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy
    }
  };
});
