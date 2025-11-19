import type { ClientConfig, ApiConfig } from './types';

class ConfigService {
  private static instance: ConfigService;
  private clientConfig: ClientConfig | null = null;
  private apiConfig: ApiConfig | null = null;

  private constructor() {}

  static getInstance(): ConfigService {
    if (!ConfigService.instance) {
      ConfigService.instance = new ConfigService();
    }
    return ConfigService.instance;
  }

  setClientConfig(config: ClientConfig): void {
    this.clientConfig = config;
    this.apiConfig = config.api || this.getDefaultApiConfig();
  }

  getClientConfig(): ClientConfig | null {
    return this.clientConfig;
  }

  getApiConfig(): ApiConfig {
    return this.apiConfig || this.getDefaultApiConfig();
  }

  getApiBaseUrl(): string {
    const apiConfig = this.getApiConfig();
    return apiConfig.baseUrl;
  }

  private getDefaultApiConfig(): ApiConfig {
    // Try to get runtime configuration first (injected at container startup)
    const runtimeConfig = (window as any).__RUNTIME_CONFIG__;
    
    // Fallback chain: runtime config -> build-time env vars -> default
    const baseUrl = runtimeConfig?.VITE_API_BASE_URL || 
                   import.meta.env.VITE_API_BASE_URL || 
                   import.meta.env.VITE_API_URL || 
                   'http://localhost:8000';
    
    return {
      baseUrl,
      timeout: 30000,
      retries: 3
    };
  }

  // Helper method to get configuration from backend
  async loadConfigFromBackend(): Promise<Partial<ClientConfig> | null> {
    try {
      // Get runtime configuration if available
      const runtimeConfig = (window as any).__RUNTIME_CONFIG__;
      
      // Check if OIDC is enabled via runtime config
      const oidcEnabled = runtimeConfig?.VITE_OIDC_ENABLED === 'true';
      
      if (oidcEnabled && runtimeConfig) {
        // Use runtime configuration for OIDC
        return {
          clientId: runtimeConfig.VITE_OIDC_CLIENT_ID || '',
          name: 'IA Core Tools',
          auth: {
            type: 'oidc',
            oidc: {
              enabled: true,
              authority: runtimeConfig.VITE_OIDC_AUTHORITY || '',
              clientId: runtimeConfig.VITE_OIDC_CLIENT_ID || '',
              redirectUri: runtimeConfig.VITE_OIDC_REDIRECT_URI || `${window.location.origin}/auth/success`,
              scope: runtimeConfig.VITE_OIDC_SCOPE || 'openid profile email',
              audience: runtimeConfig.VITE_OIDC_AUDIENCE
            }
          }
        };
      }
      
      // Fallback to backend API config
      const baseUrl = this.getApiBaseUrl();
      const response = await fetch(`${baseUrl}/api/internal/client-config`);
      
      if (!response.ok) {
        throw new Error(`Failed to load config: ${response.status}`);
      }
      
      const config = await response.json();
      return {
        clientId: config.client_id,
        name: config.client_name,
        auth: {
          type: config.oidc_enabled ? 'oidc' : 'session',
          oidc: config.oidc_enabled ? {
            enabled: true,
            authority: config.oidc_authority || '',
            clientId: config.oidc_client_id || '',
            redirectUri: `${window.location.origin}/callback`,
            scope: 'openid profile email'
          } : undefined
        }
      };
    } catch (error) {
      console.warn('Failed to load config from backend:', error);
      return null;
    }
  }
}

export const configService = ConfigService.getInstance();
