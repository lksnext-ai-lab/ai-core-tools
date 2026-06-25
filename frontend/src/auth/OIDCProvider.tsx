import React, { createContext, useState, useEffect, useMemo } from 'react';
import type { AuthConfig } from '../core/types';
import { UserManager, User, WebStorageStateStore, type UserManagerSettings } from 'oidc-client-ts';
import { authService } from '../services/auth';

interface OIDCContextType {
  user: User | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  isAuthenticated: boolean;
  loading: boolean;
}

export const OIDCContext = createContext<OIDCContextType | undefined>(undefined);

interface OIDCProviderProps {
  config: AuthConfig;
  children: React.ReactNode;
}

export const OIDCProvider: React.FC<OIDCProviderProps> = ({ config, children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [userManager, setUserManager] = useState<UserManager | null>(null);

  useEffect(() => {
    if (config.type === 'oidc' && config.oidc?.enabled) {

      const managerConfig: UserManagerSettings = {
        authority: config.oidc.authority,
        client_id: config.oidc.clientId,
        redirect_uri: config.oidc.redirectUri,
        response_type: 'code',
        automaticSilentRenew: true,
        userStore: new WebStorageStateStore({ store: globalThis.localStorage }),
        silent_redirect_uri: `${globalThis.location.origin}/silent-renew.html`,
        post_logout_redirect_uri: globalThis.location.origin,
        accessTokenExpiringNotificationTimeInSeconds: 60,
        includeIdTokenInSilentRenew: true,
        monitorSession: true,
        checkSessionIntervalInSeconds: 2,
        response_mode: 'query'
      };

      let scope = config.oidc.scope || 'openid profile email';
      if (config.oidc.audience) {
        // Azure AD requires audience as a scope with /.default suffix.
        scope = `${config.oidc.audience}/.default openid profile email`;
      }
      managerConfig.scope = scope;

      const manager = new UserManager(managerConfig);

      setUserManager(manager);

      const isCallback = globalThis.location.pathname === '/auth/success' ||
                        globalThis.location.search.includes('code=') ||
                        globalThis.location.search.includes('state=');

      if (isCallback) {
        manager.signinRedirectCallback()
          .then(user => {
            setUser(user);
            authService.setOIDCToken(user);
            setLoading(false);
          })
          .catch(err => {
            console.error('OIDC callback processing failed:', err);
            setLoading(false);
          });
      } else {
        manager.getUser()
          .then(user => {
            setUser(user);
            if (user) {
              authService.setOIDCToken(user);
            } else {
              authService.clearAuth();
            }
            setLoading(false);
          })
          .catch(err => {
            console.error('OIDC getUser failed:', err);
            setUser(null);
            authService.clearAuth();
            setLoading(false);
          });
      }

      // Named refs required — oidc-client-ts compares listeners by identity on removal.
      const onUserLoaded = (user: User) => {
        setUser(user);
        authService.setOIDCToken(user);
      };
      const onUserUnloaded = () => {
        setUser(null);
        authService.clearAuth();
      };
      const onAccessTokenExpiring = () => {
        // intentionally empty — automaticSilentRenew handles renewal
      };
      const onAccessTokenExpired = () => {
        authService.clearAuth();
        manager.signinSilent().catch(err => {
          console.error('OIDC silent renewal failed:', err);
          setUser(null);
        });
      };
      const onSilentRenewError = (error: Error) => {
        console.error('Silent renewal error:', error);
        authService.clearAuth();
        setUser(null);
      };
      const onUserSignedOut = () => {
        authService.clearAuth();
        setUser(null);
      };

      manager.events.addUserLoaded(onUserLoaded);
      manager.events.addUserUnloaded(onUserUnloaded);
      manager.events.addAccessTokenExpiring(onAccessTokenExpiring);
      manager.events.addAccessTokenExpired(onAccessTokenExpired);
      manager.events.addSilentRenewError(onSilentRenewError);
      manager.events.addUserSignedOut(onUserSignedOut);

      return () => {
        manager.events.removeUserLoaded(onUserLoaded);
        manager.events.removeUserUnloaded(onUserUnloaded);
        manager.events.removeAccessTokenExpiring(onAccessTokenExpiring);
        manager.events.removeAccessTokenExpired(onAccessTokenExpired);
        manager.events.removeSilentRenewError(onSilentRenewError);
        manager.events.removeUserSignedOut(onUserSignedOut);
      };
    } else {
      setLoading(false);
    }
  }, [config]);

  const login = async () => {
    if (userManager) {
      await userManager.signinRedirect();
    }
  };

  const logout = async () => {
    if (userManager) {
      authService.clearAuth();
      await userManager.signoutRedirect();
    }
  };

  const contextValue = useMemo(() => ({
    user,
    login,
    logout,
    isAuthenticated: !!user,
    loading
  }), [user, login, logout, loading]);

  return (
    <OIDCContext.Provider value={contextValue}>
      {children}
    </OIDCContext.Provider>
  );
};
