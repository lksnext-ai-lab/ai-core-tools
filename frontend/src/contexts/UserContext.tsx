import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
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

export const UserProvider: React.FC<UserProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Access OIDC context directly to avoid circular dependency with useAuth
  const oidcContext = useContext(OIDCContext);

  const refreshUser = async () => {
    try {
      // If using OIDC, get user from backend
      if (oidcContext?.user) {
        try {
          const baseUrl = configService.getApiBaseUrl();
          const token = oidcContext.user.access_token;
          
          const response = await fetch(`${baseUrl}/internal/me`, {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          });
          
          if (response.ok) {
            const userData = await response.json();
            setUser({
              user_id: userData.user_id,
              email: userData.email,
              name: userData.name,
              is_authenticated: true,
              is_admin: userData.is_admin || userData.is_omniadmin,
              is_omniadmin: userData.is_omniadmin
            });
            return;
          }
        } catch (error) {
          console.error('Failed to fetch user from backend:', error);
        }
        
        // Fallback: use OIDC profile if backend call fails
        const oidcUser = oidcContext.user as any;
        const userData: User = {
          user_id: 0,
          email: oidcUser.profile?.email || '',
          name: oidcUser.profile?.name || oidcUser.profile?.preferred_username,
          is_authenticated: true,
          is_admin: false,
          is_omniadmin: false
        };
        setUser(userData);
      } else if (authService.isAuthenticated()) {
        // Dev mode: token exists, set a minimal authenticated user
        // Full user data will be set after login from the login response
        setUser({
          user_id: 0,
          email: '',
          name: '',
          is_authenticated: true,
          is_admin: false,
          is_omniadmin: false
        });
      } else {
        setUser(null);
      }
    } catch (error) {
      console.error('Failed to refresh user:', error);
      setUser(null);
    }
  };

  const logout = async () => {
    // If using OIDC, use OIDC logout
    if (oidcContext?.user) {
      await oidcContext.logout();
    } else {
      // Fake-login mode: just clear local storage
      authService.clearAuth();
    }
    setUser(null);
  };

  useEffect(() => {
    const initializeUser = async () => {
      try {
        // If using OIDC, get user from backend
        if (oidcContext?.user) {
          try {
            const baseUrl = configService.getApiBaseUrl();
            const token = oidcContext.user.access_token;
            
            const response = await fetch(`${baseUrl}/internal/me`, {
              headers: {
                'Authorization': `Bearer ${token}`
              }
            });
            
            if (response.ok) {
              const userData = await response.json();
              setUser({
                user_id: userData.user_id,
                email: userData.email,
                name: userData.name,
                is_authenticated: true,
                is_admin: userData.is_admin || userData.is_omniadmin,
                is_omniadmin: userData.is_omniadmin
              });
              setLoading(false);
              return;
            }
          } catch (error) {
            console.error('Failed to fetch user from backend:', error);
          }
          
          // Fallback: use OIDC profile if backend call fails
          const oidcUser = oidcContext.user as any;
          const userData: User = {
            user_id: 0,
            email: oidcUser.profile?.email || '',
            name: oidcUser.profile?.name || oidcUser.profile?.preferred_username,
            is_authenticated: true,
            is_admin: false,
            is_omniadmin: false
          };
          setUser(userData);
        } else if (authService.isAuthenticated()) {
          // Dev mode: token exists, set a minimal authenticated user
          // Full user data should have been set by login
          setUser({
            user_id: 0,
            email: '',
            name: '',
            is_authenticated: true,
            is_admin: false,
            is_omniadmin: false
          });
        } else {
          // No OIDC user and no token means not authenticated
          setUser(null);
        }
      } catch (error) {
        console.error('Failed to initialize user:', error);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    // Wait for auth to finish loading before initializing user
    if (!oidcContext?.loading) {
      initializeUser();
    }
  }, [oidcContext?.user, oidcContext?.loading]);

  // Update loading state based on OIDC loading
  useEffect(() => {
    if (oidcContext) {
      setLoading(oidcContext.loading);
    }
  }, [oidcContext?.loading]);

  const value: UserContextType = useMemo(() => ({
    user,
    loading,
    setUser,
    logout,
    refreshUser,
  }), [user, loading, logout, refreshUser]);

  return (
    <UserContext.Provider value={value}>
      {children}
    </UserContext.Provider>
  );
}; 