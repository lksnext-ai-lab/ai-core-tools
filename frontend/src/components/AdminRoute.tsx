import React from 'react';
import { Navigate } from 'react-router-dom';
import { SessionGate } from './SessionGate';

interface AdminRouteProps {
  children: React.ReactNode;
}

/**
 * Requires a confirmed session with platform admin rights; other users go to the home page.
 * is_admin = env-var omniadmin; platform_role='admin' = DB-promoted admin.
 */
function AdminRoute({ children }: Readonly<AdminRouteProps>) {
  return (
    <SessionGate>
      {user => (user.is_admin || user.platform_role === 'admin'
        ? children
        : <Navigate to="/" replace />)}
    </SessionGate>
  );
}

export default AdminRoute;
