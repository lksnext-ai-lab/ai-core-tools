import type { ReactNode } from 'react';

export interface ButtonTabProps {
  readonly children: ReactNode;
  readonly ariaLabel?: string;
  readonly className?: string;
}

export function ButtonTab({
  children,
  ariaLabel = 'Items',
  className = '',
}: ButtonTabProps) {
  return (
    <div
      role="list"
      aria-label={ariaLabel}
      className={`overflow-hidden rounded-lg border border-btCard-border bg-btCard-bg dark:border-btCard-border-dark dark:bg-btCard-bg-dark hover:bg-btCard-hover ${className}`}
    >
      {children}
    </div>
  );
}

export default ButtonTab;