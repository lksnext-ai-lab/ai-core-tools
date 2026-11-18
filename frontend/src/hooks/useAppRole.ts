import { useState, useEffect, useContext } from 'react';
import { apiService } from '../services/api';
import { AppRole } from '../types/roles';
import { hasMinRole } from '../utils/roleUtils';
import { AppRoleContext } from '../contexts/AppRoleContext';

/**
 * Hook to check if the current user is the owner of an app
 * Returns { isOwner, userRole, loading, hasMinRole }
 */
export function useAppRole(appId: string | undefined) {
  const sharedRole = useContext(AppRoleContext);
  const useSharedRole = appId !== undefined && sharedRole?.appId === appId;
  const [roleState, setRoleState] = useState<{
    appId: string | undefined;
    userRole: AppRole;
    loading: boolean;
  }>({ appId: undefined, userRole: AppRole.GUEST, loading: true });

  useEffect(() => {
    let active = true;

    async function fetchAppRole() {
      if (useSharedRole) return;

      if (!appId) {
        setRoleState({ appId, userRole: AppRole.GUEST, loading: false });
        return;
      }

      setRoleState({ appId, userRole: AppRole.GUEST, loading: true });
      try {
        const app = await apiService.getApp(Number.parseInt(appId));
        // Cast the string from API to AppRole, defaulting to GUEST if invalid
        const role = Object.values(AppRole).includes(app.user_role as AppRole) 
          ? (app.user_role as AppRole) 
          : AppRole.GUEST;
        if (active) setRoleState({ appId, userRole: role, loading: false });
      } catch (err) {
        console.error('Error fetching app role:', err);
        if (active) setRoleState({ appId, userRole: AppRole.GUEST, loading: false });
      }
    }

    void fetchAppRole();
    return () => {
      active = false;
    };
  }, [appId, useSharedRole]);

  // Avoid briefly exposing the previous app's role while a new app is loading.
  const localRole = roleState.appId === appId ? roleState.userRole : AppRole.GUEST;
  const localLoading = appId !== undefined && (
    roleState.appId !== appId || roleState.loading
  );
  const currentRole = useSharedRole
    ? sharedRole?.userRole ?? AppRole.GUEST
    : localRole;
  const loading = useSharedRole
    ? sharedRole?.loading ?? true
    : localLoading;

  return {
    // Backward compatibility
    isOwner: hasMinRole(currentRole, AppRole.OWNER),
    isAdmin: hasMinRole(currentRole, AppRole.ADMINISTRATOR),
    // New extensible properties
    userRole: currentRole,
    loading,
    hasMinRole: (role: AppRole) => hasMinRole(currentRole, role)
  };
}



