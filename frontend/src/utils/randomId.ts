/**
 * Random identifier for client-side keys (React list keys, local tool-call ids).
 *
 * Uses crypto.getRandomValues instead of Math.random, and not crypto.randomUUID,
 * which only exists in secure contexts (HTTPS/localhost) — the app can also be
 * served over plain HTTP on a client server.
 */
export function randomId(): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}
