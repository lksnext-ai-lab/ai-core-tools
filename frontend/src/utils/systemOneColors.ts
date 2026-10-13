// Color coding of System One answers in the playground. Pure functions, so the rules are testable.

/** Fixed palette for choice options: an option keeps its color whatever the order, so it can be recognized. */
export const CATEGORY_PALETTE = ['#2563eb', '#9333ea', '#0891b2', '#db2777', '#ca8a04', '#4f46e5', '#0d9488', '#ea580c'] as const;

/** A stable color per option name (a hash of the name): the same category gets the same color in every answer. */
export function categoryColor(name: string): string {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.codePointAt(0)!) >>> 0;
  return CATEGORY_PALETTE[hash % CATEGORY_PALETTE.length];
}

const GREEN: [number, number, number] = [16, 185, 129];
const RED: [number, number, number] = [239, 68, 68];

/**
 * Position t in [0, 1] of a scale mapped onto the green -> red gradient. With `colorStart: 'green'` the first level is
 * green; with 'red' the first level is red. Levels are evenly spread; a single level is the first end.
 */
export function scaleColor(index: number, levels: number, colorStart: 'green' | 'red' = 'green'): string {
  const t = levels <= 1 ? 0 : Math.min(Math.max(index / (levels - 1), 0), 1);
  const [from, to] = colorStart === 'green' ? [GREEN, RED] : [RED, GREEN];
  const mix = from.map((c, i) => Math.round(c + (to[i] - c) * t));
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
}

/** Yes is green, No is red. Undetermined (null) keeps the neutral color. */
export function yesNoColor(decision: boolean | null): string {
  if (decision === null) return 'rgb(156, 163, 175)';
  return decision ? 'rgb(16, 185, 129)' : 'rgb(239, 68, 68)';
}
