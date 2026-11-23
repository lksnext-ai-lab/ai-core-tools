import { useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties, type ComponentType, type DragEvent, type PointerEvent } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  type Edge,
  type EdgeMouseHandler,
  type NodeMouseHandler,
  type NodeProps,
  type OnBeforeDelete,
  type OnConnect,
  type OnEdgesChange,
  type OnEdgesDelete,
  type OnInit,
  type OnNodeDrag,
  type OnNodesChange,
  type OnNodesDelete,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { apiService, ApiError, type AIService, type Agent } from '../../../services/api';
import { errorMessage, validationDetailMessage } from '../../../constants/messages';
import { PIECE_VISUALS } from '../nodeKindConfig';
import {
  buildPortPatch,
  connectedPieces,
  portsFor,
  resolveDropPort,
  type AgentType,
  type PieceKind,
  type PortDef,
  type PortId,
} from './agentPorts';
import { canConnect, canDisconnect } from './connectionRules';
import type { CanvasMessage } from './connectionRules';
import { layoutKey, loadLayout, saveLayout, type CanvasLayout, type StorageLike } from './canvasLayout';
import { createSaveQueue, planConnect, type SaveStep } from './savePlan';
import { AgentPortNode, type CanvasFlowNode } from './AgentPortNode';
import { PieceNode } from './PieceNode';
import { CanvasPalette, PIECE_DRAG_MIME, parsePieceDragPayload } from './CanvasPalette';
import { CanvasInspector } from './CanvasInspector';
import { CreatePieceModal } from './CreatePieceModal';
import { EditPieceModal } from './EditPieceModal';
import CompactServiceEditor from '../../services/CompactServiceEditor';
import { useServicesManager } from '../../../hooks/useServicesManager';
import { useSettingsCache } from '../../../contexts/SettingsCacheContext';
import type { LifecycleStatus, SandboxServiceFormData, ServiceFormData } from '../../../types/services';
import { useAgentCanvasData, type CanvasPiece } from './useAgentCanvasData';

/** What the inspector panel receives when something is selected. */
export type CanvasSelection =
  | { type: 'agent' }
  | { type: 'piece'; piece: CanvasPiece }
  | { type: 'edge'; port: PortId; piece: CanvasPiece };

/** Toast text for a failed canvas save: a 422's first validation message, else the error message or the fallback. */
/** Margin around the graph when fitting the view: small, so the nodes stay readable in the narrow canvas column. */
const FIT_PADDING = 0.06;

function saveErrorMessage(err: unknown, fallback: string): string {
  // A 422 carries the backend's validation message in `detail`, not in `message`.
  const validation = err instanceof ApiError && err.status === 422 ? validationDetailMessage(err.detail) : null;
  return validation ?? errorMessage(err, fallback);
}

export interface AgentCanvasProps {
  readonly appId: number;
  readonly agentId: number;
  /** False for roles below EDITOR: no connecting, no disconnecting (panning/dragging still works). */
  readonly canEdit: boolean;
  /**
   * True for ADMINISTRATOR and up: enables the palette `+` for the kinds that
   * create shared resources (AI services, embedding, sandbox, skills, MCP,
   * output parsers, middlewares). Silos and agents only need `canEdit`.
   */
  readonly canCreateShared?: boolean;
  /** Invoked with the selection on click; null when the pane is clicked. */
  readonly onSelect?: (selection: CanvasSelection | null) => void;
  /** Invoked after each successful save (connect, disconnect or inspector field), e.g. to refresh the page header. */
  readonly onSaved?: () => void;
}

interface CanvasEdgeData extends Record<string, unknown> {
  readonly port: PortId;
  readonly piece: CanvasPiece;
}

type CanvasEdge = Edge<CanvasEdgeData, 'default'>;

/**
 * A save step plus, when it targets the edited agent, the connection intent
 * behind it. The port patch is rebuilt from the freshly fetched agent inside
 * the queued task, so two rapid connects on the same port can't overwrite
 * each other's addition (`step.patch` still carries the plan's extras such
 * as `enable_code_interpreter`).
 */
interface CanvasSaveStep {
  readonly step: SaveStep;
  readonly connect?: { readonly port: PortId; readonly kind: PieceKind; readonly pieceId: number };
}

/** A piece dropped on the agent where several ports accept it: the user picks one. */
interface PendingChoice {
  readonly piece: CanvasPiece;
  readonly ports: readonly PortDef[];
}

/** Layout written during this session; wins over the stored copy for the same app+agent. */
interface EditedLayout {
  readonly scope: string;
  readonly layout: CanvasLayout;
}

/** Selected connection stroke (ink, like the app's selected states). */
const SELECTED_EDGE_COLOR = '#0f172a';

const NODE_TYPES: Record<string, ComponentType<NodeProps<CanvasFlowNode>>> = {
  agent: AgentPortNode,
  piece: PieceNode,
};

/** Column of pieces connected to primary ports (the agent's left border). */
const PIECE_COLUMN_X = -320;
/** Column of pieces connected to secondary ports (the agent's right border). */
const SECONDARY_COLUMN_X = 420;
/** Default column for loose pieces (no saved position), to the right of both columns. */
const LOOSE_COLUMN_X = 640;
const PIECE_ROW_HEIGHT = 90;

/** localStorage access itself can throw (blocked storage); the canvas works without it. */
function safeLocalStorage(): StorageLike | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Splits a piece node id (`${kind}:${id}`) back into its parts. */
function parsePieceNodeId(nodeId: string): { kind: PieceKind; id: number } | null {
  const separator = nodeId.indexOf(':');
  if (separator <= 0) return null;
  const kind = nodeId.slice(0, separator) as PieceKind;
  const id = Number.parseInt(nodeId.slice(separator + 1), 10);
  return Number.isNaN(id) ? null : { kind, id };
}

/** Node id of a piece card (`${kind}:${id}`), the same key the layout stores. */
function pieceNodeId(piece: Pick<CanvasPiece, 'kind' | 'id'>): string {
  return `${piece.kind}:${piece.id}`;
}

/** Pointer position of a React Flow drag event (mouse or touch); null when a touch drag has no coordinates. */
function dragPointerPoint(event: MouseEvent | TouchEvent): { x: number; y: number } | null {
  if (!('touches' in event)) return { x: event.clientX, y: event.clientY };
  const touch = event.changedTouches[0] ?? event.touches[0];
  return touch ? { x: touch.clientX, y: touch.clientY } : null;
}

/**
 * Default positions: the agent sits at the origin and its connected pieces
 * line up in one column to its left, grouped by port in `portsFor` order.
 * Loose pieces (on the canvas but unconnected) sit in a column to the right.
 * Positions saved in localStorage (from an earlier drag) override the default.
 */
