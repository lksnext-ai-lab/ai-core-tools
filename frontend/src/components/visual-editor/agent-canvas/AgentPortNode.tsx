import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { useTranslation } from 'react-i18next';
import { KindIcon } from './KindIcon';
import { NODE_KIND_VISUALS, PIECE_VISUALS } from '../nodeKindConfig';
import type { PieceKind, PortDef } from './agentPorts';
import type { CanvasPiece } from './useAgentCanvasData';

/**
 * Data payload carried by every node on the per-agent canvas. Fields are
 * optional and only the ones for the node's `type` are set, so the agent
 * body and the piece cards share one data shape.
 */
export interface CanvasNodeData extends Record<string, unknown> {
  readonly label: string;
  /** Caption under the label ("Agent" / "OCR agent"; piece cards use the kind caption). */
  readonly typeCaption?: string;
  /** i18n key (agentCanvas.kinds.*) for the caption; wins over `typeCaption` when set. */
  readonly typeCaptionKey?: string;
  /** Agent body only: primary port rows, in `portsFor` order. */
  readonly ports?: readonly PortDef[];
  /** Agent body only: secondary ports, in `portsFor` order. */
  readonly secondaryPorts?: readonly PortDef[];
  /** Agent body only: whether the edited agent is usable as a tool (shows the Tool badge). */
  readonly isTool?: boolean;
  /** Agent body only: piece kind currently being dragged toward the canvas, if any. */
  readonly draggingKind?: PieceKind | null;
  /** Agent body only, AI services only: whether the dragged service supports video. */
  readonly draggingSupportsVideo?: boolean;
  /** Piece cards only: the connected piece. */
  readonly piece?: CanvasPiece;
  /** Piece cards only: labels of the ports the piece feeds, in port order (one card per piece even when it connects to several ports). */
  readonly portLabels?: readonly string[];
  /** Piece cards only: on the canvas but not connected to any port yet. */
  readonly loose?: boolean;
}

export type CanvasFlowNode = Node<CanvasNodeData>;

function PortRow({
  port,
  side,
  isConnectable,
  dragging,
  acceptsDrag,
}: {
  readonly port: PortDef;
  /** `left` ports hang off the card's left border, `right` ports off its right border. */
  readonly side: 'left' | 'right';
  readonly isConnectable: boolean;
  readonly dragging: boolean;
  readonly acceptsDrag: boolean;
}) {
  const { t } = useTranslation('common');
  const isRight = side === 'right';
  const portLabel = t(`agentCanvas.ports.${port.id}`, { defaultValue: port.label });
  const isTools = port.id === 'tools';
  // The bullet is painted with the accent color(s) of the piece kinds it takes,
  // so users can match a piece to its port at a glance. Tools is deliberately
  // ink black (near-white in dark mode) per user preference.
  const background =
    port.accepts.length === 1
      ? PIECE_VISUALS[port.accepts[0]].accentHex
      : `linear-gradient(135deg, ${port.accepts.map((kind) => PIECE_VISUALS[kind].accentHex).join(', ')})`;
  const label = (
    <div className={`min-w-0 flex-1 ${isRight ? 'mr-4 text-right' : 'ml-4'}`}>
      <span className="block truncate text-xs text-fg-secondary dark:text-fg-secondary-dark" title={portLabel}>
        {portLabel}
      </span>
    </div>
  );
  return (
    <div
      data-port-id={port.id}
      className={`relative flex items-center rounded-md py-0.5 transition ${
        acceptsDrag
          ? 'ring-2 ring-accent bg-surface-hover dark:ring-accent-dark dark:bg-btCard-hover'
          : dragging
            ? 'opacity-40'
            : ''
      } ${isRight ? 'flex-row-reverse' : ''}`}
    >
      <Handle
        type="target"
        position={isRight ? Position.Right : Position.Left}
        id={port.id}
        isConnectable={isConnectable}
        className={`!h-2.5 !w-2.5 !rounded-full !border-2 !border-surface dark:!border-surface-dark ${
          isTools ? '!bg-ink dark:!bg-fg-dark' : ''
        }`}
        style={isTools ? undefined : { background }}
      />
      {label}
    </div>
  );
}

/**
 * The edited agent's body: one target handle per port of `portsFor(type)`.
 * Primary ports sit in a column on the card's left border and secondary ones
 * in a column on its right border (a single column when there are no
 * secondary ports, e.g. OCR agents). While a piece is being dragged, the
 * ports that would take it light up and the rest dim.
 */
export function AgentPortNode({ data, isConnectable }: NodeProps<CanvasFlowNode>) {
  const { t } = useTranslation('common');
  const visual = NODE_KIND_VISUALS.agent;
  const ports = data.ports ?? [];
  const secondary = data.secondaryPorts ?? [];
  const isTool = data.isTool === true;
  const draggingKind = data.draggingKind ?? null;
  const draggingSupportsVideo = data.draggingSupportsVideo === true;
  const acceptsDrag = (port: PortDef): boolean =>
    draggingKind !== null &&
    port.accepts.includes(draggingKind) &&
    // The Video port only takes AI services that can analyse video.
    !(port.id === 'video' && draggingKind === 'ai_service' && !draggingSupportsVideo);
  const twoColumns = secondary.length > 0;

  const rowProps = (port: PortDef) => ({
    port,
    isConnectable,
    dragging: draggingKind !== null,
    acceptsDrag: acceptsDrag(port),
  });

  return (
    <div
      data-agent-node=""
      className={`relative min-w-[300px] rounded-md border-2 border-ink bg-surface px-3 py-2.5 dark:border-fg-dark dark:bg-surface-dark`}
    >
      <div className="flex items-center gap-3">
        <KindIcon icon={visual.icon} color={visual.accentHex} size={40} iconSize={20} />
        <div className="min-w-0 flex-1">
          {/* Keep the name clear of the absolute Tool badge on the top-right corner. */}
          <p
            className={`truncate font-display text-base font-medium text-fg dark:text-fg-dark ${isTool ? 'pr-12' : ''}`}
            title={data.label}
          >
            {data.label}
          </p>
          <p className="truncate text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {t(data.typeCaptionKey ?? visual.typeCaptionKey, { defaultValue: data.typeCaption ?? visual.typeCaption })}
          </p>
        </div>
      </div>
      {isTool && (
        <span className="absolute right-2 top-2 rounded-sm border border-line-strong bg-surface px-1.5 py-0.5 text-[10px] font-medium text-fg dark:border-btCard-border-dark dark:bg-surface-dark dark:text-fg-dark">
          {t('agentCanvas.nodes.tool')}
        </span>
      )}

      {/* Full-bleed columns so the port handles sit on the card's borders: the
          left column touches the left border, the right one the right border. */}
      <div className="-mx-3 mt-2 border-t border-line pt-2 dark:border-btCard-border-dark">
        <div className={twoColumns ? 'flex gap-8' : 'space-y-0.5'}>
          <div className="min-w-0 flex-1 space-y-0.5">
            {ports.map((port) => (
              <PortRow key={port.id} side="left" {...rowProps(port)} />
            ))}
          </div>
          {twoColumns && (
            <div className="min-w-0 flex-1 space-y-0.5">
              {secondary.map((port) => (
                <PortRow key={port.id} side="right" {...rowProps(port)} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
