import { getUserInitials } from '../../utils/userInitials';

export interface UserAvatarProps {
  readonly name?: string | null;
  readonly email?: string | null;
  /** Side of the circle in px. */
  readonly size?: number;
  readonly className?: string;
}

/** Round avatar with the person's initials (the platform has no profile pictures). Decorative: callers label the speaker. */
export function UserAvatar({ name, email, size = 32, className = '' }: UserAvatarProps) {
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-full bg-ink dark:bg-ink-dark ${className}`}
      style={{ width: size, height: size }}
    >
      <span
        className="font-display font-medium leading-none text-ink-on dark:text-ink-on-dark"
        style={{ fontSize: Math.max(10, Math.round(size * 0.375)) }}
      >
        {getUserInitials(name, email)}
      </span>
    </span>
  );
}

export default UserAvatar;