export function buildFlowNodes(
  agent: Agent,
  agentType: AgentType,
  connected: ReadonlyArray<{ port: PortId; kind: PieceKind; id: number }>,
  pieces: readonly CanvasPiece[],
  savedPositions: Readonly<Record<string, { x: number; y: number }>>,
  canEdit: boolean,
  looseNodeIds: readonly string[],
  draggingKind: PieceKind | null,
  draggingSupportsVideo: boolean,
): CanvasFlowNode[] {
  const ports = portsFor(agentType);
  const portOrder = new Map(ports.map((port, index) => [port.id, index]));
  const byPieceId = new Map(pieces.map((piece) => [pieceNodeId(piece), piece]));

  const nodes: CanvasFlowNode[] = [
    {
      id: `agent:${agent.agent_id}`,
      type: 'agent',
      position: savedPositions[`agent:${agent.agent_id}`] ?? { x: 0, y: 0 },
      data: {
        label: agent.name,
        typeCaption: agentType === 'ocr_agent' ? 'OCR agent' : 'Agent',
        typeCaptionKey: agentType === 'ocr_agent' ? 'agentCanvas.kinds.ocrAgent' : 'agentCanvas.kinds.agent',
        ports: ports.filter((port) => !port.secondary),
        secondaryPorts: ports.filter((port) => port.secondary),
        isTool: agent.is_tool === true,
        draggingKind,
        draggingSupportsVideo,
      },
      // Nodes are never deletable here: resources are managed from their own pages.
      deletable: false,
      connectable: canEdit,
    },
  ];

  const ordered = [...connected].sort(
    (a, b) => (portOrder.get(a.port) ?? 0) - (portOrder.get(b.port) ?? 0) || a.id - b.id,
  );
  // One card per piece even when it feeds several ports (e.g. one AI service
  // on Model and Transcription); the port labels aggregate in port order.
  const portById = new Map(ports.map((port) => [port.id, port]));
  const deduped: Array<{ nodeId: string; piece: CanvasPiece; portLabels: string[]; primaryFed: boolean }> = [];
  const dedupeIndex = new Map<string, number>();
  for (const entry of ordered) {
    const piece = byPieceId.get(`${entry.kind}:${entry.id}`);
    if (!piece) continue;
    const nodeId = `${entry.kind}:${entry.id}`;
    const label = ports[portOrder.get(entry.port) ?? 0].label;
    // The card sits on the side of the ports it feeds (primary wins when both).
    const primaryFed = portById.get(entry.port)?.secondary !== true;
    const seenAt = dedupeIndex.get(nodeId);
    if (seenAt !== undefined) {
      deduped[seenAt].portLabels.push(label);
      deduped[seenAt].primaryFed ||= primaryFed;
      continue;
    }
    dedupeIndex.set(nodeId, deduped.length);
    deduped.push({ nodeId, piece, portLabels: [label], primaryFed });
  }
  const placeGroup = (group: typeof deduped, x: number) =>
    group.forEach((entry, index) => {
      nodes.push({
        id: entry.nodeId,
        type: 'piece',
        position: {
          x,
          // x is forced to the column matching the fed side so saved layouts
          // (localStorage) can't leave secondary pieces left of the agent.
          y: savedPositions[entry.nodeId]?.y ?? (index - (group.length - 1) / 2) * PIECE_ROW_HEIGHT,
        },
        data: { label: entry.piece.name, piece: entry.piece, portLabels: entry.portLabels },
        // Deletable only to disconnect: handleBeforeDelete maps the card to its
        // agent edges and never returns it as a removed node.
        deletable: canEdit,
        connectable: canEdit,
      });
    });
  placeGroup(deduped.filter((entry) => entry.primaryFed), PIECE_COLUMN_X);
  placeGroup(deduped.filter((entry) => !entry.primaryFed), SECONDARY_COLUMN_X);
  looseNodeIds.forEach((nodeId, index) => {
    const piece = byPieceId.get(nodeId);
    if (!piece) return;
    nodes.push({
      id: nodeId,
      type: 'piece',
      position: savedPositions[nodeId] ?? { x: LOOSE_COLUMN_X, y: index * PIECE_ROW_HEIGHT },
      data: { label: piece.name, piece, loose: true },
      // Loose pieces only leave the canvas (layout); they are deletable when editable.
      deletable: canEdit,
      connectable: canEdit,
    });
  });
  return nodes;
}

function makeCanvasEdge(args: {
  port: PortId;
  piece: CanvasPiece;
  targetId: string;
  /** Side of the piece card the edge leaves from: the one facing the port. */
  sourceHandle: string;
  id?: string;
  pending?: boolean;
}): CanvasEdge {
  const color = PIECE_VISUALS[args.piece.kind].accentHex;
  return {
    id: args.id ?? `${args.port}:${args.piece.kind}:${args.piece.id}`,
    source: `${args.piece.kind}:${args.piece.id}`,
    target: args.targetId,
    sourceHandle: args.sourceHandle,
    targetHandle: args.port,
    type: 'default',
    deletable: true,
    focusable: false,
    reconnectable: false,
    interactionWidth: 40,
    data: { port: args.port, piece: args.piece },
    style: { stroke: color, strokeWidth: 1.5, ...(args.pending ? { strokeDasharray: '6 4' } : {}) },
    markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
  };
}

function buildFlowEdges(
  agentNodeId: string,
  agentType: AgentType,
  connected: ReadonlyArray<{ port: PortId; kind: PieceKind; id: number }>,
  pieces: readonly CanvasPiece[],
): CanvasEdge[] {
  const byPieceId = new Map(pieces.map((piece) => [pieceNodeId(piece), piece]));
  const edges: CanvasEdge[] = [];
  for (const entry of connected) {
    const piece = byPieceId.get(`${entry.kind}:${entry.id}`);
    if (!piece) continue;
    // The edge leaves the card from the side facing its port's column.
    const sourceHandle = portsFor(agentType).find((port) => port.id === entry.port)?.secondary
      ? 'left'
      : 'right';
    edges.push(makeCanvasEdge({ port: entry.port, piece, targetId: agentNodeId, sourceHandle }));
  }
  return edges;
}

/**
 * Edges a Delete gesture must consider: the ones React Flow collected plus,
 * for every selected connected piece card, each edge that card holds to the
 * agent (React Flow's default path collects those too; the card's delete
 * must not depend on it). Deduped by edge id; loose cards hold no edges and
 * the agent body is never collected as a piece.
 */
export function deleteCandidateEdges(
  candidateNodes: CanvasFlowNode[],
  candidateEdges: CanvasEdge[],
  edges: CanvasEdge[],
  agentNodeId: string,
  looseNodeIds: readonly string[],
): CanvasEdge[] {
  const connectedPieces = new Set(
    candidateNodes
      .filter((node) => node.type === 'piece' && !looseNodeIds.includes(node.id))
      .map((node) => node.id),
  );
  if (connectedPieces.size === 0) return candidateEdges;
  const byId = new Map(candidateEdges.map((edge) => [edge.id, edge]));
  for (const edge of edges) {
    if (connectedPieces.has(edge.source) && edge.target === agentNodeId) byId.set(edge.id, edge);
  }
  return [...byId.values()];
}

