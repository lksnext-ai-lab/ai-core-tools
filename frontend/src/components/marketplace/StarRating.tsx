import React, { useState } from 'react';

interface StarRatingProps {
  /** Current value (1–5), null means no rating */
  readonly value: number | null;
  /** Max stars (default 5) */
  readonly max?: number;
  /** Allow user interaction */
  readonly interactive?: boolean;
  /** Called when user clicks a star */
  readonly onChange?: (rating: number) => void;
  /** Visual size */
  readonly size?: 'sm' | 'md';
}

/**
 * Read-only or interactive star rating component.
 * When interactive, hover highlights stars and click submits the rating.
 */
export function StarRating({
  value,
  max = 5,
  interactive = false,
  onChange,
  size = 'sm',
}: StarRatingProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  const starSize = size === 'md' ? 'text-xl' : 'text-sm';
  const filled = hovered ?? value ?? 0;

  return (
    <div
      className="flex items-center gap-0.5"
      role={interactive ? 'radiogroup' : undefined}
      aria-label="Star rating"
    >
      {Array.from({ length: max }, (_, i) => {
        const starValue = i + 1;
        const isFilled = starValue <= filled;

        if (!interactive) {
          return (
            <span
              key={starValue}
              className={`${starSize} leading-none ${isFilled ? 'text-yellow-400' : 'text-gray-300'}`}
              aria-hidden="true"
            >
              ★
            </span>
          );
        }

        return (
          <button
            key={starValue}
            type="button"
            role="radio"
            aria-checked={value === starValue}
            aria-label={`${starValue} star${starValue !== 1 ? 's' : ''}`}
            className={`${starSize} leading-none transition-colors cursor-pointer ${
              isFilled ? 'text-yellow-400' : 'text-gray-300'
            } hover:text-yellow-400`}
            onMouseEnter={() => setHovered(starValue)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => onChange?.(starValue)}
          >
            ★
          </button>
        );
      })}
    </div>
  );
}

export default StarRating;
