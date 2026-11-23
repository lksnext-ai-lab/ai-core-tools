/** Up to two uppercase letters identifying a person: name initials, else the email's first letter. */
export function getUserInitials(name?: string | null, email?: string | null): string {
  const fromName = (name ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => Array.from(word)[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
  if (fromName) return fromName;
  const fromEmail = Array.from((email ?? '').trim())[0];
  return fromEmail ? fromEmail.toUpperCase() : 'U';
}