function CanvasLoading() {
  const { t } = useTranslation('common');
  return (
    <div
      className="flex h-full w-full min-h-[400px] flex-col items-center justify-center gap-3 rounded-md border border-line bg-canvas-alt dark:border-btCard-border-dark dark:bg-canvas-alt-dark"
      role="status"
      aria-live="polite"
    >
      <Loader2
        className="h-8 w-8 animate-spin motion-reduce:animate-none text-accent dark:text-accent-dark"
        aria-hidden="true"
      />
      <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('agentCanvas.canvas.loading')}</p>
    </div>
  );
}

function CanvasError({ error, onRetry }: { readonly error: string; readonly onRetry: () => void }) {
  const { t } = useTranslation('common');
  return (
    <div
      className="flex h-full w-full min-h-[400px] flex-col items-center justify-center gap-3 rounded-md border border-error/40 bg-surface px-6 text-center dark:border-error-dark/40 dark:bg-surface-dark"
      role="alert"
      aria-live="assertive"
    >
      <AlertTriangle className="h-8 w-8 text-error dark:text-error-dark" aria-hidden="true" />
      <p className="max-w-md text-sm text-fg dark:text-fg-dark">{error}</p>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm font-medium text-fg transition-colors hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:border-btCard-border-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-btCard-hover"
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        {t('agentCanvas.canvas.tryAgain')}
      </button>
    </div>
  );
}

interface PortChooserProps {
  readonly name: string;
  readonly ports: readonly PortDef[];
  readonly onPick: (port: PortDef) => void;
  readonly onCancel: () => void;
}

