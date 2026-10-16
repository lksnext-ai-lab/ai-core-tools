import { Bot, FileText, MessageSquare, Plug, Store, Target, Wrench, Database, CalendarClock, Cloud } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';


export type BackgroundImageIconName = 'Bot' | 'FileText' | 'MessageSquare' | 'Store' | 'Wrench' | 'Plug' |'Target' |'Database' | 'CalendarClock' | 'Cloud';
export type BackgroundImageVariant = 'marron' | 'vacio' | 'gris';

const icons: Record<BackgroundImageIconName, LucideIcon> = {
  Bot,
  FileText,
  MessageSquare,
  Store,
  Wrench,
  Plug,
  Target,
  Database,
  CalendarClock,
  Cloud,
};

function getVariantBackgroundClass(variant: BackgroundImageVariant): string {
  if (variant === 'marron') return 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark';
  if (variant === 'vacio') return 'border border-accent dark:border-accent-dark';
  if (variant === 'gris') return 'bg-tableCab dark:bg-surface-hover-dark';
  return '';
}

function getVariantIconClass(variant: BackgroundImageVariant): string {
  if (variant === 'marron') return 'text-bronze dark:text-bronze-dark';
  if (variant === 'vacio') return 'text-fg dark:text-fg-dark';
  if (variant === 'gris') return 'text-textImg dark:text-textImg-dark';
  return '';
}

export interface BackgroundImageProps {
  readonly icon?: BackgroundImageIconName | LucideIcon;
  readonly alt?: string;
  readonly text?: string;
  readonly size?: number;
  readonly iconSize?: number;
  readonly variant?: BackgroundImageVariant;
  readonly className?: string;
  readonly rounded?: string;
}

/** Small colored icon tile used beside recent conversation rows. */
export function BackgroundImage({
  icon,
  alt = '',
  text,
  size = 34,
  iconSize,
  variant = 'marron',
  className = '',
  rounded = 'rounded-lg',
}: BackgroundImageProps) {
  const Icon: LucideIcon | undefined = typeof icon === 'string' ? icons[icon] : icon;

  return (
    <span
      aria-hidden={!text && (!alt || !Icon)}
      className={`flex shrink-0 items-center justify-center overflow-hidden ${rounded} ${getVariantBackgroundClass(variant)} ${className}`}
      style={{ width: size, height: size }}
    >
      {Icon && (
        <Icon
          role={alt ? 'img' : undefined}
          aria-label={alt || undefined}
          aria-hidden={!alt}
          className={getVariantIconClass(variant)}
          size={iconSize ?? size / 2}
          strokeWidth={1.5}
        />
      )}
      {text && <span className="whitespace-nowrap text-[10px] font-semibold leading-none text-fg dark:text-fg-dark">{text}</span>}
    </span>
  );
}

export default BackgroundImage;