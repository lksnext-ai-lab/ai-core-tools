import { useId, useState, type CSSProperties, type DragEvent } from 'react';
import { ChevronDown, ChevronRight, PanelLeftClose, PanelLeftOpen, Plus, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { PIECE_VISUALS } from '../nodeKindConfig';
import { BackgroundImage } from '../../ui/BackgroundImage';
import { ServiceOptionStatus, serviceStatusId } from '../../ui/ServiceOptionStatus';
import type { ServiceOptionLike } from '../../../utils/serviceLifecycle';
import { portsFor, type AgentType, type PieceKind } from './agentPorts';
import { PIECE_KINDS } from './connectionRules';
import type { CanvasPiece } from './useAgentCanvasData';

/** Drag payload type for palette items dropped on the canvas (JSON `{kind, id}`). */
export const PIECE_DRAG_MIME = 'application/x-mattin-piece';

interface PaletteCategory {
  readonly kind: PieceKind;
}

const PALETTE_CATEGORIES: readonly PaletteCategory[] = [
  { kind: 'ai_service' },
  { kind: 'silo' },
  { kind: 'skill' },
  { kind: 'mcp' },
  { kind: 'agent' },
  { kind: 'parser' },
  { kind: 'middleware' },
  { kind: 'sandbox' },
  { kind: 'embedding' },
];

function isPieceKind(value: unknown): value is PieceKind {
  return typeof value === 'string' && (PIECE_KINDS as readonly string[]).includes(value);
}

/** Reads a palette drag payload; null for anything that is not a `{kind, id}` piece. */
export function parsePieceDragPayload(raw: string): { readonly kind: PieceKind; readonly id: number } | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== 'object') return null;
  const { kind, id } = parsed as { kind?: unknown; id?: unknown };
  if (!isPieceKind(kind) || typeof id !== 'number' || !Number.isInteger(id)) return null;
  return { kind, id };
}

export interface CanvasPaletteProps {
  readonly pieces: readonly CanvasPiece[];
  readonly agentType: AgentType;
  /** False for roles below EDITOR: items are not draggable and the `+` buttons are hidden. */
  readonly canEdit: boolean;
  /**
   * True for roles that may create shared resources (ADMINISTRATOR and up): the
   * `+` of AI services, embedding, sandbox, skills, MCP, output parsers and
   * middlewares. Silos and agents only need `canEdit`.
   */
  readonly canCreateShared: boolean;
  /** Desktop width of the panel, driven by the canvas's resize divider. */
  readonly style?: CSSProperties;
  /** Node id (`${kind}:${id}`) of the piece selected in the inspector, or null. */
  readonly selectedPieceId?: string | null;
  /** Opens the creation flow for a kind (wired by the creation modals). */
  readonly onCreate: (kind: PieceKind) => void;
  /** Selects a piece for the inspector; clicking an item shows its details on the right. */
  readonly onSelectPiece?: (piece: CanvasPiece) => void;
  /** Reports the piece a drag starts from the palette; null when the drag ends (drop, cancel or Escape). */
  readonly onDraggingChange?: (piece: CanvasPiece | null) => void;
}

interface PaletteItemProps {
  readonly piece: CanvasPiece;
  readonly canEdit: boolean;
  readonly selected: boolean;
  readonly onSelect?: (piece: CanvasPiece) => void;
  readonly onDraggingChange?: (piece: CanvasPiece | null) => void;
}

