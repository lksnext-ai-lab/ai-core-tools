import { useState } from 'react';
import { Copy, FileJson, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';

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

function detectSource(metadata: Record<string, unknown>): SourceInfo {
  if (metadata.media_id !== undefined) {
    const id = metadata.media_id as string | number;
    const name = metadata.name as string | undefined;
    const label = name ?? `Media #${id}`;
    return { type: 'media', label };
  }
  if (metadata.resource_id !== undefined) {
    const id = metadata.resource_id as string | number;
    const name = metadata.name as string | undefined;
    const label = name ?? `Document #${id}`;
    return { type: 'resource', label };
  }
  if (metadata.url !== undefined) {
    const urlStr = metadata.url as string;
    return { type: 'url', label: urlStr.slice(0, 60), href: urlStr };
  }
  return { type: 'generic' };
}

function MetaValue({ value }: Readonly<{ value: unknown }>) {
  if (value === null || value === undefined) {
    return <span className="text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-500">null</span>;
  }
  if (typeof value === 'boolean') {
    return (
      <span className="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-600">
        {value ? 'true' : 'false'}
      </span>
    );
  }
  if (typeof value === 'number') {
    return <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-600">{value}</span>;
  }
  if (typeof value === 'string') {
    return <span className="text-xs text-gray-700">{value}</span>;
  }
  if (Array.isArray(value)) {
    return <span className="text-xs text-gray-400 italic">▸ {value.length} items</span>;
  }
  if (typeof value === 'object') {
    return (
      <span className="text-xs text-gray-400 italic">
        ▸ {Object.keys(value as Record<string, unknown>).length} keys
      </span>
    );
  }
  // bigint, symbol, function
  return <span className="text-xs text-gray-700">{`${value as string | number | boolean | bigint}`}</span>;
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
  const [expanded, setExpanded] = useState(false);
  const [metaView, setMetaView] = useState<'pretty' | 'raw'>('pretty');
  const [lastCopied, setLastCopied] = useState<string | null>(null);

  // FR-2.4 neighbors state
  const [neighbors, setNeighbors] = useState<SearchResult[] | null>(null);
  const [loadingNeighbors, setLoadingNeighbors] = useState(false);
  const [neighborsError, setNeighborsError] = useState<string | null>(null);
  const [showNeighbors, setShowNeighbors] = useState(false);

  const { metadata, page_content, score } = result;
  const source = detectSource(metadata);

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
      setNeighborsError(err instanceof Error ? err.message : 'Failed to load neighbors');
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
    if (loadingNeighbors) return 'Loading…';
    return showNeighbors ? 'Hide neighbors' : 'Neighbors';
  }

  return (
    <div className="relative border border-gray-200 rounded-lg p-4">
      {onSelect && (
        <div className="absolute top-3 left-3 z-10">
          <input
            type="checkbox"
            checked={isSelected ?? false}
            onChange={(e) => onSelect(result.id ?? '', e.target.checked)}
            onClick={(e) => e.stopPropagation()}
            className="w-4 h-4 accent-amber-500 cursor-pointer"
            aria-label="Select document"
          />
        </div>
      )}
      {/* Header row */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-gray-500">Result #{index + 1}</span>
          {result.id && (
            <span className="text-xs text-gray-400" title={`Document ID: ${result.id}`}>
              (ID: {result.id.substring(0, 8)}...)
            </span>
          )}
          <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
            📏 {page_content.length} chars
          </span>

          {/* FR-2.2 source badges */}
          {source.type === 'media' && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
              {source.label}
            </span>
          )}
          {source.type === 'resource' && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
              {source.label}
            </span>
          )}
          {source.type === 'url' && (
            <a
              href={source.href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 hover:underline"
            >
              {source.label}
            </a>
          )}
        </div>

        {/* FR-2.5 copy + delete buttons */}
        <div className="flex items-center gap-1 ml-2 shrink-0">
          {lastCopied && (
            <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded">
              Copied!
            </span>
          )}
          <button
            onClick={handleCopyText}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded"
            title="Copy text"
          >
            <Copy className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleCopyJson}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded"
            title="Copy JSON"
          >
            <FileJson className="w-3.5 h-3.5" />
          </button>
          {onReindex && result.metadata?.resource_id && (
            <button
              onClick={(e) => { e.stopPropagation(); onReindex(String(result.metadata.resource_id as string | number)); }}
              className="text-xs px-2 py-1 text-blue-600 border border-blue-300 rounded hover:bg-blue-50 transition-colors"
              title="Re-extract and reindex this source document"
            >
              Reindex
            </button>
          )}
          {result.id && onDelete && (
            <button
              onClick={() => onDelete(result, index)}
              disabled={!!isDeleting}
              className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              title="Delete this document from silo"
            >
              {isDeleting ? (
                <div className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-red-600" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* FR-2.1 Score bar */}
      {showScore && (
        <div className="flex items-center gap-2 mb-3">
          <div className="flex-1 bg-gray-100 rounded h-1.5">
            <div
              className="bg-yellow-400 h-1.5 rounded"
              style={{ width: `${scoreBarWidth}%` }}
            />
          </div>
          <span className="text-xs text-gray-500 shrink-0">Score: {score.toFixed(3)}</span>
        </div>
      )}

      {/* FR-2.3 Content */}
      <div className="mb-3">
        <h3 className="text-sm font-medium text-gray-700 mb-1">Content:</h3>
        <p className="text-gray-900 text-sm leading-relaxed whitespace-pre-wrap">
          {displayContent}
        </p>
        {isLong && (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="mt-1 text-xs text-yellow-600 hover:text-yellow-800"
          >
            {expanded ? 'Show less' : 'Show more'}
          </button>
        )}
      </div>

      {/* FR-2.4 Neighboring chunks */}
      {showNeighborsButton && (
        <div className="mb-3">
          <button
            onClick={handleNeighbors}
            disabled={loadingNeighbors}
            className="text-xs px-2 py-1 bg-yellow-50 text-yellow-700 border border-yellow-200 rounded hover:bg-yellow-100 disabled:opacity-50"
          >
            {neighborButtonLabel()}
          </button>
          {neighborsError && (
            <span className="ml-2 text-xs text-red-500">{neighborsError}</span>
          )}
          {showNeighbors && neighbors && (
            <div className="mt-3 border-l-2 border-yellow-300 pl-3 bg-gray-50 rounded-r-lg space-y-2 py-2">
              {neighbors.map((neighbor, ni) => {
                const isCurrent = isCurrentChunk(neighbor);
                const chunkIndex = neighbor.metadata.chunk_index as MetadataPrimitive;
                const page = neighbor.metadata.page as MetadataPrimitive;
                const chunkLabel =
                  neighbor.metadata.media_id !== undefined
                    ? `chunk ${chunkIndex}`
                    : `page ${page}`;
                const neighborId = neighbor.metadata._id as MetadataPrimitive;
                const neighborKey = neighborId !== undefined ? `${neighborId}` : ni;
                return (
                  <div
                    key={neighborKey}
                    className={`text-xs p-2 rounded ${
                      isCurrent
                        ? 'bg-yellow-100 border border-yellow-300 font-medium'
                        : 'bg-white'
                    }`}
                  >
                    <span className="text-gray-400 mr-1">[{chunkLabel}]</span>
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
        <div>
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-medium text-gray-700">Metadata:</h3>
            <button
              onClick={() => setMetaView((v) => (v === 'pretty' ? 'raw' : 'pretty'))}
              className="text-xs text-gray-500 hover:text-gray-700 px-2 py-0.5 rounded border border-gray-200"
            >
              {metaView === 'pretty' ? 'Raw JSON' : 'Pretty'}
            </button>
          </div>
          <div className="bg-gray-50 rounded p-2">
            {metaView === 'raw' ? (
              <pre className="text-xs text-gray-600 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(metadata, null, 2)}
              </pre>
            ) : (
              <div className="space-y-1">
                {Object.entries(metadata).map(([key, value]) => {
                  const isInternal = ['_id', '_score', 'silo_id'].includes(key);
                  return (
                    <div
                      key={key}
                      className={`flex items-start gap-2 ${isInternal ? 'opacity-60' : ''}`}
                    >
                      <span className="text-xs font-mono text-gray-500 shrink-0 min-w-[100px]">
                        {key}:
                      </span>
                      <MetaValue value={value} />
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
