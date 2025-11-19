/**
 * Runtime configuration injected by the container at startup
 * Available via window.__RUNTIME_CONFIG__
 */
export interface RuntimeConfig {
  VITE_API_BASE_URL: string;
  VITE_OIDC_ENABLED: string;
  VITE_OIDC_AUTHORITY: string;
  VITE_OIDC_CLIENT_ID: string;
  VITE_OIDC_REDIRECT_URI: string;
  VITE_OIDC_SCOPE: string;
  VITE_OIDC_AUDIENCE: string;
}

declare global {
  interface Window {
    __RUNTIME_CONFIG__?: RuntimeConfig;
  }
}

export {};
