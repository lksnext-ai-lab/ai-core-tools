import React, { createContext, useState, useEffect, useMemo } from 'react';
import type { AuthConfig } from '../core/types';
import { UserManager, User } from 'oidc-client-ts';

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
      const manager = new UserManager({
        authority: config.oidc.authority,
        client_id: config.oidc.clientId,
        redirect_uri: config.oidc.redirectUri,
        scope: config.oidc.scope || 'openid profile email',
        response_type: 'code',
        automaticSilentRenew: true
      });

      setUserManager(manager);

      manager.getUser().then(user => {
        setUser(user);
        setLoading(false);
      });

      manager.events.addUserLoaded(user => setUser(user));
      manager.events.addUserUnloaded(() => setUser(null));
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
