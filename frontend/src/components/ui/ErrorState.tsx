import Alert from './Alert';

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
      <Alert
        type="error"
        message={(
          <>
            {error}
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="mt-2 block font-medium underline underline-offset-2"
              >
                {retryLabel}
              </button>
            )}
          </>
        )}
      />
    </div>
  );
}

export default ErrorState;

