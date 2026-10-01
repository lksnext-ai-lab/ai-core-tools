import { configService } from '../core/ConfigService';
import type { User } from 'oidc-client-ts';
import { getCsrfToken } from './cookies';

export interface CurrentUserPayload {
  user_id: number;
  email: string;
  name?: string;
  is_admin?: boolean;
  is_omniadmin?: boolean;
  platform_role?: 'viewer' | 'editor' | 'admin';
}

/** `unauthorized`: the backend rejected the credentials. `unavailable`: network or server failure. */
export type CurrentUserResult =
  | { readonly status: 'ok'; readonly user: CurrentUserPayload }
  | { readonly status: 'unauthorized' }
  | { readonly status: 'unavailable' };

type OidcRenewHandler = () => Promise<boolean>;
type SessionExpiredListener = () => void;

// Serialises refresh-token rotation across tabs: the backend revokes the whole
// token family when a rotated refresh token is presented twice.
const REFRESH_LOCK_NAME = 'mattin-auth-refresh';
// The refresh runs while holding a lock shared by every tab, so it must always
// settle: a request left hanging (e.g. the backend restarting mid-request) would
// otherwise block session renewal in all other tabs.
const REFRESH_TIMEOUT_MS = 15_000;

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

  private oidcRenewHandler: OidcRenewHandler | null = null;
  private sessionExpiredListeners = new Set<SessionExpiredListener>();
  private refreshPromise: Promise<boolean> | null = null;

  /** Registered by OIDCProvider so non-React callers (api.ts) can trigger a token renewal. */
  setOidcRenewHandler(handler: OidcRenewHandler | null) {
    this.oidcRenewHandler = handler;
  }

  /** Resolves true when a fresh OIDC ID token is available. */
  async renewOidcSession(): Promise<boolean> {
    if (!this.oidcRenewHandler) return false;
    try {
      return await this.oidcRenewHandler();
    } catch {
      return false;
    }
  }

  onSessionExpired(listener: SessionExpiredListener): () => void {
    this.sessionExpiredListeners.add(listener);
    return () => {
      this.sessionExpiredListeners.delete(listener);
    };
  }

  /** Signals that the backend rejected the session and it could not be renewed. */
  notifySessionExpired() {
    this.sessionExpiredListeners.forEach(listener => listener());
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

  /**
   * Rotates the cookie pair (LOCAL mode). Concurrent callers share one in-flight
   * request, and the Web Locks API serialises rotation across tabs.
   */
  refresh(): Promise<boolean> {
    if (!this.refreshPromise) {
      const locks = typeof navigator === 'undefined' ? undefined : navigator.locks;
      const run = () => this.rotateRefreshToken();
      const pending = locks ? locks.request(REFRESH_LOCK_NAME, run) : run();
      this.refreshPromise = pending.finally(() => {
        this.refreshPromise = null;
      });
    }
    return this.refreshPromise;
  }

  private async rotateRefreshToken(): Promise<boolean> {
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
        signal: AbortSignal.timeout(REFRESH_TIMEOUT_MS),
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

  /** Resolves the backend session without throwing; the caller decides how to recover. */
  async fetchCurrentUser(): Promise<CurrentUserResult> {
    const headers: Record<string, string> = {};
    if (this.oidcAccessToken) {
      headers['Authorization'] = `Bearer ${this.oidcAccessToken}`;
    }

    try {
      const response = await fetch(`${this.baseURL}/internal/me`, {
        credentials: 'include',
        headers,
      });
      // 404: authenticated identity without a platform account — not usable either.
      if (response.status === 401 || response.status === 403 || response.status === 404) {
        return { status: 'unauthorized' };
      }
      if (!response.ok) {
        return { status: 'unavailable' };
      }
      return { status: 'ok', user: await response.json() };
    } catch {
      return { status: 'unavailable' };
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
