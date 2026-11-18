import type { ReactNode } from 'react';
import { AppRole } from '../types/roles';
import { SessionGate } from './SessionGate';
import { AppRoleRoute } from './AppRoleRoute';

export interface EditorRouteProps {
  readonly children: ReactNode;
}

function EditorRoute({ children }: Readonly<EditorRouteProps>) {
  return (
    <SessionGate>
      {() => <AppRoleRoute requiredRole={AppRole.EDITOR}>{children}</AppRoleRoute>}
    </SessionGate>
  );
}

export default EditorRoute;
