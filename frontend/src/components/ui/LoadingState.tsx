import React from 'react';

interface LoadingStateProps {
  readonly message?: string;
  readonly className?: string;
  readonly spinnerColor?: string;
}

/**
 * Reusable loading state component
 * Shows a spinner with an optional message
 */
export function LoadingState({ 
  message = "Loading...",
  className = '',
  spinnerColor = 'border-blue-600'
}: LoadingStateProps) {
  return (
    <div className={`p-6 text-center ${className}`}>
      <div className={`animate-spin rounded-full h-8 w-8 border-b-2 ${spinnerColor} mx-auto`}></div>
      <p className="mt-2 text-gray-600">{message}</p>
    </div>
  );
}

export default LoadingState;

