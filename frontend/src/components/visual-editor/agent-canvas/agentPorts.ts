/**
 * Pure model of the connection ports an agent body exposes on the visual
 * canvas: which piece kinds each port accepts, which agent field backs it,
 * and how drops and edge mutations translate into agent payload fields.
 */

import type { PIECE_KINDS } from './connectionRules';

export type PieceKind = (typeof PIECE_KINDS)[number];

export type PortId =
  | 'model'
  | 'knowledge'
  | 'skills'
  | 'tools'
  | 'output'
  | 'middlewares'
  | 'sandbox'
  | 'transcription'
  | 'video'
  | 'media_embedding'
  | 'vision'
  | 'text';

export type AgentType = 'agent' | 'ocr_agent';

export interface AgentLinks {
  service_id?: number | null;
  silo_id?: number | null;
  output_parser_id?: number | null;
  sandbox_service_id?: number | null;
  transcription_service_id?: number | null;
  video_ai_service_id?: number | null;
  media_embedding_service_id?: number | null;
  vision_service_id?: number | null;
  skill_ids?: number[];
  mcp_config_ids?: number[];
  tool_ids?: number[];
  middleware_ids?: number[];
}

/** One connection port on the agent body. */
export interface PortDef {
  readonly id: PortId;
  readonly accepts: readonly PieceKind[];
  readonly multiple: boolean;
  /** Agent field this port connects through (`tools` picks between two fields by kind). */
  readonly field: keyof AgentLinks;
  /** Rendered as a secondary slot on the body rather than a primary one. */
  readonly secondary?: boolean;
}

export const AGENT_PORTS: readonly PortDef[] = [
  { id: 'model', accepts: ['ai_service'], multiple: false, field: 'service_id' },
  { id: 'knowledge', accepts: ['silo'], multiple: false, field: 'silo_id' },
  { id: 'skills', accepts: ['skill'], multiple: true, field: 'skill_ids' },
  { id: 'tools', accepts: ['mcp', 'agent'], multiple: true, field: 'mcp_config_ids', secondary: true },
  { id: 'output', accepts: ['parser'], multiple: false, field: 'output_parser_id', secondary: true },
  { id: 'middlewares', accepts: ['middleware'], multiple: true, field: 'middleware_ids', secondary: true },
  { id: 'sandbox', accepts: ['sandbox'], multiple: false, field: 'sandbox_service_id', secondary: true },
  { id: 'transcription', accepts: ['ai_service'], multiple: false, field: 'transcription_service_id' },
  { id: 'video', accepts: ['ai_service'], multiple: false, field: 'video_ai_service_id' },
  { id: 'media_embedding', accepts: ['embedding'], multiple: false, field: 'media_embedding_service_id', secondary: true },
];

export const OCR_PORTS: readonly PortDef[] = [
  { id: 'vision', accepts: ['ai_service'], multiple: false, field: 'vision_service_id' },
  { id: 'text', accepts: ['ai_service'], multiple: false, field: 'service_id' },
  { id: 'output', accepts: ['parser'], multiple: false, field: 'output_parser_id' },
];

export function portsFor(type: AgentType): readonly PortDef[] {
  return type === 'ocr_agent' ? OCR_PORTS : AGENT_PORTS;
}

const ALL_PORTS: readonly PortDef[] = [...AGENT_PORTS, ...OCR_PORTS];

function portDef(port: PortId): PortDef {
  const def = ALL_PORTS.find((entry) => entry.id === port);
  if (!def) throw new Error(`Unknown port "${port}"`);
  return def;
}

/** Agent field a piece connects through on `port`; `tools` picks its field by kind. */
function fieldFor(port: PortId, kind: PieceKind): keyof AgentLinks {
  if (port === 'tools') return kind === 'mcp' ? 'mcp_config_ids' : 'tool_ids';
  return portDef(port).field;
}

/** Port for a drop onto the agent body. 'ask' = more than one port accepts it and none is default. */
export function resolveDropPort(type: AgentType, kind: PieceKind): PortId | 'ask' | null {
  if (type === 'ocr_agent') {
    if (kind === 'ai_service') return 'ask';
    return kind === 'parser' ? 'output' : null;
  }
  // Many agent ports accept AI services; the body default is the model slot.
  if (kind === 'ai_service') return 'model';
  const matches = AGENT_PORTS.filter((def) => def.accepts.includes(kind));
  return matches.length === 1 ? matches[0].id : matches.length === 0 ? null : 'ask';
}

/**
 * Fields to send for connecting/disconnecting `pieceId` on `port`. Multi ports
 * add/remove (add is idempotent, middlewares append at the end); single ports
 * set the id, or clear it only while it still holds `pieceId`. A remove for a
 * piece that is no longer on the port (already replaced) returns no change.
 */
export function buildPortPatch(
  agent: AgentLinks,
  port: PortId,
  kind: PieceKind,
  pieceId: number,
  mode: 'add' | 'remove',
): Partial<AgentLinks> {
  const field = fieldFor(port, kind);
  if (portDef(port).multiple) {
    const current: number[] = Array.isArray(agent[field]) ? agent[field] : [];
    const next = mode === 'remove'
      ? current.filter((id) => id !== pieceId)
      : current.includes(pieceId) ? [...current] : [...current, pieceId];
    return { [field]: next } as Partial<AgentLinks>;
  }
  if (mode === 'add') return { [field]: pieceId } as Partial<AgentLinks>;
  return agent[field] === pieceId ? ({ [field]: null } as Partial<AgentLinks>) : {};
}

/** Every (port, kind, id) currently connected, for drawing edges. */
export function connectedPieces(
  type: AgentType,
  agent: AgentLinks,
): Array<{ port: PortId; kind: PieceKind; id: number }> {
  const pieces: Array<{ port: PortId; kind: PieceKind; id: number }> = [];
  for (const def of portsFor(type)) {
    for (const kind of def.accepts) {
      const value = agent[fieldFor(def.id, kind)];
      if (def.multiple) {
        if (!Array.isArray(value)) continue;
        for (const id of value) pieces.push({ port: def.id, kind, id });
      } else if (typeof value === 'number') {
        pieces.push({ port: def.id, kind, id: value });
      }
    }
  }
  return pieces;
}
