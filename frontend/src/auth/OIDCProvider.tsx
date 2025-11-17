import React, { createContext, useState, useEffect, useMemo } from 'react';
import type { AuthConfig } from '../core/types';
import { UserManager, User, WebStorageStateStore } from 'oidc-client-ts';
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
      // Clear any legacy auth tokens from localStorage when using OIDC
      // This prevents stale tokens from causing issues
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_expires');

      const managerConfig: any = {
        authority: config.oidc.authority,
        client_id: config.oidc.clientId,
        redirect_uri: config.oidc.redirectUri,
        response_type: 'code',
        automaticSilentRenew: true,
        // Use localStorage instead of sessionStorage for cross-tab authentication
        userStore: new WebStorageStateStore({ store: globalThis.localStorage }),
        // Silent renewal configuration
        silent_redirect_uri: `${globalThis.location.origin}/silent-renew.html`,
        // Logout configuration
        post_logout_redirect_uri: globalThis.location.origin,
        // Additional settings for better token refresh
        accessTokenExpiringNotificationTimeInSeconds: 60,
        includeIdTokenInSilentRenew: true,
        monitorSession: true,
        checkSessionIntervalInSeconds: 2,
        // PKCE for enhanced security
        response_mode: 'query'
      };

      // Build scope with audience
      // For Azure AD, the audience should be included as part of the scope
      let scope = config.oidc.scope || 'openid profile email';
      if (config.oidc.audience) {
        // Add the audience as a scope with /.default suffix for Azure AD
        scope = `${config.oidc.audience}/.default openid profile email`;
      }
      managerConfig.scope = scope;

      const manager = new UserManager(managerConfig);

      setUserManager(manager);

      // Check if we're on the callback page
      const isCallback = globalThis.location.pathname === '/auth/success' || 
                        globalThis.location.search.includes('code=') || 
                        globalThis.location.search.includes('state=');
      
      if (isCallback) {
        console.log('Detected OIDC callback, processing...');
        // Process the callback
        manager.signinRedirectCallback()
          .then(user => {
            console.log('Callback processed successfully:', user);
            setUser(user);
            authService.setOIDCToken(user);
            setLoading(false);
          })
          .catch(err => {
            console.error('Callback processing failed:', err);
            setLoading(false);
          });
      } else {
        // Normal page load - check for existing user
        console.log('Checking for existing OIDC user...');
        manager.getUser()
          .then(user => {
            console.log('OIDC getUser result:', user ? 'User found' : 'No user');
            setUser(user);
            if (user) {
              authService.setOIDCToken(user);
            } else {
              // No OIDC user, clear any stale tokens
              authService.clearAuth();
            }
            setLoading(false);
          })
          .catch(err => {
            console.error('Error getting OIDC user:', err);
            setUser(null);
            authService.clearAuth();
            setLoading(false);
          });
      }

      // Token loaded event (after login or silent renewal)
      manager.events.addUserLoaded(user => {
        console.log('User token loaded/refreshed');
        setUser(user);
        authService.setOIDCToken(user);
      });

      // Token unloaded event
      manager.events.addUserUnloaded(() => {
        console.log('User token unloaded');
        setUser(null);
        authService.clearAuth();
      });

      // Token expiring event (triggered before expiration)
      manager.events.addAccessTokenExpiring(() => {
        console.log('Access token expiring, attempting silent renewal...');
      });

      // Token expired event
      manager.events.addAccessTokenExpired(() => {
        console.log('Access token expired');
        authService.clearAuth();
        // Attempt silent renewal
        manager.signinSilent().catch(err => {
          console.error('Silent renewal failed:', err);
          setUser(null);
        });
      });

      // Silent renewal error event
      manager.events.addSilentRenewError((error) => {
        console.error('Silent renewal error:', error);
        // Clear auth and potentially redirect to login
        authService.clearAuth();
        setUser(null);
      });

      // User signed out event
      manager.events.addUserSignedOut(() => {
        console.log('User signed out');
        authService.clearAuth();
        setUser(null);
      });

      // Cleanup function
      return () => {
        manager.events.removeUserLoaded(() => {});
        manager.events.removeUserUnloaded(() => {});
        manager.events.removeAccessTokenExpiring(() => {});
        manager.events.removeAccessTokenExpired(() => {});
        manager.events.removeSilentRenewError(() => {});
        manager.events.removeUserSignedOut(() => {});
      };
    } else {
      // Use existing session-based auth
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
