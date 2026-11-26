/**
 * Pure planning of the saves a connect gesture needs, plus a per-key queue
 * that runs them one at a time without letting one failure block the rest.
 */

import type { PieceKind, PortId } from './agentPorts';
import type { CanvasMessage } from './connectionRules';

/** One agent save the caller executes: getAgent → updateAgent(appId, id, {...fresh, ...patch}). */
export interface SaveStep {
  readonly agentId: number;
  readonly patch: Record<string, unknown>;
  readonly toast?: CanvasMessage;
  /** Appended to `toast` (e.g. a drop hint for other ports). */
  readonly toastSuffix?: CanvasMessage;
}

/** Ordered saves for one connect gesture. */
export function planConnect(args: {
  agentId: number;
  port: PortId;
  kind: PieceKind;
  pieceId: number;
  patch: Record<string, unknown>;
  targetIsTool?: boolean;
  codeInterpreterOn?: boolean;
  replacedName?: string | null;
  /** Appended to the connect step's success toast (e.g. a drop hint for other ports). */
  toastSuffix?: CanvasMessage;
  pieceName: string;
}): SaveStep[] {
  const steps: SaveStep[] = [];
  if (args.port === 'tools' && args.kind === 'agent' && args.targetIsTool === false) {
    steps.push({
      agentId: args.pieceId,
      patch: { is_tool: true },
      toast: { key: 'agentCanvas.save.nowTool', params: { name: args.pieceName } },
    });
  }
  if (args.port === 'sandbox' && args.codeInterpreterOn === false) {
    steps.push({
      agentId: args.agentId,
      patch: { ...args.patch, enable_code_interpreter: true },
      toast: { key: 'agentCanvas.save.codeInterpreterOn', params: { name: args.pieceName } },
    });
    return steps;
  }
  steps.push({
    agentId: args.agentId,
    patch: args.patch,
    toast: args.replacedName
      ? { key: 'agentCanvas.save.replaced', params: { replaced: args.replacedName, name: args.pieceName } }
      : { key: 'agentCanvas.save.connected', params: { name: args.pieceName } },
    ...(args.toastSuffix ? { toastSuffix: args.toastSuffix } : {}),
  });
  return steps;
}

/** Runs tasks one at a time per key; a failure rejects that task only and the queue continues. */
export function createSaveQueue(): { run<T>(key: number, task: () => Promise<T>): Promise<T> } {
  const chains = new Map<number, Promise<unknown>>();
  return {
    run<T>(key: number, task: () => Promise<T>): Promise<T> {
      const previous = chains.get(key) ?? Promise.resolve();
      const result = previous.catch(() => {}).then(task);
      chains.set(key, result.catch(() => {}));
      return result;
    },
  };
}
