import { useState, useEffect, useCallback } from 'react';
import { Loader2, RefreshCw, Trash2, Eye, ChevronLeft, ChevronRight } from 'lucide-react';
import { apiService } from '../../services/api';
import ActionDropdown from '../ui/ActionDropdown';
import Alert from '../ui/Alert';
import type { DomainUrl, DomainUrlStatus, DiscoverySource } from '../../types/crawl';

interface DomainUrlsTableProps {
  appId: number;
  domainId: number;
  canEdit: boolean;
  onViewUrl?: (urlId: number) => void;
}

function getStatusBadge(status: DomainUrlStatus): { text: string; className: string } {
  switch (status) {
    case 'PENDING':
      return { text: 'Pending', className: 'bg-yellow-100 text-yellow-800' };
    case 'CRAWLING':
      return { text: 'Crawling', className: 'bg-blue-100 text-blue-800' };
    case 'INDEXED':
      return { text: 'Indexed', className: 'bg-green-100 text-green-800' };
    case 'SKIPPED':
      return { text: 'Skipped', className: 'bg-gray-100 text-gray-600' };
    case 'FAILED':
      return { text: 'Failed', className: 'bg-red-100 text-red-800' };
    case 'REMOVED':
      return { text: 'Removed', className: 'bg-gray-100 text-gray-400 line-through' };
    case 'EXCLUDED':
      return { text: 'Excluded', className: 'bg-orange-100 text-orange-700' };
    default:
      return { text: status, className: 'bg-gray-100 text-gray-600' };
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All statuses' },
  { value: 'PENDING', label: 'Pending' },
  { value: 'CRAWLING', label: 'Crawling' },
  { value: 'INDEXED', label: 'Indexed' },
  { value: 'SKIPPED', label: 'Skipped' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'REMOVED', label: 'Removed' },
  { value: 'EXCLUDED', label: 'Excluded' },
];

const DISCOVERED_VIA_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All sources' },
  { value: 'SITEMAP', label: 'Sitemap' },
  { value: 'CRAWL', label: 'Crawl' },
  { value: 'MANUAL', label: 'Manual' },
];

const PER_PAGE = 20;

