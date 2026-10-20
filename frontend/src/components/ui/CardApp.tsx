import type { HTMLAttributes, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import BackgroundImage from './BackgroundImage';

export type CardAppVariant = 'white' | 'canvas' | 'subtle';

const variantClasses: Record<CardAppVariant, string> = {
  white: 'bg-surface dark:bg-surface-dark border border-line dark:border-btCard-border-dark',
  canvas: 'bg-canvas-alt dark:bg-canvas-alt-dark border border-bg-soft dark:border-bronze-border-dark',
  subtle: 'bg-tableCab dark:bg-btCard-dark',
};

export interface CardAppProps extends HTMLAttributes<HTMLDivElement> {
  readonly children: ReactNode;
  readonly variant?: CardAppVariant;
  readonly icon?: LucideIcon;
  readonly titulo?: string;
  readonly subtitulo?: string;
  readonly headerExtra?: ReactNode;
}

/** Surface container for page sections and form blocks. Defaults to p-4; pass a padding class to override. */
export function CardApp({
  children,
  variant = 'white',
  icon,
  titulo,
  subtitulo,
  headerExtra,
  className = '',
  ...divProps
}: Readonly<CardAppProps>) {
  return (
    <div
      {...divProps}
      className={`group relative flex h-full flex-col rounded-md p-4 text-left ${variantClasses[variant]} ${className}`}
    >
      {(icon || titulo || subtitulo || headerExtra) && (
        <div className="mb-6 flex items-center">
          {icon && (
            <BackgroundImage
              icon={icon}
              size={40}
              iconSize={20}
              variant="marron"
              className="mr-4 rounded-xl"
            />
          )}
          {(titulo || subtitulo) && (
            <div>
              {titulo && <h3 className="text-lg font-semibold text-fg dark:text-fg-dark">{titulo}</h3>}
              {subtitulo && <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{subtitulo}</p>}
            </div>
          )}
          {headerExtra && <div className="ml-auto">{headerExtra}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

export default CardApp;
