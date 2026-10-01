import React from 'react';

interface ErrorStateProps {
  readonly error: string;
  readonly onRetry?: () => void;
  readonly className?: string;
  readonly retryLabel?: string;
}

/**
 * Reusable error state component
 * Shows an error message with an optional retry button
 */
export function ErrorState({ 
  error, 
  onRetry, 
  className = '',
  retryLabel = 'Try again'
}: ErrorStateProps) {
  return (
    <div className={`p-6 ${className}`}>
      <div className="bg-error-bg border border-error-border rounded-lg p-4 dark:bg-error-bg-dark dark:border-error-border-dark">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg 
              className="h-5 w-5 text-error dark:text-error-dark"
              xmlns="http://www.w3.org/2000/svg" 
              viewBox="0 0 20 20" 
              fill="currentColor"
            >
              <path 
                fillRule="evenodd" 
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" 
                clipRule="evenodd" 
              />
            </svg>
          </div>
          <div className="ml-3 flex-1">
            <p className="text-sm text-error dark:text-error-dark">{error}</p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="mt-2 text-sm text-error-strong hover:text-error underline underline-offset-2 font-medium dark:text-error-strong-dark dark:hover:text-error-dark"
              >
                {retryLabel}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ErrorState;

