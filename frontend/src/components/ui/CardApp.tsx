import type { HTMLAttributes, ReactNode } from 'react';

export type CardAppVariant = 'white' | 'canvas' | 'subtle';

const variantClasses: Record<CardAppVariant, string> = {
  white: 'bg-white dark:bg-surface-dark border border-line dark:border-btCard-border-dark flex flex-col',
  canvas: 'bg-canvas-alt dark:bg-canvas-alt-dark border border-bg-soft dark:border-bronze-border-dark flex flex-col',
  subtle: 'bg-tableCab dark:bg-btCard-dark flex flex-col',
};

export interface CardAppProps extends HTMLAttributes<HTMLDivElement> {
  readonly children: ReactNode;
  readonly variant?: CardAppVariant;
}

export function CardApp({
  children,
  variant = 'white',
  className = '',
  ...divProps
}: Readonly<CardAppProps>) {
  return (
    <div
      {...divProps}
      className={`group relative h-full rounded-md p-4 text-left ${variantClasses[variant]} ${className}`}
    >
      {children}
    </div>
  );
}

export default CardApp;