import type { CSSProperties } from 'react';
import type { LucideIcon } from 'lucide-react';

export interface KindIconProps {
  readonly icon: LucideIcon;
  /** The piece kind's hue (`accentHex`), the same one its connector dots and edges use. */
  readonly color: string;
  readonly size?: number;
  readonly iconSize?: number;
}

/**
 * Icon tile tinted with the piece kind's colour, so a kind reads the same in the
 * palette, on the canvas and in the inspector. Lighter glyph in dark mode for contrast.
 */
export function KindIcon({ icon: Icon, color, size = 34, iconSize }: KindIconProps) {
  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center rounded-lg bg-[color:color-mix(in_srgb,var(--kind)_14%,transparent)] text-[color:var(--kind)] dark:bg-[color:color-mix(in_srgb,var(--kind)_30%,transparent)] dark:text-[color:color-mix(in_srgb,var(--kind)_55%,white)]"
      style={{ width: size, height: size, '--kind': color } as CSSProperties}
    >
      <Icon size={iconSize ?? size / 2} strokeWidth={1.5} />
    </span>
  );
}
