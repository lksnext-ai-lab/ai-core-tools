// localStorage persistence for the platform chatbot's per-user conversation.
//
// Every key is scoped to the user id, so a different user signing in on the same
// browser never sees (or continues) somebody else's conversation, and the stored
// history is validated on read because localStorage is writable by anything
// running on this origin.

const PREFIX = 'platform_chatbot_';
const LEGACY_SESSION_KEY = 'platform_chatbot_session_id';

export interface StoredChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  follow_ups?: string[];
}

function sessionKey(userId: number): string {
  return `${PREFIX}session_id_${userId}`;
}

function historyKey(sessionId: string): string {
  return `${PREFIX}history_${sessionId}`;
}

function defaultSessionId(userId: number): string {
  return `${PREFIX}${userId}`;
}

function belongsTo(sessionId: string, userId: number): boolean {
  const own = defaultSessionId(userId);
  return sessionId === own || sessionId.startsWith(`${own}_`);
}

function isStoredChatMessage(value: unknown): value is StoredChatMessage {
  if (typeof value !== 'object' || value === null) return false;
  const msg = value as Record<string, unknown>;
  return (
    (msg.role === 'user' || msg.role === 'assistant') &&
    typeof msg.content === 'string' &&
    typeof msg.timestamp === 'number' &&
    (msg.follow_ups === undefined ||
      (Array.isArray(msg.follow_ups) && msg.follow_ups.every((f) => typeof f === 'string')))
  );
}

/** Returns the user's current session id, creating (and persisting) one if needed. */
export function resolveSessionId(userId: number): string {
  try {
    const stored = localStorage.getItem(sessionKey(userId));
    if (stored && belongsTo(stored, userId)) return stored;

    // Before keys were per user, a single browser-wide key was used; only adopt
    // it when it was created for this same user.
    const legacy = localStorage.getItem(LEGACY_SESSION_KEY);
    localStorage.removeItem(LEGACY_SESSION_KEY);
    const resolved = legacy && belongsTo(legacy, userId) ? legacy : defaultSessionId(userId);
    localStorage.setItem(sessionKey(userId), resolved);
    return resolved;
  } catch {
    return defaultSessionId(userId);
  }
}

/** Starts a fresh conversation for the user and returns its session id. */
export function newSessionId(userId: number): string {
  const id = `${defaultSessionId(userId)}_${Date.now()}`;
  try {
    localStorage.setItem(sessionKey(userId), id);
  } catch {
    // localStorage may be unavailable — the id still works for this page view
  }
  return id;
}

/** Reads the stored history, dropping anything that is not a well-formed message. */
export function readHistory(sessionId: string): StoredChatMessage[] {
  if (!sessionId) return [];
  try {
    const raw = localStorage.getItem(historyKey(sessionId));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isStoredChatMessage) : [];
  } catch {
    return [];
  }
}

export function writeHistory(sessionId: string, messages: StoredChatMessage[]): void {
  try {
    localStorage.setItem(historyKey(sessionId), JSON.stringify(messages));
  } catch {
    // localStorage may be unavailable or full — fail silently
  }
}

/** Removes every platform chatbot entry (call on logout). */
export function clearPlatformChatbotStorage(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(PREFIX)) keys.push(key);
    }
    keys.forEach((key) => localStorage.removeItem(key));
  } catch {
    // ignore
  }
}
