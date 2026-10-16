export type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';
export type SpinnerTone = 'fg' | 'current' | 'muted';

export interface SpinnerProps {
  readonly size?: SpinnerSize;
  /** `current` inherits the text color of its container (use inside buttons). */
  readonly tone?: SpinnerTone;
  /** Accessible text. When set, the spinner is announced as a status; otherwise it is decorative. */
  readonly label?: string;
  readonly className?: string;
}

const sizeClasses: Record<SpinnerSize, string> = {
  xs: 'h-3 w-3 border-2',
  sm: 'h-4 w-4 border-2',
  md: 'h-5 w-5 border-2',
  lg: 'h-8 w-8 border-[3px]',
  xl: 'h-12 w-12 border-4',
};

const toneClasses: Record<SpinnerTone, string> = {
  fg: 'border-fg/20 border-t-fg dark:border-fg-dark/20 dark:border-t-fg-dark',
  current: 'border-current/30 border-t-current',
  muted: 'border-fg-tertiary/20 border-t-fg-tertiary dark:border-fg-tertiary-dark/20 dark:border-t-fg-tertiary-dark',
};

/** Loading spinner: faint track ring with a solid rotating arc. */
export function Spinner({ size = 'sm', tone = 'fg', label, className = '' }: SpinnerProps) {
  const ring = (
    <span
      className={`inline-block shrink-0 animate-spin rounded-full ${toneClasses[tone]} ${sizeClasses[size]} ${label ? '' : className}`}
      aria-hidden="true"
    />
  );

  if (!label) return ring;

  return (
    <output className={`inline-flex ${className}`}>
      {ring}
      <span className="sr-only">{label}</span>
    </output>
  );
}

export default Spinner;
