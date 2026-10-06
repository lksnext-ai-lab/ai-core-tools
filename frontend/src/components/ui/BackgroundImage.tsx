import { Bot, FileText, MessagesSquare, Store } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type BackgroundImageIconName = 'Bot' | 'FileText' | 'MessagesSquare' | 'Store';
export type BackgroundImageVariant = 'marron';

const icons: Record<BackgroundImageIconName, LucideIcon> = {
  Bot,
  FileText,
  MessagesSquare,
  Store,
};

function getVariantBackgroundClass(variant: BackgroundImageVariant): string {
  if (variant === 'marron') return 'bg-bronze-bg-soft dark:bg-[#2A1A14]';
  return '';
}

function getVariantIconClass(variant: BackgroundImageVariant): string {
  if (variant === 'marron') return 'text-bronze dark:text-bronze-dark';
  return '';
}

export interface BackgroundImageProps {
  readonly icon: BackgroundImageIconName | LucideIcon;
  readonly size?: number;
  readonly iconSize?: number;
  readonly variant?: BackgroundImageVariant;
  readonly className?: string;
}

/** Small colored icon tile used beside recent conversation rows. */
export function BackgroundImage({
  icon,
  size = 34,
  iconSize,
  variant = 'marron',
  className = '',
}: BackgroundImageProps) {
  const Icon = typeof icon === 'string' ? icons[icon] : icon;

  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-lg ${getVariantBackgroundClass(variant)} ${className}`}
      style={{ width: size, height: size }}
    >
      <Icon className={getVariantIconClass(variant)} size={iconSize ?? size / 2} strokeWidth={1.5} />
    </span>
  );
}

export default BackgroundImage;