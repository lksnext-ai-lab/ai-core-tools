/** Hour and minute of a date in the UI language. An invalid tag (e.g. i18next's `cimode`) falls back to the default locale. */
export function formatClockTime(date: Date, language: string): string {
  const options: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' };
  try {
    return date.toLocaleTimeString(language, options);
  } catch {
    return date.toLocaleTimeString([], options);
  }
}

/** True when the user asked the OS to reduce motion (false where `matchMedia` is unavailable). */
export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
