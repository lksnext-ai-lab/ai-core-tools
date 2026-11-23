import { useState } from 'react';
import { Copy, FileJson, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { apiService } from '../../services/api';
import { Spinner } from '../ui/Spinner';

export interface SearchResult {
  page_content: string;
  metadata: Record<string, unknown>;
  score?: number;
  id?: string;
}

interface ResultCardProps {
  result: SearchResult;
  index: number;
  maxScore: number;
  onDelete?: (result: SearchResult, index: number) => void;
  isDeleting?: boolean;
  appId: string;
  siloId: string;
  isSelected?: boolean;
  onSelect?: (id: string, selected: boolean) => void;
  onReindex?: (resourceId: string) => void;
}

type MetadataPrimitive = string | number | undefined;

type SourceInfo =
  | { type: 'media'; label: string }
  | { type: 'resource'; label: string }
  | { type: 'url'; label: string; href: string }
  | { type: 'generic' };

function detectSource(metadata: Record<string, unknown>, t: TFunction<'common'>): SourceInfo {
  if (metadata.media_id !== undefined) {
    const id = metadata.media_id as string | number;
    const name = metadata.name as string | undefined;
    const label = name ?? t('resultCard.mediaFallback', { id });
    return { type: 'media', label };
  }
  if (metadata.resource_id !== undefined) {
    const id = metadata.resource_id as string | number;
    const name = metadata.name as string | undefined;
    const label = name ?? t('resultCard.documentFallback', { id });
    return { type: 'resource', label };
  }
  if (metadata.url !== undefined) {
    const urlStr = metadata.url as string;
    return { type: 'url', label: urlStr.slice(0, 60), href: urlStr };
  }
  return { type: 'generic' };
}

function MetaValue({ value, t }: Readonly<{ value: unknown; t: TFunction<'common'> }>) {
  if (value === null || value === undefined) {
    return <span className="font-mono text-fg-tertiary dark:text-fg-tertiary-dark">null</span>;
  }
  if (typeof value === 'boolean') {
    return <span className="font-mono">{value ? 'true' : 'false'}</span>;
  }
  if (typeof value === 'number') {
    return <span className="font-mono">{value}</span>;
  }
  if (typeof value === 'string') {
    return <span>{value}</span>;
  }
  if (Array.isArray(value)) {
    return <span className="italic text-fg-tertiary dark:text-fg-tertiary-dark">▸ {t('resultCard.items', { count: value.length })}</span>;
  }
  if (typeof value === 'object') {
    return (
      <span className="italic text-fg-tertiary dark:text-fg-tertiary-dark">
        ▸ {t('resultCard.keys', { count: Object.keys(value as Record<string, unknown>).length })}
      </span>
    );
  }
  // bigint, symbol, function
  return <span>{`${value as string | number | boolean | bigint}`}</span>;
}

export default function ResultCard({
  result,
  index,
  maxScore,
  onDelete,
  isDeleting,
  appId,
  siloId,
  isSelected,
  onSelect,
  onReindex,
}: Readonly<ResultCardProps>) {
  const { t } = useTranslation('common');
  const [expanded, setExpanded] = useState(false);
  const [metaView, setMetaView] = useState<'pretty' | 'raw'>('pretty');
  const [lastCopied, setLastCopied] = useState<string | null>(null);

  // FR-2.4 neighbors state
  const [neighbors, setNeighbors] = useState<SearchResult[] | null>(null);
  const [loadingNeighbors, setLoadingNeighbors] = useState(false);
  const [neighborsError, setNeighborsError] = useState<string | null>(null);
  const [showNeighbors, setShowNeighbors] = useState(false);

  const { metadata, page_content, score } = result;
  const source = detectSource(metadata, t);

  // FR-2.1 score bar — TypeScript 4.4+ narrows score through aliased condition
  const showScore = score != null && maxScore > 0;
  const scoreBarWidth = showScore ? Math.min((score / maxScore) * 100, 100) : 0;

  // FR-2.3 expand/collapse
  const isLong = page_content.length > 300;
  const displayContent = isLong && !expanded ? page_content.slice(0, 300) + '…' : page_content;

  // FR-2.5 copy handlers
  async function handleCopyText() {
    try {
      await navigator.clipboard.writeText(page_content);
      setLastCopied('text');
      setTimeout(() => setLastCopied(null), 1500);
    } catch {
      // silent fail — clipboard may be unavailable in non-HTTPS
    }
  }

  async function handleCopyJson() {
    try {
      await navigator.clipboard.writeText(
        JSON.stringify({ page_content, metadata, score }, null, 2),
      );
      setLastCopied('json');
      setTimeout(() => setLastCopied(null), 1500);
    } catch {
      // silent fail
    }
  }

  // FR-2.4 neighbors handler
  async function handleNeighbors() {
    if (neighbors !== null) {
      setShowNeighbors((prev) => !prev);
      return;
    }
    setLoadingNeighbors(true);
    setNeighborsError(null);
    try {
      const sourceType = metadata.media_id !== undefined ? 'media' : 'resource';
      const rawId = (metadata.media_id ?? metadata.resource_id) as string | number;
      const sourceId = `${rawId}`;
      const data = await apiService.getSiloNeighbors(appId, siloId, sourceType, sourceId);
      setNeighbors((data as { chunks: SearchResult[] }).chunks);
      setShowNeighbors(true);
    } catch (err) {
      setNeighborsError(err instanceof Error ? err.message : t('resultCard.loadNeighborsFailed'));
    } finally {
      setLoadingNeighbors(false);
    }
  }

  function isCurrentChunk(neighbor: SearchResult): boolean {
    const nm = neighbor.metadata;
    if (metadata._id !== undefined && nm._id !== undefined) {
      return metadata._id === nm._id;
    }
    if (metadata.media_id !== undefined && metadata.chunk_index !== undefined) {
      return nm.chunk_index === metadata.chunk_index;
    }
    if (metadata.resource_id !== undefined && metadata.page !== undefined) {
      return nm.page === metadata.page;
    }
    return false;
  }

  const showNeighborsButton = source.type === 'media' || source.type === 'resource';

  function neighborButtonLabel(): string {
    if (loadingNeighbors) return t('resultCard.loading');
    return showNeighbors ? t('resultCard.hideNeighbors') : t('resultCard.neighbors');
  }

  const iconButtonClass = 'rounded p-1.5 text-fg-tertiary hover:bg-surface-hover hover:text-fg-secondary dark:text-fg-tertiary-dark dark:hover:bg-surface-hover-dark dark:hover:text-fg-secondary-dark';
  const pillClass = 'rounded-lg bg-surface-hover px-[9px] py-0.5 text-[11.5px] text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark';
  const linkClass = 'text-[12.5px] text-fg underline decoration-accent underline-offset-[3px] hover:text-accent dark:text-fg-dark dark:decoration-accent-dark dark:hover:text-accent-dark';

  return (
    <article className="rounded-lg border border-line px-4 py-3.5 dark:border-line-dark">
      {/* Header row */}
      <div className="mb-2.5 flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2.5">
          {onSelect && (
            <input
              type="checkbox"
              checked={isSelected ?? false}
              onChange={(e) => onSelect(result.id ?? '', e.target.checked)}
              onClick={(e) => e.stopPropagation()}
              className="h-4 w-4 cursor-pointer accent-ink dark:accent-ink-dark"
              aria-label={t('resultCard.selectDocument')}
            />
          )}
          <span className="text-[13px] font-semibold text-fg dark:text-fg-dark">{t('resultCard.resultNumber', { number: index + 1 })}</span>
          {result.id && (
            <span className="font-mono text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark" title={t('resultCard.documentId', { id: result.id })}>
              {result.id.substring(0, 8)}…
            </span>
          )}
          <span className={pillClass}>
            {t('resultCard.characterCount', { count: page_content.length })}
          </span>

          {/* FR-2.2 source badges */}
          {(source.type === 'media' || source.type === 'resource') && (
            <span className={`max-w-[260px] truncate ${pillClass}`} title={source.label}>
              {source.label}
            </span>
          )}
          {source.type === 'url' && (
            <a
              href={source.href}
              target="_blank"
              rel="noopener noreferrer"
              className={`max-w-[260px] truncate hover:underline ${pillClass}`}
              title={source.href}
            >
              {source.label}
            </a>
          )}
        </div>

        {/* FR-2.5 copy + delete buttons */}
        <div className="flex shrink-0 items-center gap-1">
          {lastCopied && (
            <span className="rounded bg-success-bg px-2 py-0.5 text-xs text-success dark:bg-success-bg-dark dark:text-success-dark">
              {t('resultCard.copied')}
            </span>
          )}
          <button
            onClick={handleCopyText}
            className={iconButtonClass}
            title={t('resultCard.copyText')}
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={handleCopyJson}
            className={iconButtonClass}
            title={t('resultCard.copyJson')}
          >
            <FileJson className="h-3.5 w-3.5" />
          </button>
          {onReindex && result.metadata?.resource_id !== undefined && (
            <button
              onClick={(e) => { e.stopPropagation(); onReindex(String(result.metadata.resource_id as string | number)); }}
              className="rounded-md border border-line px-2 py-1 text-xs text-fg-secondary transition-colors hover:bg-surface-hover dark:border-line-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
              title={t('resultCard.reindexSourceDocument')}
            >
              {t('resultCard.reindex')}
            </button>
          )}
          {result.id && onDelete && (
            <button
              onClick={() => onDelete(result, index)}
              disabled={!!isDeleting}
              className="rounded p-1.5 text-error hover:bg-error-bg disabled:cursor-not-allowed disabled:opacity-50 dark:text-error-dark dark:hover:bg-error-bg-dark"
              title={t('resultCard.deleteDocument')}
            >
              {isDeleting ? (
                <Spinner size="xs" tone="current" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* FR-2.1 Score bar */}
      {showScore && (
        <div className="mb-3 flex items-center gap-2">
          <div className="h-1.5 flex-1 rounded bg-surface-hover dark:bg-surface-hover-dark">
            <div
              className="h-1.5 rounded bg-accent dark:bg-accent-dark"
              style={{ width: `${scoreBarWidth}%` }}
            />
          </div>
          <span className="shrink-0 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('resultCard.score', { score: score.toFixed(3) })}</span>
        </div>
      )}

      {/* FR-2.3 Content */}
      <div>
        <p className="m-0 whitespace-pre-wrap text-[13.5px] leading-[1.6] text-fg dark:text-fg-dark">
          {displayContent}
        </p>
        {isLong && (
          <button
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
            className={`mt-1.5 ${linkClass}`}
          >
            {expanded ? t('resultCard.showLess') : t('resultCard.showMore')}
          </button>
        )}
      </div>

      {/* FR-2.4 Neighboring chunks */}
      {showNeighborsButton && (
        <div className="mt-3">
          <button
            onClick={handleNeighbors}
            disabled={loadingNeighbors}
            className="rounded-md border border-line px-2 py-1 text-xs text-fg-secondary hover:bg-surface-hover disabled:opacity-50 dark:border-line-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
          >
            {neighborButtonLabel()}
          </button>
          {neighborsError && (
            <span className="ml-2 text-xs text-error dark:text-error-dark">{neighborsError}</span>
          )}
          {showNeighbors && neighbors && (
            <div className="mt-3 space-y-2 rounded-r-lg border-l-2 border-accent bg-surface-tint py-2 pl-3 dark:border-accent-dark dark:bg-surface-tint-dark">
              {neighbors.map((neighbor, ni) => {
                const isCurrent = isCurrentChunk(neighbor);
                const chunkIndex = neighbor.metadata.chunk_index as MetadataPrimitive;
                const page = neighbor.metadata.page as MetadataPrimitive;
                const chunkLabel =
                  neighbor.metadata.media_id !== undefined
                    ? t('resultCard.chunkLabel', { index: chunkIndex })
                    : t('resultCard.pageLabel', { page });
                const neighborId = neighbor.metadata._id as MetadataPrimitive;
                const neighborKey = neighborId !== undefined ? `${neighborId}` : ni;
                return (
                  <div
                    key={neighborKey}
                    className={`rounded p-2 text-xs text-fg dark:text-fg-dark ${
                      isCurrent
                        ? 'border border-bronze-border bg-bronze-bg font-medium dark:border-bronze-border-dark dark:bg-bronze-bg-dark'
                        : 'bg-surface dark:bg-surface-dark'
                    }`}
                  >
                    <span className="mr-1 text-fg-tertiary dark:text-fg-tertiary-dark">[{chunkLabel}]</span>
                    {neighbor.page_content.slice(0, 120)}
                    {neighbor.page_content.length > 120 ? '…' : ''}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* FR-2.6 Metadata */}
      {Object.keys(metadata).length > 0 && (
        <details className="group mt-2.5 border-t border-line pt-2.5 dark:border-line-dark">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] font-medium text-fg dark:text-fg-dark [&::-webkit-details-marker]:hidden">
            <span aria-hidden="true" className="inline-block transition-transform duration-150 group-open:rotate-90 motion-reduce:transition-none">▸</span>
            {t('resultCard.metadata')}
            <span className="font-normal text-fg-tertiary dark:text-fg-tertiary-dark">· {t('resultCard.fieldCount', { count: Object.keys(metadata).length })}</span>
          </summary>
          <div className="mt-2.5">
            {metaView === 'raw' ? (
              <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-[#33302a] bg-[#1c1b18] px-3.5 py-3 font-mono text-xs leading-relaxed text-[#f2efe9]">
                {JSON.stringify(metadata, null, 2)}
              </pre>
            ) : (
              <dl className="m-0 grid grid-cols-[150px_minmax(0,1fr)] gap-x-3.5 gap-y-1.5 rounded-md border border-line bg-surface-tint px-3.5 py-3 text-[12.5px] text-fg dark:border-line-dark dark:bg-surface-tint-dark dark:text-fg-dark">
                {Object.entries(metadata).map(([key, value]) => {
                  const isInternal = ['_id', '_score', 'silo_id'].includes(key);
                  return (
                    <div key={key} className={`contents ${isInternal ? '[&>*]:opacity-60' : ''}`}>
                      <dt className="truncate font-mono text-fg-tertiary dark:text-fg-tertiary-dark" title={key}>
                        {key}
                      </dt>
                      <dd className="m-0 break-words">
                        <MetaValue value={value} t={t} />
                      </dd>
                    </div>
                  );
                })}
              </dl>
            )}
            <button
              onClick={() => setMetaView((v) => (v === 'pretty' ? 'raw' : 'pretty'))}
              className={`mt-2 ${linkClass}`}
            >
              {metaView === 'pretty' ? t('resultCard.rawJson') : t('resultCard.pretty')}
            </button>
          </div>
        </details>
      )}
    </article>
  );
}
