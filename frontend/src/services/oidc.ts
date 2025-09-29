import { getIdentityProviderByKey, getIdentityProviders, type IdentityProviderConfig } from '../config/identityProviders';

interface OidcTokens {
  accessToken: string;
  idToken: string;
  refreshToken?: string;
  scope?: string;
  expiresIn?: number;
  tokenType?: string;
  receivedAt: number;
}

export interface OidcSession {
  providerKey: string;
  tokens: OidcTokens;
  profile: Record<string, unknown>;
  userInfo?: Record<string, unknown>;
}

interface LoginRequest {
  providerKey: string;
  codeVerifier: string;
  state: string;
}

interface OidcMetadata {
  authorization_endpoint: string;
  token_endpoint: string;
  userinfo_endpoint?: string;
  end_session_endpoint?: string;
}

type SessionListener = (session: OidcSession | null) => void;

const LOGIN_REQUEST_STORAGE_KEY = 'oidc.login-request';

const metadataCache = new Map<string, OidcMetadata>();

function isBrowser() {
  return typeof window !== 'undefined';
}

function getLoginRequest(): LoginRequest | null {
  if (!isBrowser()) return null;

  const raw = sessionStorage.getItem(LOGIN_REQUEST_STORAGE_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as LoginRequest;
  } catch (error) {
    console.error('Failed to parse login request payload', error);
    sessionStorage.removeItem(LOGIN_REQUEST_STORAGE_KEY);
    return null;
  }
}

function persistLoginRequest(request: LoginRequest) {
  if (!isBrowser()) return;
  sessionStorage.setItem(LOGIN_REQUEST_STORAGE_KEY, JSON.stringify(request));
}

function clearLoginRequest() {
  if (!isBrowser()) return;
  sessionStorage.removeItem(LOGIN_REQUEST_STORAGE_KEY);
}

function decodeJwt(token: string): Record<string, unknown> {
  const [, payload] = token.split('.');
  if (!payload) {
    throw new Error('Invalid JWT received');
  }

  const padded = payload.replace(/-/g, '+').replace(/_/g, '/');
  const decoded = atob(padded.padEnd(padded.length + (4 - (padded.length % 4)) % 4, '='));
  return JSON.parse(decoded);
}

async function sha256(value: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  return crypto.subtle.digest('SHA-256', encoder.encode(value));
}

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function generateRandomString(length = 64): string {
  const charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  const randomValues = new Uint8Array(length);
  crypto.getRandomValues(randomValues);
  let result = '';
  randomValues.forEach((value) => {
    result += charset[value % charset.length];
  });
  return result;
}

async function createCodeChallenge(codeVerifier: string) {
  const hashed = await sha256(codeVerifier);
  return base64UrlEncode(hashed);
}

async function fetchMetadata(provider: IdentityProviderConfig): Promise<OidcMetadata> {
  if (metadataCache.has(provider.key)) {
    return metadataCache.get(provider.key)!;
  }

  const response = await fetch(`${provider.authority.replace(/\/$/, '')}/.well-known/openid-configuration`);
  if (!response.ok) {
    throw new Error(`Failed to fetch OIDC metadata for ${provider.name}`);
  }

  const metadata = await response.json() as OidcMetadata;
  metadataCache.set(provider.key, metadata);
  return metadata;
}

async function requestToken(provider: IdentityProviderConfig, metadata: OidcMetadata, code: string, codeVerifier: string) {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: provider.clientId,
    code,
    redirect_uri: provider.redirectUri,
    code_verifier: codeVerifier,
  });

  const response = await fetch(metadata.token_endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  });

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new Error(errorPayload.error_description || 'Failed to exchange authorization code');
  }

  return response.json();
}

async function requestUserInfo(metadata: OidcMetadata, accessToken: string) {
  if (!metadata.userinfo_endpoint) {
    return undefined;
  }

  const response = await fetch(metadata.userinfo_endpoint, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!response.ok) {
    console.warn('Failed to fetch userinfo payload');
    return undefined;
  }

  return response.json();
}

class OidcService {
  private session: OidcSession | null = null;
  private listeners: Set<SessionListener> = new Set();

  getAvailableProviders() {
    return getIdentityProviders();
  }

  subscribe(listener: SessionListener) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(session: OidcSession | null) {
    for (const listener of this.listeners) {
      listener(session);
    }
  }

