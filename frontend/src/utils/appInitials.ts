const MIN_SIGNIFICANT_LENGTH = 4;

const chars = (text: string): string[] => Array.from(text);
const initialOf = (word: string): string => chars(word)[0] ?? '';

/**
 * Up to two uppercase letters identifying an app, derived from its name.
 *
 * - One word: its first two letters.
 * - Several words: the initials of the first two words longer than 3 characters
 *   (a single one gives a single initial).
 * - Several words, none longer than 3 characters: the initials of the first two words.
 */
export function getAppInitials(name: string | null | undefined): string {
  const words = (name ?? '').split(/\s+/).filter(Boolean);
  if (words.length === 0) return '';

  if (words.length === 1) {
    return chars(words[0]).slice(0, 2).join('').toUpperCase();
  }

  const significant = words.filter((w) => chars(w).length >= MIN_SIGNIFICANT_LENGTH);
  const source = significant.length > 0 ? significant : words;
  return source.slice(0, 2).map(initialOf).join('').toUpperCase();
}
