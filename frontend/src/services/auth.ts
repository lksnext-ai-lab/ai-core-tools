class AuthService {
  private readonly baseURL = import.meta.env.VITE_API_BASE_URL || 'https://aict-desa.lksnext.com';
  private readonly TOKEN_KEY = 'auth_token';
  private readonly EXPIRES_KEY = 'auth_expires';

  // ==================== TOKEN MANAGEMENT ====================
  
  setToken(token: string, expiresAt?: string) {
    localStorage.setItem(this.TOKEN_KEY, token);
    if (expiresAt) {
      localStorage.setItem(this.EXPIRES_KEY, expiresAt);
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
        this.clearAuth();
        return null;
      }
    }
    
    return token;
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

    const token = this.getToken();
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
          // Token expired or invalid
          this.clearAuth();
          window.location.href = '/login';
          throw new Error('Authentication required');
        }
        
        const errorData = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  // ==================== AUTHENTICATION FLOW ====================

  async getLoginMode(): Promise<{ mode: string; login_url?: string; state?: string; message?: string }> {
    return this.request('/auth/login');
  }

  async login() {
    try {
      const response = await this.getLoginMode();
      
      if (response.mode === 'FAKE') {
        // Fake login mode - don't redirect
        throw new Error('Fake login mode - use email login form');
      }
      
      // OIDC mode - redirect to Google OAuth
      if (response.login_url) {
        window.location.href = response.login_url;
      } else {
        throw new Error('No login URL provided');
      }
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  }

  async fakeLogin(email: string): Promise<{ access_token: string; user: any; expires_at: string }> {
    const response = await this.request('/auth/fake-login', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
    
    // Store the token
    if (response.access_token) {
      this.setToken(response.access_token, response.expires_at);
    }
    
    return response;
  }

  async verifyToken(token?: string): Promise<any> {
    const tokenToVerify = token || this.getToken();
    if (!tokenToVerify) {
      throw new Error('No token available');
    }

    return this.request('/auth/verify', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${tokenToVerify}`
      }
    });
  }

  async getCurrentUser(): Promise<any> {
    return this.request('/auth/me');
  }

  async logout() {
    try {
      // Call backend logout endpoint
      await this.request('/auth/logout', { method: 'POST' });
    } catch (error) {
      console.error('Logout API call failed:', error);
    } finally {
      // Clear local auth data regardless of API call result
      this.clearAuth();
      window.location.href = '/login';
    }
  }

  // ==================== AUTH CALLBACK HANDLING ====================

  handleAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    const expires = urlParams.get('expires');
    const error = urlParams.get('error');

    if (error) {
      console.error('Auth callback error:', error);
      return { success: false, error };
    }

    if (token) {
      this.setToken(token, expires || undefined);
      
      // Clean up URL
      window.history.replaceState({}, document.title, window.location.pathname);
      
      return { success: true, token };
    }

    return { success: false, error: 'No token received' };
  }

  // ==================== INITIALIZATION ====================

  async initialize(): Promise<boolean> {
    const token = this.getToken();
    if (!token) {
      return false;
    }

    try {
      await this.verifyToken(token);
      return true;
    } catch (error) {
      console.error('Token verification failed:', error);
      this.clearAuth();
      return false;
    }
  }
}

export const authService = new AuthService(); 