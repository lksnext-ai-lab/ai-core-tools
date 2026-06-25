import { configService } from '../core/ConfigService';
import type { User } from 'oidc-client-ts';
import { getCsrfToken } from './cookies';

class AuthService {
  private get baseURL(): string {
    return configService.getApiBaseUrl();
  }

  // Handles both { detail: string } (HTTPException) and Pydantic 422 array shapes.
  private async extractErrorMessage(response: Response, fallback: string): Promise<string> {
    const data = await response.json().catch(() => null);
    const detail = (data as { detail?: unknown } | null)?.detail;

    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown };
      if (typeof first.msg === 'string') {
        // Pydantic v2 prefixes ValueError messages with "Value error, "
        return first.msg.replace(/^Value error,\s*/i, '');
      }
    }
    return fallback;
  }

  // In-memory OIDC ID token; api.ts reads it synchronously for the bearer header.
  private oidcAccessToken: string | null = null;

  /** Stores the ID token (not the access token) — Azure AD access tokens fail
   *  backend audience validation (aud = api://<client_id> vs. aud = client_id). */
  setOIDCToken(user: User) {
    this.oidcAccessToken = user.id_token ?? null;
  }

  getOIDCToken(): string | null {
    return this.oidcAccessToken;
  }

  clearOIDCToken() {
    this.oidcAccessToken = null;
  }

  // Alias kept for callers being migrated off clearAuth().
  clearAuth() {
    this.clearOIDCToken();
  }

  /** @deprecated Prefer UserContext.user — unreliable for LOCAL cookie sessions. */
  isAuthenticated(): boolean {
    return this.oidcAccessToken !== null;
  }

  /** Sets httpOnly access_token + refresh_token cookies and a readable csrf_token cookie. */
  async localLogin(email: string, password: string): Promise<{ user: { user_id: number; email: string; name?: string; is_admin?: boolean; is_omniadmin?: boolean } }> {
    const url = `${this.baseURL}/internal/auth/login`;
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      throw new Error(await this.extractErrorMessage(response, 'Login failed'));
    }

    return response.json();
  }

  async logout(): Promise<void> {
    const url = `${this.baseURL}/internal/auth/logout`;
    const csrf = getCsrfToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (csrf) {
      headers['X-CSRF-Token'] = csrf;
    }

    await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
    }).catch(() => {}); // best-effort
  }

  /** Rotates the cookie pair; used by api.ts for silent-refresh on 401. */
  async refresh(): Promise<boolean> {
    const url = `${this.baseURL}/internal/auth/refresh`;
    const csrf = getCsrfToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (csrf) {
      headers['X-CSRF-Token'] = csrf;
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers,
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    const url = `${this.baseURL}/internal/auth/change-password`;
    const csrf = getCsrfToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (csrf) {
      headers['X-CSRF-Token'] = csrf;
    }

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });

    if (!response.ok) {
      throw new Error(await this.extractErrorMessage(response, 'Password change failed'));
    }
  }

  /** One-time token flow; no session created — user must log in after. */
  async setPassword(token: string, password: string): Promise<void> {
    const url = `${this.baseURL}/internal/auth/set-password`;
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: password }),
    });

    if (!response.ok) {
      throw new Error(await this.extractErrorMessage(response, 'Set password failed. The link may have expired.'));
    }
  }

  async getCurrentUser(): Promise<{ user_id: number; email: string; name?: string; is_admin?: boolean; is_omniadmin?: boolean }> {
    const url = `${this.baseURL}/internal/me`;
    const headers: Record<string, string> = {};

    const oidcToken = this.oidcAccessToken;
    if (oidcToken) {
      headers['Authorization'] = `Bearer ${oidcToken}`;
    }

    const response = await fetch(url, {
      credentials: 'include',
      headers,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return response.json();
  }
}

export const authService = new AuthService();
