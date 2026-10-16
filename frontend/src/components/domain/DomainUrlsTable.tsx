import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Trash2, Eye, ChevronLeft, ChevronRight } from 'lucide-react';
import { apiService } from '../../services/api';
import ActionDropdown from '../ui/ActionDropdown';
import Alert from '../ui/Alert';
import type { DomainUrl, DomainUrlStatus, DiscoverySource } from '../../types/crawl';
import { Spinner } from '../ui/Spinner';
import { Badge, type BadgeVariant } from '../ui/Badge';
import { LoadingState } from '../ui/LoadingState';
import { FormField, FormSelect } from '../ui/FormField';
import { ButtonApp } from '../ui/ButtonApp';
import Table, { type TableColumn } from '../ui/Table';

interface DomainUrlsTableProps {
  appId: number;
  domainId: number;
  canEdit: boolean;
  onViewUrl?: (urlId: number) => void;
}

function getStatusBadge(status: DomainUrlStatus): { text: string; variant: BadgeVariant; className?: string } {
  switch (status) {
    case 'PENDING':
      return { text: 'Pending', variant: 'warning' };
    case 'CRAWLING':
      return { text: 'Crawling', variant: 'info' };
    case 'INDEXED':
      return { text: 'Indexed', variant: 'success' };
    case 'SKIPPED':
      return { text: 'Skipped', variant: 'default' };
    case 'FAILED':
      return { text: 'Failed', variant: 'error' };
    case 'REMOVED':
      return { text: 'Removed', variant: 'default', className: 'line-through opacity-70' };
    case 'EXCLUDED':
      return { text: 'Excluded', variant: 'secondary' };
    default:
      return { text: status, variant: 'default' };
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

  const columns: TableColumn<DomainUrl>[] = [
    {
      header: 'URL',
      className: 'px-6 py-4 max-w-xs',
      render: url => (
        <span title={url.url} className="block truncate text-gray-900 font-mono text-xs">
          {url.url}
        </span>
      ),
    },
    {
      header: 'Status',
      className: 'px-6 py-4 whitespace-nowrap',
      render: url => {
        const badge = getStatusBadge(url.status as DomainUrlStatus);
        return (
          <Badge
            label={badge.text}
            variant={badge.variant}
            className={badge.className}
            icon={badge.text === 'Crawling' ? <Spinner size="xs" tone="current" /> : undefined}
          />
        );
      },
    },
    {
      header: 'Via',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-gray-500',
      render: url => url.discovered_via as DiscoverySource,
    },
    {
      header: 'Depth',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-gray-500',
      render: url => url.depth,
    },
    {
      header: 'Last crawled',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-gray-500',
      render: url => formatDate(url.last_crawled_at),
    },
    {
      header: 'Next crawl',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-gray-500',
      render: url => (
        <span title={url.consecutive_skips > 1 ? `${url.consecutive_skips} skips (backoff active)` : undefined}>
          {formatDate(url.next_crawl_at)}
          {url.consecutive_skips > 1 && (
            <span className="ml-1 text-orange-500">({url.consecutive_skips}x)</span>
          )}
        </span>
      ),
    },
    {
      header: 'Failures',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-gray-500',
      render: url => (
        url.failure_count > 0
          ? <span className="text-red-600 font-medium">{url.failure_count}</span>
          : url.failure_count
      ),
    },
    {
      header: 'Actions',
      headerClassName: 'text-right',
      className: 'px-6 py-4 whitespace-nowrap text-right',
      render: url => (
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
                  ? <Spinner size="sm" tone="current" />
                  : <RefreshCw className="w-4 h-4" />,
                variant: 'primary' as const,
                disabled: recrawlingId !== null,
              },
              {
                label: 'Delete',
                onClick: () => { void handleDelete(url.id); },
                icon: deletingId === url.id
                  ? <Spinner size="sm" tone="current" />
                  : <Trash2 className="w-4 h-4" />,
                variant: 'danger' as const,
                disabled: deletingId !== null,
              },
            ] : []),
          ]}
        />
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}
      {successMessage && <Alert type="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />}

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center">
        <FormSelect
          id="status_filter"
          label="Status"
          labelClassName="sr-only"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          options={STATUS_OPTIONS}
        />
        <FormSelect
          id="discovered_via_filter"
          label="Source"
          labelClassName="sr-only"
          value={discoveredViaFilter}
          onChange={e => setDiscoveredViaFilter(e.target.value)}
          options={DISCOVERED_VIA_OPTIONS}
        />
        <form onSubmit={handleSearchSubmit} className="flex gap-1">
          <FormField
            id="url_search"
            label="Search URLs"
            labelClassName="sr-only"
            className="w-48"
            value={qInput}
            onChange={e => setQInput(e.target.value)}
            placeholder="Search URLs..."
          />
          <ButtonApp
            type="submit"
            label="Search"
            variant="secondary"
            size="small"
          />
          {qFilter && (
            <ButtonApp
              label="Clear"
              variant="secondary"
              size="small"
              onClick={() => { setQFilter(''); setQInput(''); }}
            />
          )}
        </form>
        <ButtonApp
          label="Refresh"
          variant="secondary"
          size="small"
          icon={<RefreshCw className="w-3 h-3" />}
          className="ml-auto"
          onClick={() => void fetchUrls(page)}
        />
      </div>

      {/* Table */}
      {loading ? (
        <LoadingState variant="section" message="Loading URLs..." />
      ) : (
        <Table
          columns={columns}
          data={urls}
          keyExtractor={url => url.id}
          emptyMessage={
            statusFilter || discoveredViaFilter || qFilter
              ? 'No URLs match the current filters.'
              : 'No URLs yet. Add URLs manually or run a crawl.'
          }
        />
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
