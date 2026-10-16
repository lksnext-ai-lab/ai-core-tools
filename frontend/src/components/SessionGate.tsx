import React, { useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useUser, type User } from '../contexts/UserContext';
import { ErrorState } from './ui/ErrorState';
import { LoadingState } from './ui/LoadingState';

interface SessionGateProps {
  readonly children: (user: User) => React.ReactNode;
}

function FullScreenSpinner() {
  return (
    <LoadingState variant="fullScreen" message="Checking your session…" />
  );
}

/**
 * Renders protected content only once the backend has confirmed the session.
 * Distinguishes a rejected session (redirect to /login, keeping the requested
 * location) from an unreachable backend (retry screen instead of a false logout).
 */
export function SessionGate({ children }: SessionGateProps) {
  const { user, loading, sessionError, refreshUser } = useUser();
  const location = useLocation();
  const [retrying, setRetrying] = useState(false);

  if (loading) {
    return <FullScreenSpinner />;
  }

  if (!user && sessionError === 'unavailable') {
    const retry = () => {
      setRetrying(true);
      void refreshUser().finally(() => setRetrying(false));
    };
    return (
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-gray-900">
        <ErrorState
          className="max-w-md w-full"
          error="We couldn't reach the server to check your session."
          onRetry={retrying ? undefined : retry}
          retryLabel="Try again"
        />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children(user)}</>;
}

export default SessionGate;
