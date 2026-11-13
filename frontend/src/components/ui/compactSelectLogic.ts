/** Pure logic behind CompactSelectPopover (kept free of React so it can be unit-tested). */

export interface SelectLogicOption {
  readonly value: string;
  readonly label: string;
  readonly group?: string;
  readonly disabled?: boolean;
}

export interface SelectLogicGroup<T extends SelectLogicOption> {
  /** Position of the group; used for DOM ids and React keys (never the header text). */
  readonly index: number;
  readonly header?: string;
  readonly items: readonly { readonly option: T; readonly index: number }[];
}

export const PAGE_STEP = 10;

export function filterOptions<T extends SelectLogicOption>(options: readonly T[], query: string): readonly T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return options;
  return options.filter((o) => o.label.toLowerCase().includes(needle));
}

/** Groups options by header (order of first appearance); `index` follows the visual order. */
export function buildGroups<T extends SelectLogicOption>(options: readonly T[]): SelectLogicGroup<T>[] {
  const buckets = new Map<string, T[]>();
  for (const option of options) {
    const header = option.group ?? '';
    const bucket = buckets.get(header) ?? [];
    bucket.push(option);
    buckets.set(header, bucket);
  }
  let next = 0;
  return Array.from(buckets, ([header, items], index) => ({
    index,
    header: header || undefined,
    items: items.map((option) => ({ option, index: next++ })),
  }));
}

export function flattenGroups<T extends SelectLogicOption>(groups: readonly SelectLogicGroup<T>[]): T[] {
  return groups.flatMap((g) => g.items.map((i) => i.option));
}

export function clampIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.min(Math.max(index, 0), length - 1);
}

export type NavigationKey = 'ArrowDown' | 'ArrowUp' | 'Home' | 'End' | 'PageDown' | 'PageUp';

/** Next active index for a navigation key, always within [0, length-1] (0 for an empty list). */
export function nextActiveIndex(current: number, key: NavigationKey, length: number): number {
  const from = clampIndex(current, length);
  switch (key) {
    case 'ArrowDown': return clampIndex(from + 1, length);
    case 'ArrowUp': return clampIndex(from - 1, length);
    case 'Home': return 0;
    case 'End': return clampIndex(length - 1, length);
    case 'PageDown': return clampIndex(from + PAGE_STEP, length);
    case 'PageUp': return clampIndex(from - PAGE_STEP, length);
  }
}

export type ActivateResult =
  | { readonly kind: 'none' }
  | { readonly kind: 'single'; readonly value: string }
  | { readonly kind: 'multiple'; readonly values: string[]; readonly selected: boolean };

/** What activating the option at `activeIndex` does. Disabled / missing options do nothing. */
export function activateResult<T extends SelectLogicOption>(
  flat: readonly T[],
  activeIndex: number,
  multiple: boolean,
  currentValues: readonly string[],
): ActivateResult {
  if (flat.length === 0) return { kind: 'none' };
  const option = flat[clampIndex(activeIndex, flat.length)];
  if (!option || option.disabled) return { kind: 'none' };
  if (!multiple) return { kind: 'single', value: option.value };
  const selected = !currentValues.includes(option.value);
  return {
    kind: 'multiple',
    selected,
    values: selected ? [...currentValues, option.value] : currentValues.filter((v) => v !== option.value),
  };
}

/** Labels of the selected values; values missing from `options` use `fallbackLabel` (or are dropped). */
export function selectedLabels(
  options: readonly SelectLogicOption[],
  values: readonly string[],
  fallbackLabel?: (value: string) => string,
): string[] {
  const out: string[] = [];
  for (const v of values) {
    const found = options.find((o) => o.value === v);
    if (found) out.push(found.label);
    else if (fallbackLabel) out.push(fallbackLabel(v));
  }
  return out;
}

export function chipValueText(
  labels: readonly string[],
  placeholder: string,
  summarize?: (labels: readonly string[]) => string,
): string {
  if (labels.length === 0) return placeholder;
  if (labels.length > 2 && summarize) return summarize(labels);
  return labels.join(', ');
}

export const TYPE_AHEAD_RESET_MS = 500;

/** Index of the next option whose label starts with `buffer`, searching after `current` and wrapping. */
export function typeAheadIndex(flat: readonly SelectLogicOption[], current: number, buffer: string): number {
  const needle = buffer.toLowerCase();
  if (!needle || flat.length === 0) return -1;
  // Repeating one character cycles through the options that start with it.
  const cycling = needle.split('').every((c) => c === needle[0]);
  const prefix = cycling ? needle[0] : needle;
  const start = cycling ? current + 1 : current;
  for (let step = 0; step < flat.length; step++) {
    const i = (start + step + flat.length) % flat.length;
    if (flat[i].label.toLowerCase().startsWith(prefix)) return i;
  }
  return -1;
}
