import type { ReactNode } from 'react';

export type ButtonAppVariant = 'primary' | 'secondary' | 'table' | 'muted' | 'danger';
export type ButtonAppSize = 'compact' | 'small' | 'control' | 'medium' | 'spacious' | 'large';
export type ButtonAppType = 'button' | 'submit' | 'reset';

export interface ButtonAppProps {
  readonly label: string;
  readonly type?: ButtonAppType;
  readonly onClick?: () => void;
  readonly variant?: ButtonAppVariant;
  readonly size?: ButtonAppSize;
  readonly icon?: ReactNode;
  readonly disabled?: boolean;
  readonly loading?: boolean;
  readonly ariaPressed?: boolean;
  readonly className?: string;
}

const sizeClasses: Record<ButtonAppSize, string> = {
  compact: 'px-3 py-1.5 text-xs',
  small: 'px-[11px] py-[6px] text-[12.5px]',
  control: 'px-4 py-2 text-sm',
  medium: 'px-[15px] py-[9px] text-sm',
  spacious: 'px-[18px] py-[11px] text-[15px]',
  large: 'px-[22px] py-3 text-[15px]',
};

const variantClasses: Record<ButtonAppVariant, string> = {
  primary: 'border border-transparent bg-ink dark:bg-ink-dark text-ink-on dark:text-ink-on-dark hover:bg-[#383838] dark:hover:bg-[#d8d3c8]',
  secondary: 'border border-ink bg-surface text-fg hover:bg-surface-hover dark:border-ink-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark',
  table: 'border border-ink bg-transparent text-fg hover:bg-surface-hover dark:border-ink-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark',
  muted: 'border border-line bg-transparent text-fg-secondary hover:bg-surface-hover dark:border-line-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark',
  danger: 'border border-error text-error hover:bg-error-bg dark:border-error-dark dark:text-error-dark dark:hover:bg-error-bg-dark',
};

/** Button variants based on the actions used throughout the Mattin app template. */
export function ButtonApp({
  label,
  type = 'button',
  onClick,
  variant = 'primary',
  size = 'medium',
  icon,
  disabled = false,
  loading = false,
  ariaPressed,
  className = '',
}: ButtonAppProps) {
  const baseClasses = 'inline-flex cursor-pointer items-center justify-center gap-2 font-display font-normal tracking-[-0.02em] transition-colors disabled:cursor-not-allowed disabled:opacity-50';

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      aria-pressed={ariaPressed}
      aria-busy={loading}
      className={`${baseClasses} ${sizeClasses[size]} rounded-md ${variantClasses[variant]} ${className}`}
    >
      {loading ? (
        <span
          className="h-4 w-4 animate-spin rounded-full border-2 border-current/30 border-t-current"
          aria-hidden="true"
        />
      ) : icon}
      {label}
    </button>
  );
}

export default ButtonApp;