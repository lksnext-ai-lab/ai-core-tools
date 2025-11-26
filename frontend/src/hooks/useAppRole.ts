import { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import { AppRole } from '../types/roles';
import { hasMinRole } from '../utils/roleUtils';

/**
 * Hook to check if the current user is the owner of an app
 * Returns { isOwner, userRole, loading, hasMinRole }
 */
export function useAppRole(appId: string | undefined) {
  const [userRole, setUserRole] = useState<AppRole>(AppRole.GUEST);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAppRole() {
      if (!appId) {
        setLoading(false);
        return;
      }

      try {
        const app = await apiService.getApp(parseInt(appId));
        // Cast the string from API to AppRole, defaulting to GUEST if invalid
        const role = Object.values(AppRole).includes(app.user_role as AppRole) 
          ? (app.user_role as AppRole) 
          : AppRole.GUEST;
        setUserRole(role);
      } catch (err) {
        console.error('Error fetching app role:', err);
        setUserRole(AppRole.GUEST);
      } finally {
        setLoading(false);
      }
    }

    fetchAppRole();
  }, [appId]);

  return {
    // Backward compatibility
    isOwner: hasMinRole(userRole, AppRole.OWNER),
    isAdmin: hasMinRole(userRole, AppRole.ADMINISTRATOR),
    // New extensible properties
    userRole,
    loading,
    hasMinRole: (role: AppRole) => hasMinRole(userRole, role)
  };
}



