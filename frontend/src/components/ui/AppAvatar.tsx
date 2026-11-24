import { useImageFallback } from '../../hooks/useImageFallback';
import { getAppInitials } from '../../utils/appInitials';

export interface AppAvatarProps {
  readonly name?: string | null;
  /** App image URL; the initials are shown when absent or when it fails to load. */
  readonly src?: string | null;
  /** Side of the tile in px. */
  readonly size?: number;
  readonly className?: string;
}

/** Rounded tile of an App: its image, else its initials. Decorative: callers name the App. */
export function AppAvatar({ name, src, size = 40, className = '' }: AppAvatarProps) {
  const { showImage, onError } = useImageFallback(src);

  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-md border-[1.5px] border-accent bg-surface font-display font-medium text-ink dark:border-accent-dark dark:bg-surface-dark dark:text-ink-dark ${className}`}
      style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.375)) }}
    >
      {showImage ? (
        <img src={src ?? undefined} alt="" className="h-full w-full object-cover" onError={onError} />
      ) : (
        getAppInitials(name)
      )}
    </span>
  );
}

export default AppAvatar;