function PaletteItem({ piece, canEdit, selected, onSelect, onDraggingChange }: PaletteItemProps) {
  const { t } = useTranslation('common');
  const statusBaseId = useId();
  const visual = PIECE_VISUALS[piece.kind];
  const Icon = visual.icon;
  // Retired pieces cannot be connected, so they cannot be dragged either.
  const draggable = canEdit && piece.lifecycleStatus !== 'retired';
  const statusOptions: ServiceOptionLike[] = piece.lifecycleStatus
    ? [{ service_id: piece.id, name: piece.name, lifecycle_status: piece.lifecycleStatus }]
    : [];
  const describedBy = serviceStatusId(statusOptions, piece.id, statusBaseId);
  const isAgentPiece = piece.kind === 'agent';

  const handleDragStart = (event: DragEvent<HTMLDivElement>) => {
    event.dataTransfer.setData(PIECE_DRAG_MIME, JSON.stringify({ kind: piece.kind, id: piece.id }));
    event.dataTransfer.effectAllowed = 'copy';
    onDraggingChange?.(piece);
  };

  // dragend fires however the drag ends, so the drop highlights always clear.
  const handleDragEnd = () => onDraggingChange?.(null);

  return (
    <li>
      <div
        draggable={draggable}
        onDragStart={draggable ? handleDragStart : undefined}
        onDragEnd={draggable ? handleDragEnd : undefined}
        onClick={onSelect ? () => onSelect(piece) : undefined}
        role={onSelect ? 'button' : undefined}
        tabIndex={onSelect ? 0 : undefined}
        onKeyDown={
          onSelect
            ? (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(piece);
                }
              }
            : undefined
        }
        aria-describedby={describedBy}
        aria-pressed={onSelect ? selected : undefined}
        title={isAgentPiece && !piece.isTool ? t('agentCanvas.palette.connectTurnsTool') : undefined}
        className={`group flex items-start gap-2 rounded-md border px-2 py-1.5 transition-colors ${
          selected
            ? 'border-2 border-bg-soft bg-surface-hover dark:border-bronze-border-dark dark:bg-btCard-hover'
            : 'border-line bg-surface hover:bg-surface-hover dark:border-btCard-border-dark dark:bg-surface-dark dark:hover:bg-surface-hover-dark'
        } focus:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:focus-visible:ring-accent-dark ${
          draggable ? 'cursor-grab active:cursor-grabbing' : onSelect ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
        }`}
      >
        <BackgroundImage icon={Icon} size={28} iconSize={14} />
        <div className="min-w-0 flex-1">
          <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm font-medium text-fg dark:text-fg-dark">
            <span className="min-w-0 break-words" title={piece.name}>
              {piece.name}
            </span>
            {piece.isSystem && (
              <span className="shrink-0 rounded-md bg-surface-tint px-1.5 py-0.5 text-[10px] font-medium text-fg-secondary dark:bg-surface-tint-dark dark:text-fg-secondary-dark">
                {t('agentCanvas.palette.systemBadge')}
              </span>
            )}
            {isAgentPiece && piece.isTool && (
              <span className="shrink-0 rounded-md bg-surface-tint px-1.5 py-0.5 text-[10px] font-medium text-fg-secondary dark:bg-surface-tint-dark dark:text-fg-secondary-dark">
                {t('agentCanvas.palette.toolBadge')}
              </span>
            )}
          </p>
          <ServiceOptionStatus options={statusOptions} selectedId={piece.id} selectId={statusBaseId} />
        </div>
      </div>
    </li>
  );
}

/**
 * Left-hand palette of the per-agent canvas: every piece the app offers,
 * grouped by kind. Items are dragged onto the canvas; the category `+` buttons
 * create new ones. OCR agents only see the categories their ports accept.
 */
