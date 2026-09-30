import React from 'react';
import { Navigate } from 'react-router-dom';
import { SessionGate } from './SessionGate';

interface EditorRouteProps {
  children: React.ReactNode;
}

function EditorRoute({ children }: Readonly<EditorRouteProps>) {
  return (
    <SessionGate>
      {user => (!user.is_admin && user.platform_role === 'viewer'
        ? <Navigate to="/home" replace />
        : children)}
    </SessionGate>
  );
}

export default EditorRoute;
