import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react';
import type { ReactNode } from 'react';
import { authService } from '../services/auth';
import { OIDCContext } from '../auth/OIDCProvider';
import { configService } from '../core/ConfigService';

export interface User {
  user_id: number;
  email: string;
  name?: string;
  is_authenticated: boolean;
  is_admin?: boolean;
  is_omniadmin?: boolean;
  platform_role?: 'viewer' | 'editor' | 'admin';
  /** True for editors and admins; false for viewers */
  is_editor?: boolean;
}

interface UserContextType {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

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

async function fetchUserFromBackend(
  bearerToken: string | null,
): Promise<User | null> {
  const baseUrl = configService.getApiBaseUrl();
  const headers: Record<string, string> = {};

  if (bearerToken) {
    headers['Authorization'] = `Bearer ${bearerToken}`;
  }

  try {
    const response = await fetch(`${baseUrl}/internal/me`, {
      credentials: 'include',
      headers,
    });

    if (!response.ok) return null;

    const userData: {
      user_id: number;
      email: string;
      name?: string;
      is_admin?: boolean;
      is_omniadmin?: boolean;
      platform_role?: 'viewer' | 'editor' | 'admin';
    } = await response.json();

    return {
      user_id: userData.user_id,
      email: userData.email,
      name: userData.name,
      is_authenticated: true,
      is_admin: userData.is_admin ?? userData.is_omniadmin ?? false,
      is_omniadmin: userData.is_omniadmin ?? false,
      platform_role: userData.platform_role,
      is_editor: (userData.is_admin ?? false) || userData.platform_role !== 'viewer',
    };
  } catch {
    return null;
  }
}

export const UserProvider: React.FC<UserProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const oidcContext = useContext(OIDCContext);

  const refreshUser = useCallback(async () => {
    try {
      if (oidcContext?.user) {
        const token = oidcContext.user.id_token ?? null;
        const resolved = await fetchUserFromBackend(token);

        if (resolved) {
          setUser(resolved);
          return;
        }

        // Backend unreachable — fall back to OIDC profile fields.
        const oidcUser = oidcContext.user;
        setUser({
          user_id: 0,
          email: (oidcUser.profile as Record<string, string>)?.email ?? '',
          name: (oidcUser.profile as Record<string, string>)?.name
            ?? (oidcUser.profile as Record<string, string>)?.preferred_username,
          is_authenticated: true,
          is_admin: false,
          is_omniadmin: false,
          platform_role: 'viewer',
          is_editor: false,
        });
      } else {
        // LOCAL mode: httpOnly cookie sent automatically; no bearer needed.
        const resolved = await fetchUserFromBackend(null);
        setUser(resolved);
      }
    } catch {
      setUser(null);
    }
  }, [oidcContext?.user]);

  const logout = useCallback(async () => {
    if (oidcContext?.user) {
      await oidcContext.logout();
    } else {
      await authService.logout();
    }
    setUser(null);
  }, [oidcContext?.user, oidcContext?.logout]);

  useEffect(() => {
    const initializeUser = async () => {
      try {
        if (oidcContext?.user) {
          const token = oidcContext.user.id_token ?? null;
          const resolved = await fetchUserFromBackend(token);

          if (resolved) {
            setUser(resolved);
            setLoading(false);
            return;
          }

          // Backend unreachable — fall back to OIDC profile fields.
          const oidcUser = oidcContext.user;
          setUser({
            user_id: 0,
            email: (oidcUser.profile as Record<string, string>)?.email ?? '',
            name: (oidcUser.profile as Record<string, string>)?.name
              ?? (oidcUser.profile as Record<string, string>)?.preferred_username,
            is_authenticated: true,
            is_admin: false,
            is_omniadmin: false,
            platform_role: 'viewer',
            is_editor: false,
          });
        } else {
          const resolved = await fetchUserFromBackend(null);
          setUser(resolved);
        }
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    if (!oidcContext?.loading) {
      initializeUser();
    }
  }, [oidcContext?.user, oidcContext?.loading]);

  // Mirrors OIDC loading to prevent auth-flash during callback or silent-renew.
  useEffect(() => {
    if (oidcContext) {
      setLoading(oidcContext.loading);
    }
  }, [oidcContext?.loading]);

  const value: UserContextType = useMemo(
    () => ({
      user,
      loading,
      setUser,
      logout,
      refreshUser,
    }),
    [user, loading, logout, refreshUser],
  );

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
};
