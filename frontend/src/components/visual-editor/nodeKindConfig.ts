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

export type GraphNodeKind =
  | 'agent'
  | 'service'
  | 'silo'
  | 'embedding'
  | 'skill'
  | 'mcp'
  | 'parser';

/**
 * Visual configuration for a single graph node kind: icon, Tailwind accent
 * classes (light + dark aware) and a human-readable type caption shown under
 * the entity label. Kept as a plain data map (no JSX) so it stays cheap to
 * import from both the node components and the flow adapter.
 */
export interface NodeKindVisual {
  readonly icon: LucideIcon;
  readonly typeCaption: string;
  /** i18n key (agentCanvas.kinds.*) for the caption; prefer over `typeCaption`. */
  readonly typeCaptionKey: string;
  /** Icon glyph color - intentionally decoupled from `captionClass` because
   *  some kind hues (amber/cyan) need a darker shade for the smaller type
   *  caption text to hit 4.5:1 contrast than looks right for a 16px icon. */
  readonly iconClass: string;
  /** Type caption text color - AA-safe (>=4.5:1) against the card background in both themes. */
  readonly captionClass: string;
  /** Icon chip background. */
  readonly chipClass: string;
  /** Card border color (also used to tint the connected edges). */
  readonly borderClass: string;
  /** Card background. */
  readonly bgClass: string;
  /** Raw hex used for React Flow edge/marker strokes (must match borderClass hue). */
  readonly accentHex: string;
  /** Agents are the primary/central entity - rendered slightly larger and bolder. */
  readonly emphasize: boolean;
}

export const NODE_KIND_VISUALS: Record<GraphNodeKind, NodeKindVisual> = {
  agent: {
    icon: Bot,
    typeCaption: 'Agent',
    typeCaptionKey: 'agentCanvas.kinds.agent',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    accentHex: '#6366f1',
    emphasize: true,
  },
  service: {
    icon: Cpu,
    typeCaption: 'AI Service',
    typeCaptionKey: 'agentCanvas.kinds.service',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    // Deep navy: must read clearly apart from the agent's indigo bullet.
    accentHex: '#1e40af',
    emphasize: false,
  },
  silo: {
    icon: Database,
    typeCaption: 'Silo',
    typeCaptionKey: 'agentCanvas.kinds.silo',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    accentHex: '#d97706',
    emphasize: false,
  },
  embedding: {
    icon: Layers,
    typeCaption: 'Embedding',
    typeCaptionKey: 'agentCanvas.kinds.embedding',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    // Stronger cyan than the sibling cards: the embedding bullet/edge are the
    // same hue and the pale card read as "colorless" next to them.
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    accentHex: '#0891b2',
    emphasize: false,
  },
  skill: {
    icon: Sparkles,
    typeCaption: 'Skill',
    typeCaptionKey: 'agentCanvas.kinds.skill',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    accentHex: '#9333ea',
    emphasize: false,
  },
  mcp: {
    icon: Plug,
    typeCaption: 'MCP Config',
    typeCaptionKey: 'agentCanvas.kinds.mcp',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    accentHex: '#e11d48',
    emphasize: false,
  },
  parser: {
    icon: FileJson,
    typeCaption: 'Output Parser',
    typeCaptionKey: 'agentCanvas.kinds.parser',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    accentHex: '#475569',
    emphasize: false,
  },
};

/**
 * Per-agent canvas piece visuals, keyed by the ports model's `PieceKind`.
 * Kinds the app graph also renders reuse the same entry; sandbox services
 * and middlewares have no graph-node equivalent, so they carry their own
 * visuals here.
 */
export const PIECE_VISUALS: Record<PieceKind, NodeKindVisual> = {
  ai_service: NODE_KIND_VISUALS.service,
  embedding: NODE_KIND_VISUALS.embedding,
  sandbox: {
    icon: Container,
    typeCaption: 'Sandbox service',
    typeCaptionKey: 'agentCanvas.kinds.sandbox',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    accentHex: '#059669',
    emphasize: false,
  },
  silo: NODE_KIND_VISUALS.silo,
  skill: NODE_KIND_VISUALS.skill,
  mcp: NODE_KIND_VISUALS.mcp,
  agent: NODE_KIND_VISUALS.agent,
  parser: NODE_KIND_VISUALS.parser,
  middleware: {
    icon: ArrowLeftRight,
    typeCaption: 'Middleware',
    typeCaptionKey: 'agentCanvas.kinds.middleware',
    iconClass: 'text-bronze dark:text-bronze-dark',
    captionClass: 'text-fg-secondary dark:text-fg-secondary-dark',
    chipClass: 'bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark',
    borderClass: 'border-line dark:border-btCard-border-dark',
    bgClass: 'bg-surface dark:bg-surface-dark',
    accentHex: '#ea580c',
    emphasize: false,
  },
};