export function CanvasPalette({
  pieces,
  agentType,
  canEdit,
  canCreateShared,
  style,
  selectedPieceId,
  onCreate,
  onSelectPiece,
  onDraggingChange,
}: CanvasPaletteProps) {
  const { t } = useTranslation('common');
  const baseId = useId();
  const [filter, setFilter] = useState('');
  /** Whole palette folded into a narrow rail, to give the canvas the room. */
  const [railed, setRailed] = useState(false);
  /** Categories the user folded; a filter always shows matches, so it opens them. */
  const [foldedKinds, setFoldedKinds] = useState<ReadonlySet<PieceKind>>(() => new Set());
  const needle = filter.trim().toLowerCase();
  const toggleKind = (kind: PieceKind): void =>
    setFoldedKinds((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  const isOpen = (kind: PieceKind): boolean => needle !== '' || !foldedKinds.has(kind);
  const ports = portsFor(agentType);
  /** Silos and agents need EDITOR; the other kinds create shared resources and need ADMINISTRATOR. */
  const canCreateFor = (kind: PieceKind): boolean =>
    kind === 'silo' || kind === 'agent' ? canEdit : canCreateShared;
  const selectedKind = selectedPieceId?.slice(0, selectedPieceId.indexOf(':')) ?? null;
  const selectedId = selectedPieceId ? Number.parseInt(selectedPieceId.slice(selectedPieceId.indexOf(':') + 1), 10) : null;

  const groups = PALETTE_CATEGORIES.filter((category) => ports.some((port) => port.accepts.includes(category.kind)))
    .map((category) => ({
      category,
      items: pieces.filter(
        (piece) => piece.kind === category.kind && piece.name.toLowerCase().includes(needle),
      ),
    }))
    .filter(({ items }) => needle === '' || items.length > 0);
  // Empty categories sink to the end (stable sort keeps the category order inside each group).
  const orderedGroups = [...groups].sort((a, b) => (a.items.length === 0 ? 1 : 0) - (b.items.length === 0 ? 1 : 0));
  const memoryLabel = t('agentCanvas.palette.memoryComingSoon');
  const showMemory = agentType === 'agent' && (needle === '' || memoryLabel.toLowerCase().includes(needle));
  const noMatches = needle !== '' && groups.length === 0 && !showMemory;

  if (railed) {
    return (
      <aside
        aria-label={t('agentCanvas.palette.ariaLabel')}
        className="flex w-full shrink-0 items-center justify-center rounded-md border border-line bg-surface p-2 md:w-12 dark:border-btCard-border-dark dark:bg-surface-dark"
      >
        <button
          type="button"
          onClick={() => setRailed(false)}
          aria-expanded={false}
          aria-label={t('agentCanvas.palette.expand')}
          title={t('agentCanvas.palette.expand')}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-fg-secondary transition-colors hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:focus-visible:ring-accent-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
        >
          <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
        </button>
      </aside>
    );
  }

  return (
    <aside
      aria-label={t('agentCanvas.palette.ariaLabel')}
      style={style}
      className="flex max-h-72 w-full shrink-0 flex-col overflow-hidden rounded-md border border-line bg-surface md:max-h-none md:w-[var(--palette-w)] dark:border-btCard-border-dark dark:bg-surface-dark"
    >
      <div className="flex items-center gap-1 border-b border-line p-2 dark:border-line-dark">
        <label htmlFor={`${baseId}-filter`} className="sr-only">
          {t('agentCanvas.palette.filter')}
        </label>
        <div className="relative min-w-0 flex-1">
          <Search
            className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-tertiary dark:text-fg-tertiary-dark"
            aria-hidden="true"
          />
          <input
            id={`${baseId}-filter`}
            type="search"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder={t('agentCanvas.palette.filter')}
            className="w-full rounded-md border border-line bg-surface-hover py-1.5 pl-7 pr-2 text-sm text-fg placeholder:text-fg-tertiary focus:outline-none focus:border-ink focus:ring-1 focus:ring-ink dark:border-line-dark dark:bg-surface-hover-dark dark:text-fg-dark dark:placeholder:text-fg-tertiary-dark dark:focus:border-ink-dark dark:focus:ring-ink-dark"
          />
        </div>
        <button
          type="button"
          onClick={() => setRailed(true)}
          aria-expanded={true}
          aria-label={t('agentCanvas.palette.collapse')}
          title={t('agentCanvas.palette.collapse')}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-fg-tertiary transition-colors hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:focus-visible:ring-accent-dark dark:text-fg-tertiary-dark dark:hover:bg-surface-hover-dark"
        >
          <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {orderedGroups.map(({ category, items }) => {
          const headingId = `${baseId}-${category.kind}`;
          const listId = `${baseId}-${category.kind}-list`;
          const open = isOpen(category.kind);
          return (
            <section key={category.kind} aria-labelledby={headingId} className="mb-3">
              <div className="flex items-center justify-between gap-2 px-1 pb-1">
                <h3 id={headingId} className="min-w-0 flex-1">
                  <button
                    type="button"
                    onClick={() => toggleKind(category.kind)}
                    aria-expanded={open}
                    aria-controls={listId}
                    className="flex w-full items-center gap-1 rounded-md py-0.5 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-fg-tertiary transition-colors hover:text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:focus-visible:ring-accent-dark dark:text-fg-tertiary-dark dark:hover:text-fg-dark"
                  >
                    {open ? (
                      <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    )}
                    <span className="truncate">{t(`agentCanvas.palette.categories.${category.kind}`)}</span>
                    <span className="font-normal normal-case text-fg-tertiary dark:text-fg-tertiary-dark">{items.length}</span>
                  </button>
                </h3>
                {canCreateFor(category.kind) && (
                  <button
                    type="button"
                    onClick={() => onCreate(category.kind)}
                    aria-label={t('agentCanvas.palette.create', { kind: t(`agentCanvas.palette.singular.${category.kind}`) })}
                    title={t('agentCanvas.palette.create', { kind: t(`agentCanvas.palette.singular.${category.kind}`) })}
                    className="inline-flex h-6 w-6 items-center justify-center rounded-md text-fg-secondary transition-colors hover:bg-surface-hover hover:text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-accent dark:focus-visible:ring-accent-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark dark:hover:text-fg-dark"
                  >
                    <Plus className="h-4 w-4" aria-hidden="true" />
                  </button>
                )}
              </div>
              {open && (
                <ul id={listId} className="space-y-1">
                  {items.map((piece) => (
                    <PaletteItem
                      key={`${piece.kind}:${piece.id}`}
                      piece={piece}
                      canEdit={canEdit}
                      selected={piece.kind === selectedKind && piece.id === selectedId}
                      onSelect={onSelectPiece}
                      onDraggingChange={onDraggingChange}
                    />
                  ))}
                  {items.length === 0 && (
                    <li className="px-1 py-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('agentCanvas.palette.none')}</li>
                  )}
                </ul>
              )}
            </section>
          );
        })}

        {showMemory && (
          <button
            type="button"
            disabled
            className="mt-1 w-full rounded-md border border-dashed border-line-strong px-2 py-1.5 text-left text-sm text-fg-tertiary disabled:cursor-not-allowed disabled:opacity-60 dark:border-line-strong-dark dark:text-fg-tertiary-dark"
          >
            {memoryLabel}
          </button>
        )}

        {noMatches && (
          <p className="px-1 py-2 text-xs text-fg-secondary dark:text-fg-secondary-dark">{t('agentCanvas.palette.noMatches')}</p>
        )}
      </div>
    </aside>
  );
}
