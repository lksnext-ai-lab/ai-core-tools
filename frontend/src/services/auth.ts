import { configService } from '../core/ConfigService';
import type { User } from 'oidc-client-ts';

class AuthService {
  private get baseURL(): string {
    return configService.getApiBaseUrl();
  }
  private readonly TOKEN_KEY = 'auth_token';
  private readonly EXPIRES_KEY = 'auth_expires';

  // ==================== TOKEN MANAGEMENT ====================
  
  setToken(token: string, expiresAt?: string) {
    localStorage.setItem(this.TOKEN_KEY, token);
    if (expiresAt) {
      localStorage.setItem(this.EXPIRES_KEY, expiresAt);
    }
  }

  setOIDCToken(user: User) {
    if (user.access_token) {
      const expiresAt = user.expires_at 
        ? new Date(user.expires_at * 1000).toISOString()
        : undefined;
      this.setToken(user.access_token, expiresAt);
    }
  }

  getToken(): string | null {
    const token = localStorage.getItem(this.TOKEN_KEY);
    const expires = localStorage.getItem(this.EXPIRES_KEY);
    
    if (!token) return null;
    
    // Check if token is expired
    if (expires) {
      const expiryDate = new Date(expires);
      if (expiryDate <= new Date()) {
        // Token is expired
        console.warn('Token expired');
        this.clearAuth();
        return null;
      }
    }
    
    return token;
  }

  async getValidToken(): Promise<string | null> {
    // Simply return the current token from localStorage
    // OIDC token refresh is handled by OIDCProvider
    return this.getToken();
  }

  clearAuth() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.EXPIRES_KEY);
  }

  isAuthenticated(): boolean {
    return this.getToken() !== null;
  }

  // ==================== API REQUESTS ====================

  private async request(endpoint: string, options: RequestInit = {}) {
    const url = `${this.baseURL}${endpoint}`;
    
    const defaultHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    const token = await this.getValidToken();
    if (token) {
      defaultHeaders['Authorization'] = `Bearer ${token}`;
    }

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        if (response.status === 401) {
          // Clear auth on 401 but don't redirect
          // Let the calling code handle the error
          this.clearAuth();
        }
        
        const errorData = await response.json().catch(
          () => ({ detail: 'Request failed' })
        );
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  // ==================== AUTHENTICATION FLOW ====================

  // Development mode only - fake login for testing without OIDC
  async fakeLogin(email: string): Promise<{ access_token: string; user: any; expires_at: string }> {
    const response = await this.request('/internal/auth/dev-login', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
    
    // Store the token
    if (response.access_token) {
      this.setToken(response.access_token, response.expires_at);
    }
    
    return response;
  }

  // Get current user info (used for fake-login dev mode)
  // In OIDC mode, user info comes from the OIDC User object
  async getCurrentUser(): Promise<any> {
    return this.request('/auth/me');
  }
}

export const authService = new AuthService(); 