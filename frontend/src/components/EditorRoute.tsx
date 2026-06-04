import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useUser } from '../contexts/UserContext';

interface EditorRouteProps {
  children: React.ReactNode;
}

function EditorRoute({ children }: Readonly<EditorRouteProps>) {
  const { user, loading } = useUser();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!user?.is_authenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (!user?.is_admin && user?.platform_role === 'viewer') {
    return <Navigate to="/home" replace />;
  }

  return <>{children}</>;
}

export default EditorRoute;
