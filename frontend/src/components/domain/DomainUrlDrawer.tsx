import { useState, useEffect } from 'react';
import { ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { apiService } from '../../services/api';
import Modal from '../ui/Modal';
import type { DomainUrlDetail, DomainUrlStatus, DiscoverySource } from '../../types/crawl';

interface DomainUrlDrawerProps {
  appId: number;
  domainId: number;
  urlId: number | null;
  canEdit: boolean;
  onClose: () => void;
}

function statusBadgeClass(status: DomainUrlStatus): string {
  switch (status) {
    case 'INDEXED': return 'bg-green-100 text-green-800';
    case 'CRAWLING': return 'bg-blue-100 text-blue-800';
    case 'PENDING': return 'bg-yellow-100 text-yellow-800';
    case 'FAILED': return 'bg-red-100 text-red-800';
    case 'SKIPPED': return 'bg-gray-100 text-gray-600';
    case 'REMOVED': return 'bg-gray-100 text-gray-400';
    case 'EXCLUDED': return 'bg-orange-100 text-orange-700';
    default: return 'bg-gray-100 text-gray-600';
  }
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function Field({ label, value }: Readonly<{ label: string; value: React.ReactNode }>) {
  return (
    <div>
      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-800">{value ?? '—'}</dd>
    </div>
  );
}

export default function DomainUrlDrawer({
  appId,
  domainId,
  urlId,
  canEdit,
  onClose,
}: Readonly<DomainUrlDrawerProps>) {
  const [urlDetail, setUrlDetail] = useState<DomainUrlDetail | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const [recrawling, setRecrawling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!urlId) {
      setUrlDetail(null);
      setContent(null);
      return;
    }

    const fetchData = async () => {
      try {
        setLoadingMeta(true);
        setLoadingContent(true);
        setError(null);

        const [detail, contentResp] = await Promise.allSettled([
          apiService.getDomainUrl(appId, domainId, urlId),
          apiService.getUrlContent(appId, domainId, urlId),
        ]);

        if (detail.status === 'fulfilled') {
          setUrlDetail(detail.value);
        } else {
          setError('Failed to load URL detail');
        }

        if (contentResp.status === 'fulfilled') {
          setContent((contentResp.value as any)?.content ?? null);
        }
      } finally {
        setLoadingMeta(false);
        setLoadingContent(false);
      }
    };

    void fetchData();
  }, [appId, domainId, urlId]);

  const handleRecrawl = async () => {
    if (!urlId || recrawling) return;
    try {
      setRecrawling(true);
      await apiService.recrawlDomainUrl(appId, domainId, urlId);
      // Re-fetch to show updated next_crawl_at
      const updated = await apiService.getDomainUrl(appId, domainId, urlId);
      setUrlDetail(updated);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to mark for re-crawl');
    } finally {
      setRecrawling(false);
    }
  };

  if (!urlId) return null;

  return (
    <Modal
      isOpen={urlId !== null}
      onClose={onClose}
      title="URL Detail"
      size="xlarge"
    >
      <div className="p-6 overflow-y-auto max-h-[70vh] space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
            {error}
          </div>
        )}

        {loadingMeta ? (
          <div className="flex justify-center items-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
            <span className="ml-2 text-sm text-gray-500">Loading URL details...</span>
          </div>
        ) : urlDetail ? (
          <>
            {/* URL + Status */}
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <a
                  href={urlDetail.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-blue-600 hover:text-blue-800 font-mono text-sm break-all"
                >
                  {urlDetail.url}
                  <ExternalLink className="w-3 h-3 flex-shrink-0" />
                </a>
              </div>
              <span className={`flex-shrink-0 px-2 py-0.5 rounded text-xs font-medium ${statusBadgeClass(urlDetail.status as DomainUrlStatus)}`}>
                {urlDetail.status}
              </span>
            </div>

            {/* Core metadata */}
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <Field label="Discovered via" value={urlDetail.discovered_via as DiscoverySource} />
              <Field label="Depth" value={urlDetail.depth} />
              <Field label="Last crawled" value={formatDate(urlDetail.last_crawled_at)} />
              <Field label="Last indexed" value={formatDate(urlDetail.last_indexed_at)} />
              <Field label="Next crawl" value={
                <span title={urlDetail.consecutive_skips > 1 ? `${urlDetail.consecutive_skips} consecutive skips — backoff active` : undefined}>
                  {formatDate(urlDetail.next_crawl_at)}
                  {urlDetail.consecutive_skips > 1 && (
                    <span className="ml-1 text-orange-500 text-xs">({urlDetail.consecutive_skips}× backoff)</span>
                  )}
                </span>
              } />
              <Field label="Failure count" value={
                urlDetail.failure_count > 0
                  ? <span className="text-red-600 font-medium">{urlDetail.failure_count}</span>
                  : urlDetail.failure_count
              } />
            </dl>

            {/* Last error */}
            {urlDetail.last_error && (
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Last error</p>
                <pre className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2 whitespace-pre-wrap max-h-24 overflow-y-auto">
                  {urlDetail.last_error}
                </pre>
              </div>
            )}

            {/* HTTP cache hints */}
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">HTTP cache hints</p>
              <dl className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <Field label="ETag" value={urlDetail.http_etag ?? '—'} />
                <Field label="Last-Modified" value={urlDetail.http_last_modified ?? '—'} />
                <Field label="Sitemap lastmod" value={formatDate(urlDetail.sitemap_lastmod)} />
              </dl>
            </div>

            {/* Actions */}
            {canEdit && (
              <div>
                <button
                  type="button"
                  onClick={() => { void handleRecrawl(); }}
                  disabled={recrawling}
                  className="flex items-center gap-2 text-sm bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white px-3 py-1.5 rounded-lg transition-colors"
                >
                  {recrawling ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4" />
                  )}
                  {recrawling ? 'Marking...' : 'Force re-crawl'}
                </button>
              </div>
            )}
          </>
        ) : null}

        {/* Content preview */}
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Indexed content preview</p>
          {loadingContent ? (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading content...
            </div>
          ) : content ? (
            <pre className="text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded p-3 whitespace-pre-wrap max-h-64 overflow-y-auto">
              {content}
            </pre>
          ) : (
            <p className="text-sm text-gray-500 italic">No indexed content found for this URL.</p>
          )}
        </div>
      </div>
    </Modal>
  );
}
