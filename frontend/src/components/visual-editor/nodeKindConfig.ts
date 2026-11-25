import {
  ArrowLeftRight,
  Bot,
  Container,
  Cpu,
  Database,
  Layers,
  Sparkles,
  Plug,
  FileJson,
  type LucideIcon,
} from 'lucide-react';
import type { PieceKind } from './agent-canvas/agentPorts';

/**
 * Per-agent canvas visuals for each piece kind: icon, i18n key for the type
 * caption (agentCanvas.kinds.*) and the hue used for the icon tile, the
 * connector dots and the edges. Plain data (no JSX) so it stays cheap to import.
 */
export interface PieceVisual {
  readonly icon: LucideIcon;
  readonly typeCaptionKey: string;
  /** Raw hex for React Flow edge/marker strokes and connector dots. */
  readonly accentHex: string;
}

export const PIECE_VISUALS: Record<PieceKind, PieceVisual> = {
  agent: { icon: Bot, typeCaptionKey: 'agentCanvas.kinds.agent', accentHex: '#6366f1' },
  // Deep navy: must read clearly apart from the agent's indigo bullet.
  ai_service: { icon: Cpu, typeCaptionKey: 'agentCanvas.kinds.service', accentHex: '#1e40af' },
  silo: { icon: Database, typeCaptionKey: 'agentCanvas.kinds.silo', accentHex: '#d97706' },
  // Stronger cyan: the embedding bullet/edge share the hue and a pale card read as "colorless".
  embedding: { icon: Layers, typeCaptionKey: 'agentCanvas.kinds.embedding', accentHex: '#0891b2' },
  skill: { icon: Sparkles, typeCaptionKey: 'agentCanvas.kinds.skill', accentHex: '#9333ea' },
  mcp: { icon: Plug, typeCaptionKey: 'agentCanvas.kinds.mcp', accentHex: '#e11d48' },
  parser: { icon: FileJson, typeCaptionKey: 'agentCanvas.kinds.parser', accentHex: '#475569' },
  sandbox: { icon: Container, typeCaptionKey: 'agentCanvas.kinds.sandbox', accentHex: '#059669' },
  middleware: { icon: ArrowLeftRight, typeCaptionKey: 'agentCanvas.kinds.middleware', accentHex: '#ea580c' },
};
