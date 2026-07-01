/** Returns the value of the named cookie, or null if absent. */
export function getCookieValue(name: string): string | null {
  if (typeof document === 'undefined') return null;

  const encoded = encodeURIComponent(name);
  const prefix = `${encoded}=`;
  const parts = document.cookie.split(';');

  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }

  return null;
}

/** Returns the non-httpOnly csrf_token cookie, or null in OIDC/unauthenticated states. */
export function getCsrfToken(): string | null {
  return getCookieValue('csrf_token');
}
