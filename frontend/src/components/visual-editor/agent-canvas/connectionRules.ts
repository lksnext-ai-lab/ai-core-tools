import type { AgentType, PieceKind, PortDef } from './agentPorts';

/**
 * Pure connection rules for the per-agent canvas: whether a piece may be
 * connected to (or disconnected from) a port, with exact user-facing reasons.
 * `port` is passed in instead of calling `portsFor` because pure modules
 * cannot import at runtime.
 */

export interface RuleContext {
  readonly canEdit: boolean;
  readonly agentId: number; // 0 for an unsaved agent
  readonly agentType: AgentType;
  readonly hasMemory: boolean;
  readonly port: PortDef; // target port
  readonly kind: PieceKind;
  readonly pieceId: number;
  readonly lifecycleStatus?: 'active' | 'deprecated' | 'retired';
  /** AI services only: whether the service can analyse video (absent = unknown = no). */
  readonly supportsVideo?: boolean;
  readonly toolEdges: Readonly<Record<number, readonly number[]>>; // from getAgents().tool_ids
}

/**
 * A user-facing message as an i18n key plus its values; the UI translates it.
 * A `kind` param holds a PieceKind and a `port` param a PortId: the UI turns
 * them into the translated phrase / port label.
 */
export interface CanvasMessage {
  readonly key: string;
  readonly params?: Readonly<Record<string, string>>;
}

export type RuleResult = { ok: true; warning?: CanvasMessage } | { ok: false; reason: CanvasMessage };

/** Every piece kind, e.g. to validate drag payloads. */
export const PIECE_KINDS = [
  'ai_service', 'embedding', 'sandbox', 'silo', 'skill', 'mcp', 'agent', 'parser', 'middleware',
] as const;

const READ_ONLY: CanvasMessage = { key: 'agentCanvas.rules.readOnly' };

/** Connecting `toolId` as a tool of `agentId` creates a cycle if `toolId` transitively uses `agentId`. */
export function wouldCreateToolCycle(
  agentId: number,
  toolId: number,
  toolEdges: Readonly<Record<number, readonly number[]>>,
): boolean {
  const seen = new Set<number>();
  const stack = [toolId];
  while (stack.length > 0) {
    const current = stack.pop() as number;
    if (current === agentId) return true;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const next of toolEdges[current] ?? []) stack.push(next);
  }
  return false;
}

export function canConnect(ctx: RuleContext): RuleResult {
  if (!ctx.canEdit) return { ok: false, reason: READ_ONLY };
  if (!ctx.port.accepts.includes(ctx.kind)) {
    return {
      ok: false,
      reason: { key: 'agentCanvas.rules.wrongPort', params: { kind: ctx.kind, port: ctx.port.id } },
    };
  }
  if (ctx.port.id === 'video' && ctx.kind === 'ai_service' && ctx.supportsVideo !== true) {
    return { ok: false, reason: { key: 'agentCanvas.rules.noVideo' } };
  }
  if (ctx.kind === 'agent') {
    if (ctx.pieceId === ctx.agentId) return { ok: false, reason: { key: 'agentCanvas.rules.selfTool' } };
    if (wouldCreateToolCycle(ctx.agentId, ctx.pieceId, ctx.toolEdges)) {
      return { ok: false, reason: { key: 'agentCanvas.rules.toolLoop' } };
    }
  }
  if (ctx.lifecycleStatus === 'retired') {
    return { ok: false, reason: { key: 'agentCanvas.rules.retired' } };
  }
  if (ctx.lifecycleStatus === 'deprecated') {
    return { ok: true, warning: { key: 'agentCanvas.rules.deprecated' } };
  }
  return { ok: true };
}

export function canDisconnect(ctx: Pick<RuleContext, 'canEdit' | 'agentType' | 'hasMemory' | 'port'>): RuleResult {
  if (!ctx.canEdit) return { ok: false, reason: READ_ONLY };
  if (ctx.port.id === 'media_embedding' && ctx.hasMemory) {
    return {
      ok: false,
      reason: { key: 'agentCanvas.rules.needsMediaEmbedding' },
    };
  }
  return { ok: true };
}
