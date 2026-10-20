import type { ReactNode } from 'react';

export interface ButtonCardProps {
  readonly children: ReactNode;
  readonly onClick: () => void;
  readonly ariaLabel?: string;
  readonly className?: string;
}

/**
 * Whole-card button (apps grid, marketplace catalog). An invisible button covers the card;
 * the content ignores pointer events, so nested controls need `pointer-events-auto relative z-10`.
 */
export function ButtonCard({
  children,
  onClick,
  ariaLabel = 'Open card',
  className = '',
}: ButtonCardProps) {
  return (
    <div
      className={`
        group relative flex h-full flex-col
        rounded-md bg-surface-ash p-5
        text-left dark:bg-btCard-dark
        ${className}
      `}
    >
      <button
        type="button"
        onClick={onClick}
        aria-label={ariaLabel}
        className="absolute inset-0 z-0 h-full w-full cursor-pointer rounded-md outline-none focus-visible:outline-none"
      />
      <div className="pointer-events-none relative z-10 flex min-h-0 flex-1 flex-col">
        {children}
      </div>
    </div>
  );
}

export default ButtonCard;
