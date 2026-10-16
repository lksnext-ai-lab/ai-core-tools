import { Spinner, type SpinnerSize } from './Spinner';

export type LoadingStateVariant = 'inline' | 'section' | 'page' | 'fullScreen';

export interface LoadingStateProps {
  readonly message?: string;
  /**
   * - `inline`: spinner and message side by side (table bodies, small panels)
   * - `section`: stacked, for a card or panel area (default)
   * - `page`: stacked and larger, replaces a whole page's content
   * - `fullScreen`: covers the viewport (session checks, auth redirects)
   */
  readonly variant?: LoadingStateVariant;
  readonly className?: string;
}

const variantClasses: Record<LoadingStateVariant, string> = {
  inline: 'flex items-center justify-center gap-2 py-6',
  section: 'flex flex-col items-center justify-center gap-2 p-6',
  page: 'flex min-h-64 flex-col items-center justify-center gap-3 py-12',
  fullScreen: 'flex min-h-screen flex-col items-center justify-center gap-3 bg-canvas dark:bg-canvas-dark',
};

const spinnerSizes: Record<LoadingStateVariant, SpinnerSize> = {
  inline: 'md',
  section: 'lg',
  page: 'xl',
  fullScreen: 'xl',
};

/**
 * Reusable loading state component
 * Shows a spinner with an optional message
 */
export function LoadingState({
  message = 'Loading...',
  variant = 'section',
  className = '',
}: LoadingStateProps) {
  return (
    <output aria-live="polite" className={`${variantClasses[variant]} ${className}`}>
      <Spinner size={spinnerSizes[variant]} />
      <span className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{message}</span>
    </output>
  );
}

export default LoadingState;
