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
    // Fallback to environment variable or default
    const baseUrl = import.meta.env.VITE_API_BASE_URL || 
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
