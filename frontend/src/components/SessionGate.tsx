import React, { useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useUser, type User } from '../contexts/UserContext';
import { ErrorState } from './ui/ErrorState';

interface SessionGateProps {
  readonly children: (user: User) => React.ReactNode;
}

function FullScreenSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-white dark:bg-gray-900" role="status" aria-live="polite">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" aria-hidden="true"></div>
      <span className="sr-only">Checking your session…</span>
    </div>
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
      refreshUser().finally(() => setRetrying(false));
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
