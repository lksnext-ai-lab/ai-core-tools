import { useImageFallback } from '../../hooks/useImageFallback';
import { getUserInitials } from '../../utils/userInitials';

export interface UserAvatarProps {
  readonly name?: string | null;
  readonly email?: string | null;
  /** Profile picture URL; the initials are shown when absent or when it fails to load. */
  readonly src?: string | null;
  /** Side of the circle in px. */
  readonly size?: number;
  readonly className?: string;
}

/** Round avatar: the profile picture, else the person's initials. Decorative: callers label the speaker. */
export function UserAvatar({ name, email, src, size = 32, className = '' }: UserAvatarProps) {
  const { showImage, onError } = useImageFallback(src);

  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-ink dark:bg-ink-dark ${className}`}
      style={{ width: size, height: size }}
    >
      {showImage ? (
        <img
          src={src ?? undefined}
          alt=""
          className="h-full w-full object-cover"
          onError={onError}
        />
      ) : (
        <span
          className="font-display font-medium leading-none text-ink-on dark:text-ink-on-dark"
          style={{ fontSize: Math.max(10, Math.round(size * 0.375)) }}
        >
          {getUserInitials(name, email)}
        </span>
      )}
    </span>
  );
}

export default UserAvatar;