/** Small card listing the ports a dropped piece can connect through. Escape or a click outside cancels. */
function PortChooser({ name, ports, onPick, onCancel }: PortChooserProps) {
  const { t } = useTranslation('common');
  const headingId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const firstPortRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    firstPortRef.current?.focus();
  }, []);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (event.target instanceof Node && containerRef.current?.contains(event.target)) return;
      onCancel();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onCancel]);

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-labelledby={headingId}
      className="absolute left-1/2 top-3 z-20 w-60 -translate-x-1/2 rounded-md border border-line bg-surface p-3 dark:border-btCard-border-dark dark:bg-surface-dark"
    >
      <p id={headingId} className="font-display text-sm font-medium text-fg dark:text-fg-dark">
        {t('agentCanvas.canvas.connectTo', { name })}
      </p>
      <div className="mt-2 flex flex-col gap-1">
        {ports.map((port, index) => (
          <button
            key={port.id}
            ref={index === 0 ? firstPortRef : undefined}
            type="button"
            onClick={() => onPick(port)}
            className="rounded-md px-3 py-1.5 text-left text-sm text-fg transition-colors hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:text-fg-dark dark:hover:bg-btCard-hover"
          >
            {t(`agentCanvas.ports.${port.id}`, { defaultValue: port.label })}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Draggable vertical strip next to a side panel: dragging it resizes that panel (desktop only). */
function PanelDivider(props: {
  readonly label: string;
  readonly onStart: (event: PointerEvent<HTMLDivElement>) => void;
  readonly onMove: (event: PointerEvent<HTMLDivElement>) => void;
  readonly onEnd: () => void;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={props.label}
      onPointerDown={props.onStart}
      onPointerMove={props.onMove}
      onPointerUp={props.onEnd}
      onLostPointerCapture={props.onEnd}
      className="hidden w-1 shrink-0 cursor-ew-resize touch-none select-none self-stretch rounded-full bg-transparent transition-colors hover:bg-line-strong md:block dark:hover:bg-btCard-border-dark"
    />
  );
}

/**
 * Per-agent visual canvas: the edited agent in the middle with one named
 * port per field it connects through, connected pieces around it, and
 * drag-to-connect/select+Delete editing backed by the pure ports model,
 * connection rules and save queue. Pieces dragged from the palette and
 * dropped on the agent connect; dropped elsewhere they stay as loose cards.
 * Layout (positions + loose pieces) lives only in localStorage; connections
 * save immediately, one step per gesture. The inspector on the right edits
 * the selected agent, piece or connection through the same save queue.
 */
export function AgentCanvas({ appId, agentId, canEdit, canCreateShared = false, onSelect, onSaved }: AgentCanvasProps) {
  const { t } = useTranslation('common');
  /** Translates a rule / save-plan message; `kind` and `port` params become the translated phrase and port label. */
  const formatMessage = useCallback(
    (message: CanvasMessage): string => {
      const { kind, port, portLabel, ...rest } = message.params ?? {};
      return t(message.key, {
        ...rest,
        ...(kind ? { kind: t(`agentCanvas.phrases.${kind}`) } : {}),
        ...(port ? { port: t(`agentCanvas.ports.${port}`, { defaultValue: portLabel ?? port }) } : {}),
      });
    },
    [t],
  );
  const { agent, pieces, toolEdges, loading, error, refetch } = useAgentCanvasData(appId, agentId);
  const storage = useMemo(safeLocalStorage, []);
  const queue = useMemo(() => createSaveQueue(), []);
  const scope = layoutKey(appId, agentId);

  const agentType: AgentType = agent?.type === 'ocr_agent' ? 'ocr_agent' : 'agent';
  const agentNodeId = agent ? `agent:${agent.agent_id}` : '';

  const connected = useMemo(
    () => (agent ? connectedPieces(agentType, agent) : []),
    [agent, agentType],
  );
  const connectedNodeIds = useMemo(
    () => new Set(connected.map((entry) => `${entry.kind}:${entry.id}`)),
    [connected],
  );

  const [editedLayout, setEditedLayout] = useState<EditedLayout | null>(null);

  // Saved layout scoped to this app+agent. Node ids include every existing
  // piece (not just connected ones) so a disconnected piece keeps its
  // position in storage and `loose` ids survive the round trip.
  const layout = useMemo<CanvasLayout>(() => {
    if (editedLayout?.scope === scope) return editedLayout.layout;
    if (!agent) return { positions: {}, loose: [] };
    const known = new Set<string>([agentNodeId, ...pieces.map((piece) => `${piece.kind}:${piece.id}`)]);
    return loadLayout(storage, appId, agentId, known);
  }, [agent, agentNodeId, pieces, storage, appId, agentId, scope, editedLayout]);

  /** Loose pieces that are still unconnected (a piece that got connected leaves the canvas as loose). */
  const looseNodeIds = useMemo(
    () => layout.loose.filter((nodeId) => !connectedNodeIds.has(nodeId)),
    [layout.loose, connectedNodeIds],
  );

  // Latest layout for callbacks that finish after an await (a connect's
  // save, a drag stop) so they never write back a stale copy.
  const layoutRef = useRef<CanvasLayout>(layout);
  useEffect(() => {
    layoutRef.current = layout;
  }, [layout]);

  /** Applies `mutate` to the latest layout, saves it and renders it. */
  const updateLayout = useCallback(
    (mutate: (current: CanvasLayout) => CanvasLayout) => {
      const next = mutate(layoutRef.current);
      layoutRef.current = next;
      saveLayout(storage, appId, agentId, next);
      setEditedLayout({ scope: layoutKey(appId, agentId), layout: next });
    },
    [storage, appId, agentId],
  );

  const [pendingEdges, setPendingEdges] = useState<CanvasEdge[]>([]);
  /** Gesture token for pending-edge ids, so one gesture's cleanup can't cross into another's. */
  const pendingSeq = useRef(0);

  /** Piece being dragged toward the canvas (palette or a loose card), for the port drop highlights. */
  const [draggingPiece, setDraggingPiece] = useState<CanvasPiece | null>(null);
  const draggingKind = draggingPiece?.kind ?? null;
  const draggingSupportsVideo = draggingPiece?.supportsVideo === true;

  const canvasRef = useRef<HTMLDivElement>(null);

  // Desktop widths of the two side panels; the thin dividers next to them drag-resize them.
  const [paletteWidth, setPaletteWidth] = useState(224);
  const [inspectorWidth, setInspectorWidth] = useState(320);
  const panelDrag = useRef<null | { readonly side: 'palette' | 'inspector'; readonly startX: number; readonly start: number }>(null);
  const startPanelResize = useCallback(
    (side: 'palette' | 'inspector') => (event: PointerEvent<HTMLDivElement>) => {
      panelDrag.current = { side, startX: event.clientX, start: side === 'palette' ? paletteWidth : inspectorWidth };
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    [paletteWidth, inspectorWidth],
  );
  const movePanelResize = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const drag = panelDrag.current;
    if (!drag) return;
    const delta = drag.side === 'palette' ? event.clientX - drag.startX : drag.startX - event.clientX;
    const min = drag.side === 'palette' ? 180 : 280;
    const max = drag.side === 'palette' ? 420 : 560;
    const next = Math.min(max, Math.max(min, drag.start + delta));
    (drag.side === 'palette' ? setPaletteWidth : setInspectorWidth)(next);
  }, []);
  const endPanelResize = useCallback(() => {
    panelDrag.current = null;
  }, []);

  const flowNodes = useMemo(
    () =>
      agent
        ? buildFlowNodes(
            agent,
            agentType,
            connected,
            pieces,
            layout.positions,
            canEdit,
            looseNodeIds,
            draggingKind,
            draggingSupportsVideo,
          )
        : [],
    [
      agent,
      agentType,
      connected,
      pieces,
      layout.positions,
      canEdit,
      looseNodeIds,
      draggingKind,
      draggingSupportsVideo,
    ],
  );

  const flowEdges = useMemo(
    () => (agent ? buildFlowEdges(agentNodeId, agentType, connected, pieces) : []),
    [agent, agentNodeId, agentType, connected, pieces],
  );

  // Local, draggable copies of the adapted nodes/edges - same pattern as the
  // old app-wide canvas: React Flow owns position/selection between
  // re-renders, and a resync preserves the live values.
  const [nodes, setNodes] = useState<CanvasFlowNode[]>([]);
  const nodesRef = useRef<readonly CanvasFlowNode[]>(nodes);
  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    setNodes((current) => {
      const byId = new Map(current.map((node) => [node.id, node]));
      return flowNodes.map((node) => {
        const existing = byId.get(node.id);
        return existing ? { ...node, position: existing.position } : node;
      });
    });
  }, [flowNodes]);

  const [edges, setEdges] = useState<CanvasEdge[]>([]);
  useEffect(() => {
    setEdges((current) => {
      const byId = new Map(current.map((edge) => [edge.id, edge]));
      return [...flowEdges, ...pendingEdges].map((edge) => {
        const existing = byId.get(edge.id);
        return existing ? { ...edge, selected: existing.selected } : edge;
      });
    });
  }, [flowEdges, pendingEdges]);

  // A failed background refetch (canvas already populated) keeps the live
  // view and reports through a toast; the full error screen is only for the
  // initial load.
  useEffect(() => {
    if (error && agent) toast.error(error);
  }, [error, agent]);

  /** Flow instance, captured on init: screen-to-flow conversion and hit tests for drops. */
  const flowRef = useRef<ReactFlowInstance<CanvasFlowNode, CanvasEdge> | null>(null);
  const handleInit: OnInit<CanvasFlowNode, CanvasEdge> = useCallback((instance) => {
    flowRef.current = instance;
  }, []);
  /** Node id of the piece set by a connect: once that node is on the canvas the view re-fits so it isn't left off screen. */
  const fitOnNextNodes = useRef<string | null>(null);
  useEffect(() => {
    const nodeId = fitOnNextNodes.current;
    // Not a boolean: clearing drag state on drop also changes `nodes` before
    // the refetch adds the piece node, so the fit must wait for that node itself.
    if (!nodeId || !nodes.some((node) => node.id === nodeId)) return;
    fitOnNextNodes.current = null;
    // Wait a beat so React Flow has measured the new node before fitting; an earlier fit ignores it.
    setTimeout(() => void flowRef.current?.fitView({ padding: FIT_PADDING, duration: 300 }), 150);
  }, [nodes]);

  const [choice, setChoice] = useState<PendingChoice | null>(null);
  const cancelChoice = useCallback(() => setChoice(null), []);
  /**
   * Creation flow in progress: the kind plus, when it was opened from a port
   * row's «+», the port the new piece must connect to.
   */
  const [creating, setCreating] = useState<{ readonly kind: PieceKind; readonly port?: PortDef } | null>(null);
  const closeCreate = useCallback(() => setCreating(null), []);
  /** Piece being edited in the overlay wizard (skill, MCP, middleware, services, output parser). */
  const [editingPiece, setEditingPiece] = useState<CanvasPiece | null>(null);
  /** AI service editing reuses the same manager (api, cache, toasts, save) the settings page uses, so an edit behaves identically in both. */
  const settingsCache = useSettingsCache();
  const servicesApi = {
    getAll: (id: number) => apiService.getAIServices(id),
    getOne: (id: number, sid: number) => apiService.getAIService(id, sid),
    create: (id: number, data: any) => apiService.createAIService(id, data),
    update: (id: number, sid: number, data: any) => apiService.updateAIService(id, sid, data),
    delete: (id: number, sid: number) => apiService.deleteAIService(id, sid),
  };
  const servicesCache = {
    get: (id: string) => settingsCache.getAIServices(id),
    set: (id: string, data: AIService[]) => settingsCache.setAIServices(id, data),
    invalidate: (id: string) => settingsCache.invalidateAIServices(id),
  };
  const {
    services,
    isModalOpen,
    editingService,
    handleEdit,
    handleSave,
    handleClose,
    setIsModalOpen,
    setEditingService,
  } = useServicesManager<AIService>(String(appId), servicesApi, servicesCache, { entity: 'AI service' });
  /** Opens the AI service editor for a canvas piece; the manager loads the full service detail first. */
  const handleEditService = useCallback(
    (piece: CanvasPiece) => {
      if (piece.kind !== 'ai_service') return;
      void handleEdit(piece.id);
    },
    [handleEdit],
  );
  /** A service edit saved: the manager closed the editor, the canvas reloads its pieces. */
  const handleSaveService = useCallback(
    async (data: ServiceFormData | SandboxServiceFormData): Promise<void> => {
      await handleSave(data);
      void refetch();
    },
    [handleSave, refetch],
  );
  /** Port row whose «+» popover is open, anchored at container-relative coordinates. */
  // The chooser, the creation, the edit modals and the selection belong to the agent they were opened for.
  useEffect(() => {
    setChoice(null);
    setCreating(null);
    setIsModalOpen(false);
    setEditingService(null);
    setEditingPiece(null);
    setDraggingPiece(null);
  }, [agentId]);

  // The selection belongs to the agent it was made for; the inspector only
  // shows it while its piece is still on the canvas and its connection still exists.
  const [selectionState, setSelectionState] = useState<{ agentId: number; selection: CanvasSelection } | null>(null);
  const selectCanvas = useCallback(
    (selection: CanvasSelection | null) => {
      setSelectionState(selection ? { agentId, selection } : null);
      onSelect?.(selection);
    },
    [agentId, onSelect],
  );
  const resolvedSelection = useMemo<CanvasSelection | null>(() => {
    if (!selectionState || selectionState.agentId !== agentId || !agent) return null;
    const selected = selectionState.selection;
    if (selected.type === 'agent') return selected;
    const piece = pieces.find((entry) => entry.kind === selected.piece.kind && entry.id === selected.piece.id);
    if (!piece) return null;
    if (selected.type === 'piece') return { type: 'piece', piece };
    const stillConnected = connected.some(
      (entry) => entry.port === selected.port && entry.kind === piece.kind && entry.id === piece.id,
    );
    return stillConnected ? { type: 'edge', port: selected.port, piece } : null;
  }, [selectionState, agentId, agent, pieces, connected]);

  /** Node id of the selected piece (piece or edge selection), so the palette can highlight it. */
  const selectedPieceId = useMemo(
    () =>
      resolvedSelection && resolvedSelection.type !== 'agent'
        ? `${resolvedSelection.piece.kind}:${resolvedSelection.piece.id}`
        : null,
    [resolvedSelection],
  );

  /**
   * Removes a node from the live copy so the next sync re-adds it at its
   * layout position: the sync keeps live positions for nodes it already has.
   */
  const reseatNode = useCallback((nodeId: string) => {
    setNodes((current) => current.filter((node) => node.id !== nodeId));
  }, []);

  const onNodesChange: OnNodesChange<CanvasFlowNode> = useCallback((changes) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const onEdgesChange: OnEdgesChange<CanvasEdge> = useCallback((changes) => {
    setEdges((current) => applyEdgeChanges(changes, current));
  }, []);

  /**
   * Saves `steps` one at a time (fetch → merge patch → update), stopping at the first failure; then refetches.
   * Resolves true when every step saved. `failureLabel` names what failed in the error toast.
   */
  const runSteps = useCallback(
    async (steps: readonly CanvasSaveStep[], failureLabel: 'connection' | 'agent' = 'connection'): Promise<boolean> => {
      let saved = true;
      for (const { step, connect } of steps) {
        try {
          await queue.run(step.agentId, async () => {
            const fresh = await apiService.getAgent(appId, step.agentId);
            // Rebuild the port patch from the fresh agent so rapid gestures on
            // the same port don't overwrite each other; step.patch still
            // carries the plan's extras (enable_code_interpreter).
            const patch = connect
              ? { ...step.patch, ...buildPortPatch(fresh, connect.port, connect.kind, connect.pieceId, 'add') }
              : step.patch;
            await apiService.updateAgent(appId, step.agentId, { ...fresh, ...patch });
            if (step.toast) toast.success(formatMessage(step.toast) + (step.toastSuffix ? formatMessage(step.toastSuffix) : ''));
          });
        } catch (err) {
          toast.error(saveErrorMessage(err, t(`agentCanvas.save.${failureLabel}Failed`)));
          saved = false;
          break;
        }
      }
      await refetch();
      if (saved) onSaved?.();
      return saved;
    },
    [appId, queue, refetch, onSaved, formatMessage, t],
  );

  /** Inspector field saves: one step through the same queue and executor as the connects. */
  const saveAgentFields = useCallback(
    (patch: Record<string, unknown>): Promise<boolean> => runSteps([{ step: { agentId, patch } }], 'agent'),
    [agentId, runSteps],
  );

  /**
   * The one connect path: every gesture that connects a piece (a handle drag
   * or a drop on the agent) ends here. Rule check, then the planned saves are
   * queued and refetched; a loose piece leaves `loose` once its save succeeds.
   * `toastSuffix` extends the success toast (a drop hint for other ports).
   */
  const connectPiece = useCallback(
    (port: PortDef, piece: CanvasPiece, toastSuffix?: CanvasMessage): void => {
      if (!agent) return;
      if (connected.some((entry) => entry.port === port.id && entry.kind === piece.kind && entry.id === piece.id)) {
        toast.info(t('agentCanvas.canvas.alreadyConnected', { name: piece.name }));
        return;
      }
      const result = canConnect({
        canEdit,
        agentId: agent.agent_id,
        agentType,
        hasMemory: agent.has_memory === true,
        port,
        kind: piece.kind,
        pieceId: piece.id,
        lifecycleStatus: piece.lifecycleStatus,
        supportsVideo: piece.supportsVideo,
        toolEdges,
      });
      if (result.ok === false) {
        toast.error(formatMessage(result.reason));
        return;
      }
      if (result.warning) toast.warning(formatMessage(result.warning));

      const patch = buildPortPatch(agent, port.id, piece.kind, piece.id, 'add');
      const replaced = port.multiple
        ? null
        : connected.find((entry) => entry.port === port.id && entry.id !== piece.id);
      const replacedName = replaced
        ? (pieces.find((entry) => entry.kind === replaced.kind && entry.id === replaced.id)?.name ?? null)
        : null;
      // planConnect decides the steps and toasts; steps for the edited agent
      // carry the connection intent so runSteps rebuilds the port patch from
      // the fresh agent inside the queue (the is_tool step saves another
      // agent and keeps its patch as is).
      const steps: CanvasSaveStep[] = planConnect({
        agentId: agent.agent_id,
        port: port.id,
        kind: piece.kind,
        pieceId: piece.id,
        patch,
        targetIsTool: piece.isTool,
        codeInterpreterOn: agent.enable_code_interpreter === true,
        replacedName,
        toastSuffix,
        pieceName: piece.name,
      }).map((step) =>
        step.agentId === agent.agent_id
          ? { step, connect: { port: port.id, kind: piece.kind, pieceId: piece.id } }
          : { step },
      );

      // Unique id per gesture: one gesture's cleanup must never remove
      // another gesture's still-in-flight pending edge.
      pendingSeq.current += 1;
      const pendingId = `pending:${port.id}:${piece.kind}:${piece.id}:${pendingSeq.current}`;
      setPendingEdges((current) => [
        ...current,
        makeCanvasEdge({
          port: port.id,
          piece,
          targetId: agentNodeId,
          sourceHandle: port.secondary ? 'left' : 'right',
          id: pendingId,
          pending: true,
        }),
      ]);

      const nodeId = pieceNodeId(piece);
      fitOnNextNodes.current = nodeId;
      void runSteps(steps)
        .then((saved) => {
          if (saved && layoutRef.current.loose.includes(nodeId)) {
            updateLayout((current) => ({
              positions: current.positions,
              loose: current.loose.filter((id) => id !== nodeId),
            }));
          }
        })
        .finally(() => {
          setPendingEdges((current) => current.filter((edge) => edge.id !== pendingId));
        });
    },
    [agent, agentNodeId, agentType, pieces, canEdit, toolEdges, connected, runSteps, updateLayout, t, formatMessage],
  );

  /** A piece dropped on the agent body: one matching port connects directly, several open the chooser, none is refused. */
  const dropOnAgent = useCallback(
    (piece: CanvasPiece): void => {
      const target = resolveDropPort(agentType, piece.kind);
      if (target === null) {
        toast.error(t('agentCanvas.canvas.cannotConnect', { kind: t(`agentCanvas.phrases.${piece.kind}`) }));
        return;
      }
      const ports = portsFor(agentType);
      if (target === 'ask') {
        setChoice({ piece, ports: ports.filter((port) => port.accepts.includes(piece.kind)) });
        return;
      }
      const port = ports.find((entry) => entry.id === target);
      if (!port) return;
      // An AI service landing on the default Model port still has to be
      // dropped on Transcription/Video explicitly; nudge when either is empty.
      const toastSuffix =
        target === 'model' && piece.kind === 'ai_service' && !connected.some((entry) => entry.port === 'transcription' || entry.port === 'video')
          ? { key: 'agentCanvas.save.dropHint' }
          : undefined;
      connectPiece(port, piece, toastSuffix);
    },
    [agentType, connected, connectPiece, t],
  );

  const handleChoosePort = useCallback(
    (port: PortDef) => {
      if (!choice) return;
      setChoice(null);
      connectPiece(port, choice.piece);
    },
    [choice, connectPiece],
  );

  /**
   * A piece saved from a «+»: refetch so it is in the pieces list, then place
   * it the way a drop would. A piece no port takes stays as a loose card; any
   * other piece goes through the same drop path (direct connect or chooser) —
   * unless the «+» sat on a port row, which connects the piece to that port.
   */
  const handlePieceCreated = useCallback(
    async (
      kind: PieceKind,
      id: number,
      name: string,
      lifecycleStatus?: LifecycleStatus,
      supportsVideo?: boolean,
      port?: PortDef,
    ): Promise<void> => {
      setCreating(null);
      await refetch();
      // A new agent is never a tool yet, so connecting it through Tools adds is_tool first.
      const piece: CanvasPiece = {
        kind,
        id,
        name,
        ...(kind === 'agent' ? { isTool: false } : {}),
        ...(lifecycleStatus ? { lifecycleStatus } : {}),
        ...(kind === 'ai_service' && supportsVideo !== undefined ? { supportsVideo } : {}),
      };
      if (port) {
        connectPiece(port, piece);
        return;
      }
      if (resolveDropPort(agentType, kind) === null) {
        const nodeId = pieceNodeId(piece);
        updateLayout((current) => ({
          positions: current.positions,
          loose: current.loose.includes(nodeId) ? current.loose : [...current.loose, nodeId],
        }));
        return;
      }
      dropOnAgent(piece);
    },
    [agentType, refetch, dropOnAgent, updateLayout, connectPiece],
  );

  /** True when `point` (flow coordinates) lies on the agent node. */
  const isOverAgent = useCallback(
    (point: { x: number; y: number }): boolean => {
      const instance = flowRef.current;
      if (!instance || !agentNodeId) return false;
      return instance
        .getIntersectingNodes({ x: point.x, y: point.y, width: 1, height: 1 })
        .some((node) => node.id === agentNodeId);
    },
    [agentNodeId],
  );

  /**
   * Port row under the pointer, scoped to the agent node. `hidden` is the
   * piece card being dragged by the pointer: it sits under the cursor at drag
   * stop and would shadow the row underneath, so it is lifted out of the hit
   * test for the duration of the call.
   */
  const portRowAtPoint = useCallback((x: number, y: number, hidden?: HTMLElement | null): PortId | null => {
    if (hidden) hidden.style.pointerEvents = 'none';
    try {
      const row = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-agent-node] [data-port-id]');
      return row ? ((row.dataset.portId as PortId) ?? null) : null;
    } finally {
      if (hidden) hidden.style.pointerEvents = '';
    }
  }, []);

  /** A loose card drag starts: the ports that would take it light up. */
  const handleNodeDragStart: OnNodeDrag<CanvasFlowNode> = useCallback(
    (_event, node) => {
      if (looseNodeIds.includes(node.id) && node.data.piece) setDraggingPiece(node.data.piece);
    },
    [looseNodeIds],
  );

  const handleNodeDragStop: OnNodeDrag<CanvasFlowNode> = useCallback(
    (event, draggedNode) => {
      setDraggingPiece(null);
      const positions: Record<string, { x: number; y: number }> = {};
      for (const node of nodesRef.current) {
        positions[node.id] = node.id === draggedNode.id ? draggedNode.position : node.position;
      }
      // A loose piece dragged over the agent connects. Its saved position is
      // dropped so it lands in the default column once connected.
      const piece = draggedNode.data.piece;
      const isLoosePiece = canEdit && piece !== undefined && looseNodeIds.includes(draggedNode.id);
      const center = {
        x: draggedNode.position.x + (draggedNode.measured?.width ?? 0) / 2,
        y: draggedNode.position.y + (draggedNode.measured?.height ?? 0) / 2,
      };
      const droppedOnAgent = isLoosePiece && isOverAgent(center);
      // A drop aimed at a specific port row connects there directly.
      let rowPort: PortDef | null = null;
      if (isLoosePiece) {
        const point = dragPointerPoint(event);
        if (point) {
          const draggedEl = document.querySelector<HTMLElement>(
            `.react-flow__node[data-id="${draggedNode.id}"]`,
          );
          const portId = portRowAtPoint(point.x, point.y, draggedEl);
          if (portId) rowPort = portsFor(agentType).find((entry) => entry.id === portId) ?? null;
        }
      }
      updateLayout((current) => {
        const merged = { ...current.positions, ...positions };
        if (droppedOnAgent || rowPort) delete merged[draggedNode.id];
        return { positions: merged, loose: current.loose };
      });
      if (droppedOnAgent || rowPort) reseatNode(draggedNode.id);
      if (rowPort && piece) {
        // A port row that doesn't take the piece falls back to the body drop
        // (single-possible-port pieces snap to that port instead of erroring).
        if (rowPort.accepts.includes(piece.kind)) {
          connectPiece(rowPort, piece);
        } else {
          dropOnAgent(piece);
        }
        return;
      }
      if (droppedOnAgent && piece) dropOnAgent(piece);
    },
    [canEdit, looseNodeIds, isOverAgent, reseatNode, dropOnAgent, updateLayout, agentType, portRowAtPoint, connectPiece],
  );

  const handleConnect: OnConnect = useCallback(
    (connection) => {
      if (!agent) return;
      // The agent body is always the edge target; normalize either drag direction.
      const toAgent = connection.target === agentNodeId;
      const fromAgent = connection.source === agentNodeId;
      const pieceNode = toAgent ? connection.source : fromAgent ? connection.target : null;
      const rawPortId = toAgent ? connection.targetHandle : fromAgent ? connection.sourceHandle : null;
      if (!pieceNode) return;
      const parsed = parsePieceNodeId(pieceNode);
      const piece = parsed
        ? pieces.find((entry) => entry.kind === parsed.kind && entry.id === parsed.id)
        : undefined;
      if (!parsed || !piece) return;
      const port = portsFor(agentType).find((entry) => entry.id === (rawPortId as PortId));
      if (port && port.accepts.includes(piece.kind)) {
        connectPiece(port, piece);
        return;
      }
      // No handle (dropped on the body) or an incompatible one: resolve like a
      // body drop, so single-possible-port pieces still snap to their port.
      dropOnAgent(piece);
    },
    [agent, agentNodeId, agentType, pieces, connectPiece, dropOnAgent],
  );

  const handleBeforeDelete: OnBeforeDelete<CanvasFlowNode, CanvasEdge> = useCallback(
    async ({ nodes: candidateNodes, edges: candidateEdges }) => {
      const ports = agent ? portsFor(agentType) : [];
      // A connected piece card must delete exactly like its connection line:
      // every edge it holds to the agent joins the candidates (deduped), so
      // the same checks and save path apply.
      const candidates = deleteCandidateEdges(candidateNodes, candidateEdges, edges, agentNodeId, looseNodeIds);
      const allowed: CanvasEdge[] = [];
      const blockedReasons = new Set<string>();
      for (const edge of candidates) {
        // A pending (not yet saved) edge must not be disconnected: on a
        // single-valued port the remove patch would null the field and wipe
        // the connection that is already there. It disappears on its own
        // once the gesture's save settles.
        if (edge.id.startsWith('pending:')) continue;
        const port = edge.data ? ports.find((entry) => entry.id === edge.data?.port) : undefined;
        if (!agent || !port) continue;
        const result = canDisconnect({ canEdit, agentType, hasMemory: agent.has_memory === true, port });
        if (result.ok === false) {
          blockedReasons.add(formatMessage(result.reason));
          continue;
        }
        allowed.push(edge);
      }
      for (const reason of blockedReasons) toast.error(reason);
      // Only loose pieces may be removed, and only from the canvas: no API call.
      const looseNodes = canEdit
        ? candidateNodes.filter((node) => node.type === 'piece' && looseNodeIds.includes(node.id))
        : [];
      return { nodes: looseNodes, edges: allowed };
    },
    [agent, agentType, canEdit, looseNodeIds, edges, agentNodeId, formatMessage],
  );

  const handleNodesDelete: OnNodesDelete<CanvasFlowNode> = useCallback(
    (removed) => {
      const removedIds = new Set(removed.map((node) => node.id));
      updateLayout((current) => ({
        positions: current.positions,
        loose: current.loose.filter((id) => !removedIds.has(id)),
      }));
    },
    [updateLayout],
  );

  const handleEdgesDelete: OnEdgesDelete<CanvasEdge> = useCallback(
    (removed) => {
      if (!agent) return;
      const ports = portsFor(agentType);
      const removedData = removed.flatMap((edge) => (edge.data ? [edge.data] : []));
      if (removedData.length === 0) return;
      let succeeded = false;
      void (async () => {
        for (const data of removedData) {
          const port = ports.find((entry) => entry.id === data.port);
          if (!port) continue;
          try {
            const saved = await queue.run(agent.agent_id, async () => {
              const fresh = await apiService.getAgent(appId, agent.agent_id);
              const patch = buildPortPatch(fresh, port.id, data.piece.kind, data.piece.id, 'remove');
              // Nothing to clear: the piece was already replaced or removed on the fresh agent.
              if (Object.keys(patch).length === 0) return false;
              await apiService.updateAgent(appId, agent.agent_id, { ...fresh, ...patch });
              return true;
            });
            if (saved) succeeded = true;
          } catch (err) {
            toast.error(saveErrorMessage(err, t('agentCanvas.save.connectionFailed')));
          }
        }
        if (succeeded) {
          toast.success(t('agentCanvas.save.connectionUpdated'));
          onSaved?.();
        }
        await refetch();
      })();
    },
    [agent, agentType, appId, queue, refetch, onSaved, t],
  );

  const handleDragOver = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (!canEdit || !event.dataTransfer.types.includes(PIECE_DRAG_MIME)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
    },
    [canEdit],
  );

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      const payload = parsePieceDragPayload(event.dataTransfer.getData(PIECE_DRAG_MIME));
      if (!canEdit || !agent || !payload) return;
      event.preventDefault();
      // A new drop replaces any chooser still open from an earlier gesture.
      setChoice(null);
      setDraggingPiece(null);
      const piece = pieces.find((entry) => entry.kind === payload.kind && entry.id === payload.id);
      const instance = flowRef.current;
      if (!piece || !instance) return;
      // A drop on a specific port row connects there — but only when that port
      // takes the piece; anything else falls through to the body drop, where
      // single-possible-port pieces snap to their port instead of erroring.
      const portId = portRowAtPoint(event.clientX, event.clientY);
      if (portId) {
        const port = portsFor(agentType).find((entry) => entry.id === portId);
        if (port && piece && port.accepts.includes(piece.kind)) {
          connectPiece(port, piece);
          return;
        }
      }
      const point = instance.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      if (isOverAgent(point)) {
        dropOnAgent(piece);
        return;
      }
      // Dropped elsewhere: the piece stays on the canvas as a loose card. A
      // piece that is already connected is already on the canvas.
      const nodeId = pieceNodeId(piece);
      if (connectedNodeIds.has(nodeId)) {
        toast.info(t('agentCanvas.canvas.alreadyOnCanvas', { name: piece.name }));
        return;
      }
      reseatNode(nodeId);
      updateLayout((current) => ({
        positions: { ...current.positions, [nodeId]: point },
        loose: current.loose.includes(nodeId) ? current.loose : [...current.loose, nodeId],
      }));
    },
    [canEdit, agent, pieces, connectedNodeIds, isOverAgent, reseatNode, dropOnAgent, updateLayout, agentType, portRowAtPoint, connectPiece, t],
  );

  const handleCreate = useCallback((kind: PieceKind) => setCreating({ kind }), []);

  const handleNodeClick: NodeMouseHandler<CanvasFlowNode> = useCallback(
    (_event, node) => {
      if (node.type === 'agent') {
        selectCanvas({ type: 'agent' });
        return;
      }
      if (node.data.piece) selectCanvas({ type: 'piece', piece: node.data.piece });
    },
    [selectCanvas],
  );

  const handleEdgeClick: EdgeMouseHandler<CanvasEdge> = useCallback(
    (_event, edge) => {
      if (edge.data) selectCanvas({ type: 'edge', port: edge.data.port, piece: edge.data.piece });
    },
    [selectCanvas],
  );

  const handlePaneClick = useCallback(() => {
    selectCanvas(null);
  }, [selectCanvas]);

  // Inline `style` outranks React Flow's `.selected` CSS class, so overlay a
  // bold consistent "selected" look at render time (same as the old canvas).
  const styledEdges = useMemo(
    () =>
      edges.map((edge) =>
        edge.selected
          ? {
              ...edge,
              style: { ...edge.style, stroke: SELECTED_EDGE_COLOR, strokeWidth: 3 },
              markerEnd:
                typeof edge.markerEnd === 'object' && edge.markerEnd !== null
                  ? { ...edge.markerEnd, color: SELECTED_EDGE_COLOR }
                  : edge.markerEnd,
            }
          : edge,
      ),
    [edges],
  );

  // Only show the full-screen loading state on the genuinely-empty initial
  // load; a background refetch must never unmount the flow (same as the old
  // canvas - it would reset the viewport on every connect/disconnect).
  if (loading && !agent) return <CanvasLoading />;
  if (error && !agent) return <CanvasError error={error} onRetry={refetch} />;
  if (!agent) return <CanvasLoading />;

  return (
    <div className="flex w-full flex-col gap-3 md:h-full md:flex-row">
      <CanvasPalette
        style={{ '--palette-w': `${paletteWidth}px` } as CSSProperties}
        pieces={pieces}
        agentType={agentType}
        canEdit={canEdit}
        canCreateShared={canCreateShared}
        selectedPieceId={selectedPieceId}
        onCreate={handleCreate}
        onSelectPiece={(piece) => selectCanvas({ type: 'piece', piece })}
        onDraggingChange={setDraggingPiece}
      />
      <PanelDivider
        label={t('agentCanvas.canvas.resizePalette')}
        onStart={startPanelResize('palette')}
        onMove={movePanelResize}
        onEnd={endPanelResize}
      />
      <div
        ref={canvasRef}
        className="relative h-[70vh] w-full min-h-[400px] min-w-0 flex-1 md:h-full overflow-hidden rounded-md border border-line bg-canvas-alt dark:border-btCard-border-dark dark:bg-canvas-alt-dark"
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <h2 className="sr-only">{t('agentCanvas.canvas.title')}</h2>
        <ReactFlow<CanvasFlowNode, CanvasEdge>
          nodes={nodes}
          edges={styledEdges}
          nodeTypes={NODE_TYPES}
          onInit={handleInit}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeDragStart={handleNodeDragStart}
          onNodeDragStop={handleNodeDragStop}
          onConnect={handleConnect}
          onBeforeDelete={handleBeforeDelete}
          onNodesDelete={handleNodesDelete}
          onEdgesDelete={handleEdgesDelete}
          onNodeClick={handleNodeClick}
          onEdgeClick={handleEdgeClick}
          onPaneClick={handlePaneClick}
          nodesConnectable={canEdit}
          elementsSelectable
          nodesDraggable
          // react-flow's default (0px) requires the pointer to not move AT ALL
          // between mousedown and mouseup to register a click.
          nodeClickDistance={10}
          nodesFocusable={false}
          edgesReconnectable={false}
          edgesFocusable={false}
          deleteKeyCode={['Delete', 'Backspace']}
          proOptions={{ hideAttribution: true }}
          fitView
          fitViewOptions={{ padding: FIT_PADDING }}
          minZoom={0.2}
          maxZoom={1.5}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} className="!text-line dark:!text-btCard-border-dark" />
          <MiniMap
            pannable
            zoomable
            bgColor="transparent"
            maskColor="rgba(128, 128, 128, 0.18)"
            className="!bg-surface dark:!bg-surface-dark !border !border-line dark:!border-btCard-border-dark [&_.react-flow__minimap-mask]:!fill-line/60 dark:[&_.react-flow__minimap-mask]:!fill-btCard-border-dark/60"
          />
          <Controls showInteractive={false} className="[&_button]:!bg-surface [&_button]:dark:!bg-surface-dark [&_button]:!border-line [&_button]:dark:!border-btCard-border-dark [&_button]:dark:!fill-fg-dark" />
        </ReactFlow>
        {choice && (
          <PortChooser
            name={choice.piece.name}
            ports={choice.ports}
            onPick={handleChoosePort}
            onCancel={cancelChoice}
          />
        )}
      </div>
      <PanelDivider
        label={t('agentCanvas.canvas.resizeInspector')}
        onStart={startPanelResize('inspector')}
        onMove={movePanelResize}
        onEnd={endPanelResize}
      />
      <CanvasInspector
        style={{ '--inspector-w': `${inspectorWidth}px` } as CSSProperties}
        appId={appId}
        agent={agent}
        agentType={agentType}
        selection={resolvedSelection}
        canEdit={canEdit}
        canCreateShared={canCreateShared}
        onEditService={handleEditService}
        onEditPiece={setEditingPiece}
        onSaveFields={saveAgentFields}
      />
      {creating && (
        <CreatePieceModal
          appId={appId}
          kind={creating.kind}
          onClose={closeCreate}
          onCreated={(kind, id, name, lifecycleStatus, supportsVideo) =>
            void handlePieceCreated(kind, id, name, lifecycleStatus, supportsVideo, creating.port)
          }
        />
      )}
      {editingPiece && (
        <EditPieceModal
          appId={appId}
          piece={editingPiece}
          onClose={() => setEditingPiece(null)}
          onSaved={() => {
            setEditingPiece(null);
            void refetch();
          }}
        />
      )}
      {isModalOpen && editingService && (
        <CompactServiceEditor
          isOpen
          kind="ai"
          scope="app"
          appId={appId}
          service={editingService}
          existingNames={services.map((s) => s.name)}
          onClose={handleClose}
          onSave={handleSaveService}
        />
      )}
    </div>
  );
}
