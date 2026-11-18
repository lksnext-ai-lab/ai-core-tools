import type { ReactNode } from 'react';
import { Navigate, useLocation, useParams } from 'react-router-dom';
import { AppRole } from '../types/roles';
import { useAppRole } from '../hooks/useAppRole';
import { AppRoleContext } from '../contexts/AppRoleContext';

export interface AppRoleRouteProps {
  readonly children: ReactNode;
  readonly requiredRole?: AppRole;
}

/**
 * App routes require a minimum effective app role. Page-level controls use the
 * same effective role for editor/admin actions; platform roles do not elevate
 * app permissions.
 */
export function AppRoleRoute({
  children,
  requiredRole = AppRole.VIEWER,
}: AppRoleRouteProps) {
  const { appId } = useParams();
  const { pathname } = useLocation();
  const { hasMinRole, loading, userRole } = useAppRole(appId);

  if (!appId) {
    // The top-level app list and non-app routes do not need an app role.
    // Any other /apps path is app-scoped and must fail closed without an ID.
    if (pathname !== '/apps' && pathname !== '/apps/' && pathname.startsWith('/apps/')) {
      return <Navigate to="/apps" state={{ appAccessDenied: true }} replace />;
    }
    return <>{children}</>;
  }

  if (loading) {
    return (
      <div
        className="flex min-h-[12rem] items-center justify-center bg-white text-gray-700 dark:bg-gray-900 dark:text-gray-200"
        role="status"
        aria-live="polite"
      >
        <span className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" aria-hidden="true" />
        <span className="sr-only">Checking app access…</span>
      </div>
    );
  }

  if (!hasMinRole(requiredRole)) {
    return <Navigate to="/apps" state={{ appAccessDenied: true }} replace />;
  }

  return (
    <AppRoleContext.Provider value={{ appId, userRole, loading }}>
      {children}
    </AppRoleContext.Provider>
  );
}
