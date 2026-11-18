import type { ReactNode } from 'react';
import { SessionGate } from './SessionGate';
import { AppRoleRoute } from './AppRoleRoute';

export interface ProtectedRouteProps {
  readonly children: ReactNode;
}

function ProtectedRoute({ children }: Readonly<ProtectedRouteProps>) {
  return <SessionGate>{() => <AppRoleRoute>{children}</AppRoleRoute>}</SessionGate>;
}

export default ProtectedRoute;