export default function DomainUrlsTable({
  appId,
  domainId,
  canEdit,
  onViewUrl,
}: Readonly<DomainUrlsTableProps>) {
  const [urls, setUrls] = useState<DomainUrl[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [discoveredViaFilter, setDiscoveredViaFilter] = useState('');
  const [qFilter, setQFilter] = useState('');
  const [qInput, setQInput] = useState('');

  // In-flight actions
  const [recrawlingId, setRecrawlingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchUrls = useCallback(async (p: number) => {
    try {
      setLoading(true);
      setError(null);
      const resp = await apiService.listDomainUrls(appId, domainId, {
        page: p,
        per_page: PER_PAGE,
        status: statusFilter || undefined,
        discovered_via: discoveredViaFilter || undefined,
        q: qFilter || undefined,
      });
      setUrls(resp.items);
      setTotal(resp.total);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to load URLs');
    } finally {
      setLoading(false);
    }
  }, [appId, domainId, statusFilter, discoveredViaFilter, qFilter]);

  useEffect(() => {
    void fetchUrls(page);
  }, [fetchUrls, page]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [statusFilter, discoveredViaFilter, qFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setQFilter(qInput);
  };

  const handleRecrawl = async (urlId: number) => {
    if (recrawlingId !== null) return;
    try {
      setRecrawlingId(urlId);
      await apiService.recrawlDomainUrl(appId, domainId, urlId);
      setSuccessMessage('URL marked for re-crawl');
      setTimeout(() => setSuccessMessage(null), 3000);
      void fetchUrls(page);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to mark URL for re-crawl');
    } finally {
      setRecrawlingId(null);
    }
  };

  const handleDelete = async (urlId: number) => {
    if (deletingId !== null) return;
    if (!confirm('Delete this URL and its indexed content?')) return;
    try {
      setDeletingId(urlId);
      await apiService.deleteDomainUrl(appId, domainId, urlId);
      setSuccessMessage('URL deleted');
      setTimeout(() => setSuccessMessage(null), 3000);
      void fetchUrls(page);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to delete URL');
    } finally {
      setDeletingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="space-y-4">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}
      {successMessage && <Alert type="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />}

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="border border-gray-300 rounded-md px-2 py-1 text-sm focus:ring-blue-500 focus:border-blue-500"
        >
          {STATUS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select
          value={discoveredViaFilter}
          onChange={e => setDiscoveredViaFilter(e.target.value)}
          className="border border-gray-300 rounded-md px-2 py-1 text-sm focus:ring-blue-500 focus:border-blue-500"
        >
          {DISCOVERED_VIA_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <form onSubmit={handleSearchSubmit} className="flex gap-1">
          <input
            type="text"
            value={qInput}
            onChange={e => setQInput(e.target.value)}
            placeholder="Search URLs..."
            className="border border-gray-300 rounded-md px-2 py-1 text-sm focus:ring-blue-500 focus:border-blue-500 w-48"
          />
          <button
            type="submit"
            className="text-xs bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-md px-2 py-1"
          >
            Search
          </button>
          {qFilter && (
            <button
              type="button"
              onClick={() => { setQFilter(''); setQInput(''); }}
              className="text-xs text-gray-500 hover:text-gray-700 px-1"
            >
              Clear
            </button>
          )}
        </form>
        <button
          type="button"
          onClick={() => void fetchUrls(page)}
          className="ml-auto text-xs flex items-center gap-1 text-gray-500 hover:text-gray-700"
        >
          <RefreshCw className="w-3 h-3" />
          Refresh
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
          <span className="ml-2 text-sm text-gray-500">Loading URLs...</span>
        </div>
      ) : urls.length === 0 ? (
        <div className="text-center py-12 text-gray-500 text-sm">
          {statusFilter || discoveredViaFilter || qFilter
            ? 'No URLs match the current filters.'
            : 'No URLs yet. Add URLs manually or run a crawl.'}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">URL</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Via</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Depth</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Last crawled</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Next crawl</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Failures</th>
                <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {urls.map(url => {
                const badge = getStatusBadge(url.status as DomainUrlStatus);
                return (
                  <tr key={url.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2 max-w-xs">
                      <span
                        title={url.url}
                        className="block truncate text-gray-900 font-mono text-xs"
                      >
                        {url.url}
                      </span>
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${badge.className}`}>
                        {badge.text === 'Crawling' && <Loader2 className="w-3 h-3 animate-spin" />}
                        {badge.text}
                      </span>
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-500">
                      {(url.discovered_via as DiscoverySource)}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-500">
                      {url.depth}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-500">
                      {formatDate(url.last_crawled_at)}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-500">
                      <span title={url.consecutive_skips > 1 ? `${url.consecutive_skips} skips (backoff active)` : undefined}>
                        {formatDate(url.next_crawl_at)}
                        {url.consecutive_skips > 1 && (
                          <span className="ml-1 text-orange-500">({url.consecutive_skips}x)</span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-500">
                      {url.failure_count > 0 ? (
                        <span className="text-red-600 font-medium">{url.failure_count}</span>
                      ) : (
                        url.failure_count
                      )}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-right">
                      <ActionDropdown
                        size="sm"
                        actions={[
                          ...(onViewUrl ? [{
                            label: 'View detail',
                            onClick: () => onViewUrl(url.id),
                            icon: <Eye className="w-4 h-4" />,
                            variant: 'success' as const,
                          }] : []),
                          ...(canEdit ? [
                            {
                              label: 'Force re-crawl',
                              onClick: () => { void handleRecrawl(url.id); },
                              icon: recrawlingId === url.id
                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                : <RefreshCw className="w-4 h-4" />,
                              variant: 'primary' as const,
                              disabled: recrawlingId !== null,
                            },
                            {
                              label: 'Delete',
                              onClick: () => { void handleDelete(url.id); },
                              icon: deletingId === url.id
                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                : <Trash2 className="w-4 h-4" />,
                              variant: 'danger' as const,
                              disabled: deletingId !== null,
                            },
                          ] : []),
                        ]}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {!loading && total > PER_PAGE && (
        <div className="flex items-center justify-center gap-3 text-sm text-gray-600">
          <button
            type="button"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="flex items-center gap-1 px-2 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </button>
          <span>Page {page} of {totalPages} ({total} total)</span>
          <button
            type="button"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="flex items-center gap-1 px-2 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
