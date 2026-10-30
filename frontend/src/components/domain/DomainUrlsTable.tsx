import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, Trash2, Eye, Link } from 'lucide-react';
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
import TablePagination from '../ui/TablePagination';
import BackgroundImage from '../ui/BackgroundImage';

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

function formatDate(iso: string | null, language?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(language);
}

const PER_PAGE = 20;

export default function DomainUrlsTable({
  appId,
  domainId,
  canEdit,
  onViewUrl,
}: Readonly<DomainUrlsTableProps>) {
  const { t, i18n } = useTranslation('common');
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

  const statusOptions = [
    { value: '', label: t('domainDetailPage.urls.allStatuses') },
    ...(['PENDING', 'CRAWLING', 'INDEXED', 'SKIPPED', 'FAILED', 'REMOVED', 'EXCLUDED'] as const).map(status => ({
      value: status,
      label: t(`domainDetailPage.urls.statuses.${status.toLowerCase()}`),
    })),
  ];
  const discoveredViaOptions = [
    { value: '', label: t('domainDetailPage.urls.allSources') },
    ...(['SITEMAP', 'CRAWL', 'MANUAL'] as const).map(source => ({
      value: source,
      label: t(`domainDetailPage.urls.sources.${source.toLowerCase()}`),
    })),
  ];

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
      setError(err?.message ?? t('domainDetailPage.urls.errors.load'));
    } finally {
      setLoading(false);
    }
  }, [appId, domainId, statusFilter, discoveredViaFilter, qFilter, t]);

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
      setSuccessMessage(t('domainDetailPage.urls.recrawlQueued'));
      setTimeout(() => setSuccessMessage(null), 3000);
      void fetchUrls(page);
    } catch (err: any) {
      setError(err?.message ?? t('domainDetailPage.urls.errors.recrawl'));
    } finally {
      setRecrawlingId(null);
    }
  };

  const handleDelete = async (urlId: number) => {
    if (deletingId !== null) return;
    if (!confirm(t('domainDetailPage.urls.confirmDelete'))) return;
    try {
      setDeletingId(urlId);
      await apiService.deleteDomainUrl(appId, domainId, urlId);
      setSuccessMessage(t('domainDetailPage.urls.deleted'));
      setTimeout(() => setSuccessMessage(null), 3000);
      void fetchUrls(page);
    } catch (err: any) {
      setError(err?.message ?? t('domainDetailPage.urls.errors.delete'));
    } finally {
      setDeletingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  const columns: TableColumn<DomainUrl>[] = [
    {
      header: t('domainDetailPage.urls.columns.url'),
      className: 'px-6 py-4 max-w-xs',
      render: url => (
        <span title={url.url} className="block truncate text-fg dark:text-fg-dark font-mono text-xs">
          {url.url}
        </span>
      ),
    },
    {
      header: t('domainDetailPage.urls.columns.status'),
      className: 'px-6 py-4 whitespace-nowrap',
      render: url => {
        const badge = getStatusBadge(url.status as DomainUrlStatus);
        return (
          <Badge
            label={t(`domainDetailPage.urls.statuses.${url.status.toLowerCase()}`, { defaultValue: badge.text })}
            variant={badge.variant}
            className={badge.className}
            icon={url.status === 'CRAWLING' ? <Spinner size="xs" tone="current" /> : undefined}
          />
        );
      },
    },
    {
      header: t('domainDetailPage.urls.columns.via'),
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: url => t(`domainDetailPage.urls.sources.${String(url.discovered_via).toLowerCase()}`, { defaultValue: url.discovered_via as DiscoverySource }),
    },
    {
      header: t('domainDetailPage.urls.columns.depth'),
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: url => url.depth,
    },
    {
      header: t('domainDetailPage.urls.columns.lastCrawled'),
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: url => formatDate(url.last_crawled_at, i18n.resolvedLanguage),
    },
    {
      header: t('domainDetailPage.urls.columns.nextCrawl'),
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: url => (
        <span title={url.consecutive_skips > 1 ? t('domainDetailPage.urls.backoffTooltip', { count: url.consecutive_skips }) : undefined}>
          {formatDate(url.next_crawl_at, i18n.resolvedLanguage)}
          {url.consecutive_skips > 1 && (
            <span className="ml-1 text-orange-500">({url.consecutive_skips}x)</span>
          )}
        </span>
      ),
    },
    {
      header: t('domainDetailPage.urls.columns.failures'),
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: url => (
        url.failure_count > 0
          ? <span className="text-red-600 font-medium">{url.failure_count}</span>
          : url.failure_count
      ),
    },
    {
      header: t('domainDetailPage.urls.columns.actions'),
      headerClassName: 'text-right',
      className: 'px-6 py-4 whitespace-nowrap text-right',
      render: url => (
        <ActionDropdown
          size="sm"
          actions={[
            ...(onViewUrl ? [{
              label: t('domainDetailPage.urls.actions.viewDetail'),
              onClick: () => onViewUrl(url.id),
              icon: <Eye className="w-4 h-4" />,
              variant: 'success' as const,
            }] : []),
            ...(canEdit ? [
              {
                label: t('domainDetailPage.urls.actions.forceRecrawl'),
                onClick: () => { void handleRecrawl(url.id); },
                icon: recrawlingId === url.id
                  ? <Spinner size="sm" tone="current" />
                  : <RefreshCw className="w-4 h-4" />,
                variant: 'primary' as const,
                disabled: recrawlingId !== null,
              },
              {
                label: t('domainDetailPage.urls.actions.delete'),
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
          label={t('domainDetailPage.urls.filters.status')}
          labelClassName="sr-only"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          options={statusOptions}
        />
        <FormSelect
          id="discovered_via_filter"
          label={t('domainDetailPage.urls.filters.source')}
          labelClassName="sr-only"
          value={discoveredViaFilter}
          onChange={e => setDiscoveredViaFilter(e.target.value)}
          options={discoveredViaOptions}
        />
        <form onSubmit={handleSearchSubmit} className="flex gap-1">
          <FormField
            id="url_search"
            label={t('domainDetailPage.urls.filters.search')}
            labelClassName="sr-only"
            className="w-48"
            value={qInput}
            onChange={e => setQInput(e.target.value)}
            placeholder={t('domainDetailPage.urls.filters.searchPlaceholder')}
          />
          <ButtonApp
            type="submit"
            label={t('domainDetailPage.urls.filters.searchButton')}
            variant="secondary"
            size="small"
          />
          {qFilter && (
            <ButtonApp
              label={t('domainDetailPage.urls.filters.clear')}
              variant="secondary"
              size="small"
              onClick={() => { setQFilter(''); setQInput(''); }}
            />
          )}
        </form>
        <ButtonApp
          label={t('domainDetailPage.urls.filters.refresh')}
          variant="secondary"
          size="small"
          icon={<RefreshCw className="w-3 h-3" />}
          className="ml-auto"
          onClick={() => void fetchUrls(page)}
        />
      </div>

      {/* Table */}
      {loading ? (
        <LoadingState variant="section" message={t('domainDetailPage.urls.loading')} />
      ) : (
        <Table
          columns={columns}
          data={urls}
          keyExtractor={url => url.id}
          emptyMessage={
            statusFilter || discoveredViaFilter || qFilter
              ? t('domainDetailPage.urls.emptyFiltered')
              : t('domainDetailPage.urls.empty')
          }
          emptyIcon={<BackgroundImage icon={Link} size={40} iconSize={20} />}
        />
      )}

      {!loading && (
        <TablePagination page={page} totalPages={totalPages} totalItems={total} onPageChange={setPage} />
      )}
    </div>
  );
}
