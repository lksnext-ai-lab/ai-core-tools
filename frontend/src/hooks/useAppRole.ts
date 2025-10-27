import { useState, useEffect } from 'react';
import { apiService } from '../services/api';

/**
 * Hook to check if the current user is the owner of an app
 * Returns { isOwner, userRole, loading }
 */
export function useAppRole(appId: string | undefined) {
  const [userRole, setUserRole] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAppRole() {
      if (!appId) {
        setLoading(false);
        return;
      }

      try {
        const app = await apiService.getApp(parseInt(appId));
        setUserRole(app.user_role || '');
      } catch (err) {
        console.error('Error fetching app role:', err);
        setUserRole('');
      } finally {
        setLoading(false);
      }
    }

    fetchAppRole();
  }, [appId]);

  return {
    isOwner: userRole === 'owner',
    isAdmin: userRole === 'owner' || userRole === 'administrator',
    userRole,
    loading
  };
}



