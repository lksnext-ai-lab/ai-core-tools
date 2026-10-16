import type { ReactNode } from 'react';
import { Link, type To } from 'react-router-dom';
import type { ButtonAppSize, ButtonAppVariant } from './ButtonApp';

export interface ButtonLinkProps {
  readonly label: string;
  readonly to: To;
  readonly variant?: ButtonAppVariant;
  readonly size?: ButtonAppSize;
  readonly icon?: ReactNode;
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
  primary: 'border border-transparent bg-ink dark:bg-ink-dark text-ink-on dark:text-ink-on-dark hover:bg-ink-hover dark:hover:bg-ink-hover-dark',
  secondary: 'border border-ink bg-surface text-fg hover:bg-surface-hover dark:border-ink-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark',
  table: 'border border-ink bg-transparent text-fg hover:bg-surface-hover dark:border-ink-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark',
  muted: 'border border-line bg-transparent text-fg-secondary hover:bg-surface-hover dark:border-line-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark',
  danger: 'border border-error text-error hover:bg-error-bg dark:border-error-dark dark:text-error-dark dark:hover:bg-error-bg-dark',
};

export function ButtonLink({
  label,
  to,
  variant = 'primary',
  size = 'medium',
  icon,
  className = '',
}: ButtonLinkProps) {
  const baseClasses = 'inline-flex items-center justify-center gap-2 font-display font-normal tracking-[-0.02em] transition-colors';

  return (
    <Link
      to={to}
      className={`${baseClasses} ${sizeClasses[size]} rounded-md ${variantClasses[variant]} ${className}`}
    >
      {icon}
      {label}
    </Link>
  );
}

export default ButtonLink;