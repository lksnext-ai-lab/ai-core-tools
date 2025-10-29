import React from 'react';
import { Navigate } from 'react-router-dom';
import { useUser } from '../contexts/UserContext';

interface AdminRouteProps {
  children: React.ReactNode;
}

/**
 * AdminRoute component - Protects routes that require admin access
 * 
 * This component checks if:
 * 1. User is authenticated
 * 2. User has admin privileges (is_admin === true)
 * 
 * If not authenticated or not admin, redirects to home page
 */
function AdminRoute({ children }: AdminRouteProps) {
  const { user, loading } = useUser();

  // Debug logging
  console.log('AdminRoute - User:', user);
  console.log('AdminRoute - Is Admin:', user?.is_admin);
  console.log('AdminRoute - Loading:', loading);

  // Show nothing while loading
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // If not authenticated or not admin, redirect to home
  if (!user || !user.is_admin) {
    console.log('AdminRoute - Access DENIED - Redirecting to home');
    return <Navigate to="/" replace />;
  }

  // User is authenticated and is admin, render the protected content
  console.log('AdminRoute - Access GRANTED - Rendering admin content');
  return <>{children}</>;
}

export default AdminRoute;

