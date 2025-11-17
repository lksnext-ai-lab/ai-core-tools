import { useContext } from 'react';
import { OIDCContext } from './OIDCProvider';
import { useUser } from '../contexts/UserContext';

export const useAuth = () => {
  const oidcContext = useContext(OIDCContext);
  const userContext = useUser();

  // Return OIDC auth if available, otherwise session auth
  if (oidcContext) {
    return {
      user: oidcContext.user,
      isAuthenticated: oidcContext.isAuthenticated,
      login: oidcContext.login,
      logout: oidcContext.logout,
      loading: oidcContext.loading
    };
  }

  return {
    user: userContext.user,
    isAuthenticated: !!userContext.user,
    login: async () => { /* redirect to login */ },
    logout: userContext.logout,
    loading: userContext.loading
  };
};
