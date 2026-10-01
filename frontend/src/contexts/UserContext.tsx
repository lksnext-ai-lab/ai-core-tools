import React, { createContext, useContext, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import type { ReactNode } from 'react';
import { authService, type CurrentUserPayload } from '../services/auth';
import { OIDCContext } from '../auth/OIDCProvider';
import { resolveCurrentUser } from '../auth/resolveCurrentUser';

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

/** `unavailable`: the backend could not be reached, so the session state is unknown. */
export type SessionError = 'unavailable';

interface UserContextType {
  user: User | null;
  /** True until the backend has confirmed (or rejected) the session. */
  loading: boolean;
  sessionError: SessionError | null;
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

function toUser(payload: CurrentUserPayload): User {
  return {
    user_id: payload.user_id,
    email: payload.email,
    name: payload.name,
    is_authenticated: true,
    is_admin: payload.is_admin ?? payload.is_omniadmin ?? false,
    is_omniadmin: payload.is_omniadmin ?? false,
    platform_role: payload.platform_role,
    is_editor: (payload.is_admin ?? false) || payload.platform_role !== 'viewer',
  };
}

export const UserProvider: React.FC<UserProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [resolving, setResolving] = useState(true);
  const [resolvedIdentity, setResolvedIdentity] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<SessionError | null>(null);
  const requestIdRef = useRef(0);

  const oidcContext = useContext(OIDCContext);
  const isOidc = oidcContext !== undefined;
  const oidcLoading = oidcContext?.loading ?? false;
  const oidcAuthenticated = oidcContext?.isAuthenticated ?? false;
  // Keyed on the subject, not the User object, so token renewals don't re-resolve.
  const oidcSubject = oidcContext?.user?.profile.sub ?? null;
  const oidcRenew = oidcContext?.renew;
  const oidcEndSession = oidcContext?.endSession;
  const oidcLogout = oidcContext?.logout;
  // Identity the current `user` belongs to; a mismatch means it is still being resolved.
  const identity = isOidc ? `oidc:${oidcAuthenticated ? oidcSubject : 'anonymous'}` : 'local';

  const resolveUser = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setResolving(true);

    try {
      const result = await resolveCurrentUser({
        fetchCurrentUser: () => authService.fetchCurrentUser(),
        renewSession: () => (oidcRenew ? oidcRenew() : authService.refresh()),
      });
      if (requestId !== requestIdRef.current) return;

      if (result.status === 'ok') {
        setUser(toUser(result.user));
        setSessionError(null);
        return;
      }

      setUser(null);
      if (result.status === 'unavailable') {
        setSessionError('unavailable');
        return;
      }
      setSessionError(null);
      if (oidcEndSession) {
        // The IdP session exists but the backend rejects it even after renewal.
        await oidcEndSession();
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setResolving(false);
        setResolvedIdentity(identity);
      }
    }
  }, [oidcRenew, oidcEndSession, identity]);

  useEffect(() => {
    if (oidcLoading) return;

    if (isOidc && !oidcAuthenticated) {
      requestIdRef.current++;
      setUser(null);
      setSessionError(null);
      setResolving(false);
      setResolvedIdentity(identity);
      return;
    }

    void resolveUser();
    return () => {
      requestIdRef.current++;
    };
  }, [isOidc, oidcLoading, oidcAuthenticated, identity, resolveUser]);

  useEffect(() => {
    return authService.onSessionExpired(() => {
      requestIdRef.current++;
      setUser(null);
      if (oidcEndSession) {
        void oidcEndSession();
      }
    });
  }, [oidcEndSession]);

  const refreshUser = useCallback(() => resolveUser(), [resolveUser]);

  const logout = useCallback(async () => {
    requestIdRef.current++;
    if (oidcLogout) {
      await oidcLogout();
    } else {
      await authService.logout();
    }
    setUser(null);
  }, [oidcLogout]);

  const loading = oidcLoading || resolving || resolvedIdentity !== identity;

  const value: UserContextType = useMemo(
    () => ({
      user,
      loading,
      sessionError,
      setUser,
      logout,
      refreshUser,
    }),
    [user, loading, sessionError, logout, refreshUser],
  );

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
};
