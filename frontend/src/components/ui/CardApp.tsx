import type { HTMLAttributes, ReactNode } from 'react';

export type CardAppVariant = 'white' | 'canvas' | 'subtle';

const variantClasses: Record<CardAppVariant, string> = {
  white: 'bg-surface dark:bg-surface-dark border border-line dark:border-btCard-border-dark',
  canvas: 'bg-canvas-alt dark:bg-canvas-alt-dark border border-bg-soft dark:border-bronze-border-dark',
  subtle: 'bg-tableCab dark:bg-btCard-dark',
};

export interface CardAppProps extends HTMLAttributes<HTMLDivElement> {
  readonly children: ReactNode;
  readonly variant?: CardAppVariant;
}

/** Surface container for page sections and form blocks. Defaults to p-4; pass a padding class to override. */
export function CardApp({
  children,
  variant = 'white',
  className = '',
  ...divProps
}: Readonly<CardAppProps>) {
  return (
    <div
      {...divProps}
      className={`group relative flex h-full flex-col rounded-md p-4 text-left ${variantClasses[variant]} ${className}`}
    >
      {children}
    </div>
  );
}

export default CardApp;
