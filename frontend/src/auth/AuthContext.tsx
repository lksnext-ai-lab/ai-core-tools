import { useContext } from 'react';
import { OIDCContext } from './OIDCProvider';
import { useUser } from '../contexts/UserContext';

/**
 * Authentication state for route guards. A session counts as authenticated only
 * once the backend has accepted it (UserContext), never from a stored IdP token alone.
 */
export const useAuth = () => {
  const oidcContext = useContext(OIDCContext);
  const userContext = useUser();

  return {
    user: userContext.user,
    isAuthenticated: userContext.user !== null,
    loading: userContext.loading,
    sessionError: userContext.sessionError,
    login: oidcContext?.login ?? (async () => { /* LOCAL mode signs in through the login form */ }),
    logout: userContext.logout,
  };
};
