import React, { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { oidcService, type OidcSession } from '../services/oidc';

export interface UserProfile {
  user_id: string;
  email?: string;
  name?: string;
  preferred_username?: string;
  picture?: string;
  providerKey: string;
  accessToken: string;
  idToken: string;
  rawProfile: Record<string, unknown>;
  userInfo?: Record<string, unknown>;
  is_authenticated: boolean;
  is_admin?: boolean;
}

interface UserContextType {
  user: UserProfile | null;
  loading: boolean;
  logout: () => Promise<void>;
  refreshUser: () => void;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

const deriveUser = (session: OidcSession | null): UserProfile | null => {
  if (!session) {
    return null;
  }

  const profile = session.userInfo ?? session.profile;
  const email = (profile?.email as string | undefined) || (session.profile?.['email'] as string | undefined);
  const name = (profile?.name as string | undefined) || (session.profile?.['name'] as string | undefined);
  const preferredUsername = (profile?.preferred_username as string | undefined) ||
    (session.profile?.['preferred_username'] as string | undefined);
  const userId = (profile?.sub as string | undefined) || (session.profile?.['sub'] as string | undefined);

  if (!userId) {
    return null;
  }

  return {
    user_id: userId,
    email,
    name,
    preferred_username: preferredUsername,
    picture: (profile?.picture as string | undefined) || (session.profile?.['picture'] as string | undefined),
    providerKey: session.providerKey,
    accessToken: session.tokens.accessToken,
    idToken: session.tokens.idToken,
    rawProfile: session.profile,
    userInfo: session.userInfo,
    is_authenticated: true,
    is_admin: Boolean(profile?.['is_admin'] ?? session.profile?.['is_admin']),
  };
};

export const useUser = () => {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};

interface UserProviderProps {
  children: ReactNode;
}

export const UserProvider: React.FC<UserProviderProps> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(() => deriveUser(oidcService.getSession()));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = oidcService.subscribe((session) => {
      setUser(deriveUser(session));
      setLoading(false);
    });

    setUser(deriveUser(oidcService.getSession()));
    setLoading(false);

    return () => {
      unsubscribe();
    };
  }, []);

  const logout = async () => {
    await oidcService.logout();
  };

  const refreshUser = () => {
    setUser(deriveUser(oidcService.getSession()));
  };

  const value: UserContextType = {
    user,
    loading,
    logout,
    refreshUser,
  };

  return (
    <UserContext.Provider value={value}>
      {children}
    </UserContext.Provider>
  );
};
