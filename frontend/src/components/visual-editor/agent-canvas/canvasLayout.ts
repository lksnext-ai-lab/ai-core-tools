/**
 * Pure persistence of the per-agent canvas layout (node positions and ids
 * pulled out of ports) in the browser's localStorage. Storage is injected so
 * the module stays testable and free of any DOM access.
 */

/** Minimal storage surface the canvas needs (localStorage-compatible). */
export interface StorageLike {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
}

/** Saved layout; node ids are `${kind}:${id}` strings. */
export interface CanvasLayout {
  readonly positions: Record<string, { x: number; y: number }>;
  readonly loose: string[];
}

/** localStorage key scoped to one agent of one app. */
export function layoutKey(appId: number, agentId: number): string {
  return `mattin.agentCanvas.v1.${appId}.${agentId}`;
}

/** Stored layout without entries for nodes the agent no longer has; malformed values are dropped. */
export function loadLayout(
  storage: StorageLike | null,
  appId: number,
  agentId: number,
  knownNodeIds: ReadonlySet<string>,
): CanvasLayout {
  let stored: unknown = null;
  try {
    stored = JSON.parse(storage?.getItem(layoutKey(appId, agentId)) ?? 'null');
  } catch {
    // Storage blocked or invalid JSON: start from an empty layout.
  }
  const { positions: rawPositions, loose: rawLoose } = (stored && typeof stored === 'object' ? stored : {}) as {
    positions?: unknown;
    loose?: unknown;
  };
  const positions: Record<string, { x: number; y: number }> = {};
  if (rawPositions && typeof rawPositions === 'object' && !Array.isArray(rawPositions)) {
    for (const [id, value] of Object.entries(rawPositions)) {
      const { x, y } = (value ?? {}) as { x?: unknown; y?: unknown };
      if (knownNodeIds.has(id) && Number.isFinite(x) && Number.isFinite(y)) {
        positions[id] = { x: x as number, y: y as number };
      }
    }
  }
  const loose = Array.isArray(rawLoose)
    ? rawLoose.filter((id): id is string => typeof id === 'string' && knownNodeIds.has(id))
    : [];
  return { positions, loose };
}

/** Persist the layout; storage failures are swallowed (persistence is best-effort). */
export function saveLayout(
  storage: StorageLike | null,
  appId: number,
  agentId: number,
  layout: CanvasLayout,
): void {
  if (!storage) return;
  try {
    storage.setItem(layoutKey(appId, agentId), JSON.stringify(layout));
  } catch {
    // Quota exceeded or storage blocked: the canvas keeps working without saved layout.
  }
}
