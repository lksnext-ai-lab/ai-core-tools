import React, { createContext, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import type { AuthConfig } from '../core/types';
import { UserManager, User, WebStorageStateStore, ErrorResponse, type UserManagerSettings } from 'oidc-client-ts';
import { authService } from '../services/auth';
import { buildOidcScope, getSessionExpiresAt, isAuthCallback, isSessionUsable, sanitizeReturnPath } from './oidcSession';

interface OIDCContextType {
  user: User | null;
  login: (returnTo?: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Renews tokens silently; resolves true when a usable session is available. */
  renew: () => Promise<boolean>;
  /** Drops the local session without contacting the identity provider. */
  endSession: () => Promise<void>;
  isAuthenticated: boolean;
  loading: boolean;
  /** Path requested before the sign-in redirect, available after the callback. */
  returnTo: string | null;
}

export const OIDCContext = createContext<OIDCContextType | undefined>(undefined);

interface OIDCProviderProps {
  config: AuthConfig;
  children: React.ReactNode;
}

const RENEW_BEFORE_EXPIRY_SECONDS = 60;

// Errors meaning the IdP session is gone and only an interactive sign-in can recover it.
const SESSION_ENDED_ERRORS = new Set([
  'login_required',
  'interaction_required',
  'consent_required',
  'account_selection_required',
  'invalid_grant',
]);

function isSessionEndedError(error: unknown): boolean {
  return error instanceof ErrorResponse && SESSION_ENDED_ERRORS.has(error.error ?? '');
}

export const OIDCProvider: React.FC<OIDCProviderProps> = ({ config, children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [returnTo, setReturnTo] = useState<string | null>(null);
  const initializedRef = useRef(false);
  const renewPromiseRef = useRef<Promise<boolean> | null>(null);

  const oidc = config.type === 'oidc' && config.oidc?.enabled ? config.oidc : undefined;
  const authority = oidc?.authority;
  const clientId = oidc?.clientId;
  const redirectUri = oidc?.redirectUri;
  const scope = oidc?.scope;
  const audience = oidc?.audience;

  const userManager = useMemo(() => {
    if (!authority || !clientId || !redirectUri) return null;

    const settings: UserManagerSettings = {
      authority,
      client_id: clientId,
      redirect_uri: redirectUri,
      response_type: 'code',
      response_mode: 'query',
      scope: buildOidcScope(scope, audience),
      userStore: new WebStorageStateStore({ store: globalThis.localStorage }),
      silent_redirect_uri: `${globalThis.location.origin}/silent-renew.html`,
      post_logout_redirect_uri: globalThis.location.origin,
      // Renewal is scheduled here against the ID token expiry: the backend
      // authenticates with the ID token, whose lifetime differs from the access token's.
      automaticSilentRenew: false,
      // Entra ID publishes no check_session_iframe, and session iframes break
      // under third-party cookie blocking.
      monitorSession: false,
      includeIdTokenInSilentRenew: true,
    };
    return new UserManager(settings);
  }, [authority, clientId, redirectUri, scope, audience]);

  const applyUser = useCallback((next: User | null) => {
    if (next) {
      authService.setOIDCToken(next);
    } else {
      authService.clearAuth();
    }
    setUser(next);
  }, []);

  const renew = useCallback((): Promise<boolean> => {
    if (!userManager) return Promise.resolve(false);
    if (!renewPromiseRef.current) {
      renewPromiseRef.current = userManager.signinSilent()
        .then(renewed => isSessionUsable(renewed))
        .catch(async (error: unknown) => {
          console.warn('OIDC silent renewal failed:', error);
          if (isSessionEndedError(error)) {
            await userManager.removeUser();
          }
          return false;
        })
        .finally(() => {
          renewPromiseRef.current = null;
        });
    }
    return renewPromiseRef.current;
  }, [userManager]);

  const endSession = useCallback(async () => {
    if (userManager) {
      await userManager.removeUser();
    }
    applyUser(null);
  }, [userManager, applyUser]);

  // One-time bootstrap: process the redirect callback or restore the stored
  // session, renewing it before reporting "authenticated" when it has expired.
  useEffect(() => {
    if (!userManager) {
      setLoading(false);
      return;
    }
    if (initializedRef.current) return;
    initializedRef.current = true;

    const bootstrap = async () => {
      try {
        let current: User | null;
        if (isAuthCallback(globalThis.location, redirectUri)) {
          current = await userManager.signinRedirectCallback();
          const state = current.state as { returnTo?: unknown } | undefined;
          setReturnTo(sanitizeReturnPath(state?.returnTo));
          globalThis.history.replaceState(globalThis.history.state, '', globalThis.location.pathname);
        } else {
          current = await userManager.getUser();
        }

        if (current && !isSessionUsable(current)) {
          const renewed = await renew();
          current = renewed ? await userManager.getUser() : null;
        }

        if (!current) {
          await userManager.removeUser();
        }
        applyUser(current);
      } catch (error) {
        console.error('OIDC session bootstrap failed:', error);
        await userManager.removeUser().catch(() => {});
        applyUser(null);
      } finally {
        setLoading(false);
      }
    };

    void bootstrap();
  }, [userManager, redirectUri, renew, applyUser]);

  useEffect(() => {
    if (!userManager) return;

    const onUserLoaded = (loaded: User) => applyUser(loaded);
    const onUserUnloaded = () => applyUser(null);

    // Keeps tabs in sync: another tab renewing or signing out rewrites the shared store.
    const onStorage = (event: StorageEvent) => {
      if (event.storageArea !== globalThis.localStorage || !event.key?.startsWith('oidc.user:')) return;
      userManager.getUser()
        .then(stored => applyUser(isSessionUsable(stored) ? stored : null))
        .catch(() => applyUser(null));
    };

    userManager.events.addUserLoaded(onUserLoaded);
    userManager.events.addUserUnloaded(onUserUnloaded);
    globalThis.addEventListener('storage', onStorage);
    authService.setOidcRenewHandler(renew);

    return () => {
      userManager.events.removeUserLoaded(onUserLoaded);
      userManager.events.removeUserUnloaded(onUserUnloaded);
      globalThis.removeEventListener('storage', onStorage);
      authService.setOidcRenewHandler(null);
    };
  }, [userManager, renew, applyUser]);

  // Renews ahead of expiry. Background tabs throttle timers, so the check also
  // runs when the tab becomes visible again.
  useEffect(() => {
    const expiresAt = getSessionExpiresAt(user);
    if (!userManager || expiresAt === undefined) return;

    const renewIfDue = () => {
      const secondsLeft = expiresAt - Date.now() / 1000;
      if (secondsLeft <= RENEW_BEFORE_EXPIRY_SECONDS) {
        void renew();
      }
    };

    const delayMs = Math.max(0, (expiresAt - RENEW_BEFORE_EXPIRY_SECONDS) * 1000 - Date.now());
    const timer = globalThis.setTimeout(() => void renew(), delayMs);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') renewIfDue();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      globalThis.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [user, userManager, renew]);

  const login = useCallback(async (requestedPath?: string) => {
    if (!userManager) return;
    await userManager.signinRedirect({ state: { returnTo: sanitizeReturnPath(requestedPath) } });
  }, [userManager]);

  const logout = useCallback(async () => {
    if (!userManager) return;
    authService.clearAuth();
    await userManager.signoutRedirect();
  }, [userManager]);

  const isAuthenticated = isSessionUsable(user);

  const contextValue = useMemo(() => ({
    user,
    login,
    logout,
    renew,
    endSession,
    isAuthenticated,
    loading,
    returnTo,
  }), [user, login, logout, renew, endSession, isAuthenticated, loading, returnTo]);

  return (
    <OIDCContext.Provider value={contextValue}>
      {children}
    </OIDCContext.Provider>
  );
};