  getSession() {
    return this.session;
  }

  isAuthenticated() {
    if (!this.session) {
      return false;
    }

    const { expiresIn, receivedAt } = this.session.tokens;
    if (!expiresIn) {
      return true;
    }

    const expiresAt = receivedAt + expiresIn * 1000;
    return Date.now() < expiresAt;
  }

  async startLogin(providerKey: string) {
    const provider = getIdentityProviderByKey(providerKey);
    if (!provider) {
      throw new Error('Unsupported identity provider selected');
    }

    const metadata = await fetchMetadata(provider);
    const state = generateRandomString(32);
    const codeVerifier = generateRandomString(64);
    const codeChallenge = await createCodeChallenge(codeVerifier);

    persistLoginRequest({ providerKey, codeVerifier, state });

    const params = new URLSearchParams({
      client_id: provider.clientId,
      redirect_uri: provider.redirectUri,
      response_type: 'code',
      scope: provider.scope,
      state,
      code_challenge: codeChallenge,
      code_challenge_method: 'S256',
    });

    if (provider.extraAuthorizeParams) {
      Object.entries(provider.extraAuthorizeParams).forEach(([key, value]) => {
        if (value) {
          params.append(key, value);
        }
      });
    }

    window.location.href = `${metadata.authorization_endpoint}?${params.toString()}`;
  }

  async handleAuthCallback(url: string = window.location.href): Promise<OidcSession> {
    const parsedUrl = new URL(url);
    const error = parsedUrl.searchParams.get('error');
    if (error) {
      throw new Error(parsedUrl.searchParams.get('error_description') || error);
    }

    const code = parsedUrl.searchParams.get('code');
    const state = parsedUrl.searchParams.get('state');
    if (!code || !state) {
      throw new Error('Authorization code response is missing expected parameters');
    }

    const loginRequest = getLoginRequest();
    if (!loginRequest || loginRequest.state !== state) {
      throw new Error('Login request information not found or state mismatch');
    }

    clearLoginRequest();

    const provider = getIdentityProviderByKey(loginRequest.providerKey);
    if (!provider) {
      throw new Error('Unknown identity provider referenced in callback');
    }

    const metadata = await fetchMetadata(provider);
    const tokenResponse = await requestToken(provider, metadata, code, loginRequest.codeVerifier);

    const tokens: OidcTokens = {
      accessToken: tokenResponse.access_token,
      idToken: tokenResponse.id_token,
      refreshToken: tokenResponse.refresh_token,
      scope: tokenResponse.scope,
      expiresIn: tokenResponse.expires_in,
      tokenType: tokenResponse.token_type,
      receivedAt: Date.now(),
    };

    if (!tokens.idToken || !tokens.accessToken) {
      throw new Error('Token response is missing expected fields');
    }

    const profile = decodeJwt(tokens.idToken);
    const userInfo = await requestUserInfo(metadata, tokens.accessToken);

    this.session = {
      providerKey: provider.key,
      tokens,
      profile: profile ?? {},
      userInfo,
    };

    this.notify(this.session);

    return this.session;
  }

  async logout() {
    if (!this.session) {
      window.location.href = '/login';
      return;
    }

    const provider = getIdentityProviderByKey(this.session.providerKey);
    if (!provider) {
      this.clearSession();
      window.location.href = '/login';
      return;
    }

    const metadata = await fetchMetadata(provider).catch(() => null);

    const postLogoutRedirect = provider.postLogoutRedirectUri || `${window.location.origin}/login`;
    const idTokenHint = this.session.tokens.idToken;

    this.clearSession();

    if (metadata?.end_session_endpoint) {
      const params = new URLSearchParams({
        post_logout_redirect_uri: postLogoutRedirect,
      });

      if (idTokenHint) {
        params.append('id_token_hint', idTokenHint);
      }

      if (provider.clientId) {
        params.append('client_id', provider.clientId);
      }

      window.location.href = `${metadata.end_session_endpoint}?${params.toString()}`;
      return;
    }

    if (provider.logoutUrl) {
      const logoutUrl = new URL(provider.logoutUrl);
      logoutUrl.searchParams.set('continue', postLogoutRedirect);
      window.location.href = logoutUrl.toString();
      return;
    }

    window.location.href = postLogoutRedirect;
  }

  clearSession() {
    this.session = null;
    this.notify(null);
  }
}

export const oidcService = new OidcService();
