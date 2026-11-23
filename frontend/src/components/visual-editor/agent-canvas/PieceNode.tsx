import { Handle, Position, type NodeProps } from '@xyflow/react';
import { useTranslation } from 'react-i18next';
import BackgroundImage from '../../ui/BackgroundImage';
import { PIECE_VISUALS } from '../nodeKindConfig';
import type { CanvasFlowNode } from './AgentPortNode';

/**
 * A connected piece (AI service, silo, skill, MCP config, agent tool, ...)
 * around the agent body, with a source handle on each side so the edge
 * leaves the card from the side facing the agent port it connects to
 * (right for primary ports, left for secondary ones). Neutral card look;
 * the kind color only shows on the connector dots.
 */
export function PieceNode({ data, isConnectable }: NodeProps<CanvasFlowNode>) {
  const { t } = useTranslation('common');
  const piece = data.piece;
  if (!piece) return null;
  const visual = PIECE_VISUALS[piece.kind];

  return (
    <div className="group relative flex min-w-[190px] items-center gap-3 rounded-md border border-line bg-surface px-3 py-2.5 transition-colors hover:bg-surface-hover dark:border-btCard-border-dark dark:bg-surface-dark dark:hover:bg-btCard-hover">
      <BackgroundImage icon={visual.icon} size={34} iconSize={17} variant="marron" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-display text-sm font-medium text-fg group-hover:whitespace-normal group-hover:break-words dark:text-fg-dark" title={piece.name}>
          {piece.name}
        </p>
        <p className="truncate text-xs text-fg-secondary dark:text-fg-secondary-dark">{t(visual.typeCaptionKey)}</p>
        {data.portLabels && data.portLabels.length > 0 && (
          <p className="truncate text-[11px] text-fg-tertiary dark:text-fg-tertiary-dark">
            {data.portLabels.join(', ')}
          </p>
        )}
        {data.loose && (
          <p className="truncate text-[11px] text-fg-tertiary dark:text-fg-tertiary-dark">{t('agentCanvas.nodes.notConnected')}</p>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        isConnectable={isConnectable}
        className="!h-2.5 !w-2.5 !rounded-full !border-2 !border-surface dark:!border-surface-dark"
        style={{ background: visual.accentHex }}
      />
      <Handle
        type="source"
        position={Position.Left}
        id="left"
        isConnectable={isConnectable}
        className="!h-2.5 !w-2.5 !rounded-full !border-2 !border-surface dark:!border-surface-dark"
        style={{ background: visual.accentHex }}
      />
    </div>
  );
}
