import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useUser } from '../contexts/UserContext';

interface EditorRouteProps {
  children: React.ReactNode;
}

function EditorRoute({ children }: Readonly<EditorRouteProps>) {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const { user, loading: userLoading } = useUser();
  const location = useLocation();

  if (authLoading || userLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (!user?.is_admin && user?.platform_role === 'viewer') {
    return <Navigate to="/home" replace />;
  }

  return <>{children}</>;
}

export default EditorRoute;
