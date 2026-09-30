import { describe, expect, it } from 'vitest';
import {
  buildOidcScope,
  getSessionExpiresAt,
  isAuthCallback,
  isSessionUsable,
  sanitizeReturnPath,
} from '../oidcSession';

const NOW = 1_700_000_000;

function session(expiresAt: number | undefined, idTokenExp: number | undefined) {
  return {
    expires_at: expiresAt,
    profile: { sub: 'user-1', iss: 'issuer', aud: 'client', exp: idTokenExp, iat: NOW - 3600 },
  } as Parameters<typeof isSessionUsable>[0];
}

describe('getSessionExpiresAt', () => {
  it('uses the ID token expiry when it ends before the access token', () => {
    expect(getSessionExpiresAt(session(NOW + 5400, NOW + 3600))).toBe(NOW + 3600);
  });

  it('uses the access token expiry when it ends first', () => {
    expect(getSessionExpiresAt(session(NOW + 600, NOW + 3600))).toBe(NOW + 600);
  });

  it('returns undefined without expiry information', () => {
    expect(getSessionExpiresAt(session(undefined, undefined))).toBeUndefined();
    expect(getSessionExpiresAt(null)).toBeUndefined();
  });
});

describe('isSessionUsable', () => {
  it('rejects a stored session whose ID token expired while the access token is still valid', () => {
    expect(isSessionUsable(session(NOW + 1800, NOW - 10), NOW)).toBe(false);
  });

  it('rejects tokens within the clock-skew window', () => {
    expect(isSessionUsable(session(NOW + 3, NOW + 3600), NOW)).toBe(false);
  });

  it('accepts a session with both tokens valid', () => {
    expect(isSessionUsable(session(NOW + 3600, NOW + 3600), NOW)).toBe(true);
  });

  it('rejects a missing session', () => {
    expect(isSessionUsable(null, NOW)).toBe(false);
  });
});

describe('buildOidcScope', () => {
  it('adds offline_access to the default scope', () => {
    expect(buildOidcScope(undefined, undefined)).toBe('openid profile email offline_access');
  });

  it('does not duplicate offline_access', () => {
    expect(buildOidcScope('openid offline_access', undefined)).toBe('openid offline_access');
  });

  it('requests the API default scope when an audience is configured', () => {
    expect(buildOidcScope('openid', 'api://client')).toBe('api://client/.default openid profile email offline_access');
  });
});

describe('isAuthCallback', () => {
  const origin = 'https://mattin.example.com';
  const redirectUri = `${origin}/auth/success`;

  it('detects an authorization response on the redirect URI', () => {
    expect(isAuthCallback({ origin, pathname: '/auth/success', search: '?code=abc&state=xyz' }, redirectUri)).toBe(true);
  });

  it('detects an error response on the redirect URI', () => {
    expect(isAuthCallback({ origin, pathname: '/auth/success', search: '?error=access_denied&state=xyz' }, redirectUri)).toBe(true);
  });

  it('ignores application pages that happen to carry a state parameter', () => {
    expect(isAuthCallback({ origin, pathname: '/apps/1/agents', search: '?state=draft' }, redirectUri)).toBe(false);
  });

  it('ignores the redirect URI without authorization parameters', () => {
    expect(isAuthCallback({ origin, pathname: '/auth/success', search: '' }, redirectUri)).toBe(false);
  });
});

describe('sanitizeReturnPath', () => {
  it('keeps same-origin paths with query strings', () => {
    expect(sanitizeReturnPath('/apps/3/agents?tab=1')).toBe('/apps/3/agents?tab=1');
  });

  it.each(['https://evil.example.com', '//evil.example.com', '/\\evil.example.com', 'apps', 42, undefined])(
    'rejects %s',
    value => {
      expect(sanitizeReturnPath(value)).toBeNull();
    },
  );
});
