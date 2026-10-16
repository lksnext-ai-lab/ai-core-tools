export type SkeletonShape = 'line' | 'block' | 'round';

export interface SkeletonProps {
  /** `line` for text rows, `block` for cards/areas, `round` for avatars, circles and pill bars. */
  readonly shape?: SkeletonShape;
  /** Size and layout (e.g. `h-3 w-24`, `flex-1`). */
  readonly className?: string;
}

const shapeClasses: Record<SkeletonShape, string> = {
  line: 'rounded',
  block: 'rounded-xl',
  round: 'rounded-full',
};

/** Placeholder block that mimics content while it loads. Combine several to draw the content's silhouette. */
export function Skeleton({ shape = 'line', className = '' }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse bg-surface-ash dark:bg-surface-hover-dark ${shapeClasses[shape]} ${className}`}
      aria-hidden="true"
    />
  );
}

export default Skeleton;
