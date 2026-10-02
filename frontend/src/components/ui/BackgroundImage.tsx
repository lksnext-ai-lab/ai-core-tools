import { Bot, FileText, MessagesSquare, Store } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type BackgroundImageIconName = 'Bot' | 'FileText' | 'MessagesSquare' | 'Store';

const icons: Record<BackgroundImageIconName, LucideIcon> = {
  Bot,
  FileText,
  MessagesSquare,
  Store,
};

export interface BackgroundImageProps {
  readonly icon: BackgroundImageIconName | LucideIcon;
  readonly size?: number;
  readonly backgroundColor?: string;
  readonly iconColor?: string;
  readonly className?: string;
}

/** Small colored icon tile used beside recent conversation rows. */
export function BackgroundImage({
  icon,
  size = 34,
  backgroundColor = '#ebe6dd',
  iconColor = '#816729',
  className = '',
}: BackgroundImageProps) {
  const Icon = typeof icon === 'string' ? icons[icon] : icon;

  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-lg ${className}`}
      style={{ width: size, height: size, backgroundColor }}
    >
      <Icon size={size / 2} color={iconColor} strokeWidth={1.5} />
    </span>
  );
}

export default BackgroundImage;