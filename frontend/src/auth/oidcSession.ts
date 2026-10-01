import type { User } from 'oidc-client-ts';

// Tolerates small clock skew between the browser and the identity provider.
const EXPIRY_SKEW_SECONDS = 5;

type SessionTokens = Pick<User, 'expires_at' | 'profile'>;

/**
 * Earliest expiry (epoch seconds) of the tokens the session depends on. The
 * backend authenticates with the ID token (profile.exp), whose lifetime differs
 * from the access token's (expires_at) in Entra ID.
 */
export function getSessionExpiresAt(user: SessionTokens | null | undefined): number | undefined {
  if (!user) return undefined;
  const candidates = [user.expires_at, user.profile?.exp].filter(
    (value): value is number => typeof value === 'number',
  );
  return candidates.length > 0 ? Math.min(...candidates) : undefined;
}

export function isSessionUsable(
  user: SessionTokens | null | undefined,
  nowSeconds: number = Date.now() / 1000,
): boolean {
  if (!user) return false;
  const expiresAt = getSessionExpiresAt(user);
  return expiresAt === undefined || expiresAt - EXPIRY_SKEW_SECONDS > nowSeconds;
}

/** Adds offline_access so Entra ID issues a refresh token and renewal avoids third-party-cookie iframes. */
export function buildOidcScope(scope: string | undefined, audience: string | undefined): string {
  const base = audience
    ? `${audience}/.default openid profile email`
    : scope || 'openid profile email';
  const scopes = base.split(/\s+/).filter(Boolean);
  if (!scopes.includes('offline_access')) {
    scopes.push('offline_access');
  }
  return scopes.join(' ');
}

/** True only on the redirect URI carrying an authorization response. */
export function isAuthCallback(
  location: Pick<Location, 'pathname' | 'search' | 'origin'>,
  redirectUri: string | undefined,
): boolean {
  if (!redirectUri) return false;
  let callbackPath: string;
  try {
    callbackPath = new URL(redirectUri, location.origin).pathname;
  } catch {
    return false;
  }
  if (location.pathname !== callbackPath) return false;
  const params = new URLSearchParams(location.search);
  return params.has('state') && (params.has('code') || params.has('error'));
}

/** Accepts only same-origin absolute paths to prevent open redirects. */
export function sanitizeReturnPath(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) return null;
  return value;
}
