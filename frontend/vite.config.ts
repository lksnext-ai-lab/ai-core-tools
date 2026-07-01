import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// Backend path prefixes served by the API. Kept in sync with docker/Caddyfile
// so local terminal dev (Vite proxy below) and the Docker deployment (Caddy)
// route requests to the backend identically — both present a single origin.
const BACKEND_PATHS = [
  '/internal',
  '/public',
  '/mcp',
  '/static',
  '/docs',
  '/scalar',
  '/health',
  '/openapi-internal.json',
  '/openapi-public.json',
];

export default defineConfig(({ mode }) => {
  if (mode === 'library') {
    return {
      plugins: [react()],
      build: {
        lib: {
          entry: path.resolve(__dirname, 'src/index.ts'),
          name: 'AICoreToolsBase',
          formats: ['es', 'cjs'],
          fileName: (format) => `index.${format === 'es' ? 'js' : 'cjs'}`
        },
        rollupOptions: {
          external: [
            'react', 
            'react-dom', 
            'react-router-dom',
            'axios',
            'oidc-client-ts',
            'react-markdown'
          ],
          output: {
            globals: {
              react: 'React',
              'react-dom': 'ReactDOM',
              'react-router-dom': 'ReactRouterDOM',
              'axios': 'axios',
              'oidc-client-ts': 'oidc-client-ts',
              'react-markdown': 'ReactMarkdown'
            },
            assetFileNames: (assetInfo) => {
              if (assetInfo.name?.endsWith('.css')) {
                return 'style.css';
              }
              return assetInfo.name || 'asset';
            }
          }
        },
        cssCodeSplit: false,
        minify: 'terser',
        sourcemap: true,
        target: 'es2020'
      }
    };
  }

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
