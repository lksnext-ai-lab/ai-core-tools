import type { ReactNode } from 'react';
import { Link, type To } from 'react-router-dom';
import {
  buttonAppSizeClasses,
  buttonAppVariantClasses,
  type ButtonAppSize,
  type ButtonAppVariant,
} from './ButtonApp';

export interface ButtonLinkProps {
  readonly label: string;
  readonly to: To;
  readonly variant?: ButtonAppVariant;
  readonly size?: ButtonAppSize;
  readonly icon?: ReactNode;
  readonly className?: string;
}

/** Router link styled as a ButtonApp — same variants and sizes, for navigation instead of actions. */
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
      className={`${baseClasses} ${buttonAppSizeClasses[size]} rounded-md ${buttonAppVariantClasses[variant]} ${className}`}
    >
      {icon}
      {label}
    </Link>
  );
}

export default ButtonLink;
