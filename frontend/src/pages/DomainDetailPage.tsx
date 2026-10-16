import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CheckCircle2, XCircle } from 'lucide-react';
import { apiService } from '../services/api';
import Alert from '../components/ui/Alert';
import { Tabs } from '../components/ui/Tabs';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import CrawlPolicyForm from '../components/forms/CrawlPolicyForm';
import CrawlJobProgressPanel from '../components/domain/CrawlJobProgressPanel';
import RunCrawlNowButton from '../components/domain/RunCrawlNowButton';
import DomainUrlsTable from '../components/domain/DomainUrlsTable';
import DomainUrlDrawer from '../components/domain/DomainUrlDrawer';
import type { CrawlJob, CrawlJobStatus } from '../types/crawl';
import { LoadingState } from '../components/ui/LoadingState';
import { Spinner } from '../components/ui/Spinner';
import { Badge, type BadgeVariant } from '../components/ui/Badge';
import { ButtonApp } from '../components/ui/ButtonApp';
import Title from '../components/ui/Title';
import CardApp from '../components/ui/CardApp';
import Table, { type TableColumn } from '../components/ui/Table';

interface DomainDetail {
  domain_id: number;
  name: string;
  description: string;
  base_url: string;
  content_tag: string;
  content_class: string;
  content_id: string;
  created_at: string;
  url_count: number;
  silo_id?: number;
  embedding_service_id?: number;
  embedding_services: Array<{ service_id: number; name: string }>;
}

// ==================== Tab definitions ====================

const TABS = [
  { id: 'configuration', label: 'Configuration' },
  { id: 'urls', label: 'URLs' },
  { id: 'job-history', label: 'Job history' },
];

// ==================== Job history table ====================

function jobStatusBadge(status: CrawlJobStatus): { text: string; variant: BadgeVariant; spinner?: boolean } {
  switch (status) {
    case 'QUEUED': return { text: 'Queued', variant: 'warning' };
    case 'RUNNING': return { text: 'Running', variant: 'info', spinner: true };
    case 'COMPLETED': return { text: 'Completed', variant: 'success' };
    case 'FAILED': return { text: 'Failed', variant: 'error' };
    case 'CANCELLED': return { text: 'Cancelled', variant: 'default' };
    default: return { text: status, variant: 'default' };
  }
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

const JOB_HISTORY_COLUMNS: TableColumn<CrawlJob>[] = [
  { header: 'ID', render: job => <span className="text-fg-secondary dark:text-fg-secondary-dark">#{job.id}</span> },
  {
    header: 'Status',
    render: job => {
      const badge = jobStatusBadge(job.status as CrawlJobStatus);
      return (
        <Badge
          label={badge.text}
          variant={badge.variant}
          icon={badge.spinner ? <Spinner size="xs" tone="current" /> : undefined}
        />
      );
    },
  },
  {
    header: 'Triggered by',
    render: job => (
      <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
        {job.triggered_by === 'MANUAL' ? 'Manual' : 'Scheduled'}
      </span>
    ),
  },
  {
    header: 'Started',
    render: job => <span className="whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark">{formatDate(job.started_at)}</span>,
  },
  {
    header: 'Finished',
    render: job => <span className="whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark">{formatDate(job.finished_at)}</span>,
  },
  { header: 'Discovered', accessor: 'discovered_count' },
  { header: 'Indexed', accessor: 'indexed_count' },
  { header: 'Skipped', accessor: 'skipped_count' },
  {
    header: 'Failed',
    render: job => job.failed_count > 0
      ? <span className="font-medium text-red-600">{job.failed_count}</span>
      : job.failed_count,
  },
];

interface JobHistoryTabProps {
  appId: number;
  domainId: number;
}

function JobHistoryTab({ appId, domainId }: Readonly<JobHistoryTabProps>) {
  const [jobs, setJobs] = useState<CrawlJob[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const PER_PAGE = 10;

  const fetchJobs = useCallback(async (p: number) => {
    try {
      setLoading(true);
      setError(null);
      const resp = await apiService.listCrawlJobs(appId, domainId, { page: p, per_page: PER_PAGE });
      setJobs(resp.items);
      setTotal(resp.total);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to load job history');
    } finally {
      setLoading(false);
    }
  }, [appId, domainId]);

  useEffect(() => {
    void fetchJobs(page);
  }, [fetchJobs, page]);

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  if (loading) return (
    <LoadingState variant="section" message="Loading job history..." />
  );

  if (error) return <Alert type="error" message={error} onDismiss={() => setError(null)} />;

  return (
    <div className="space-y-4">
      <Table
        columns={JOB_HISTORY_COLUMNS}
        data={jobs}
        keyExtractor={job => job.id}
        emptyMessage="No crawl jobs yet."
      />

      {total > PER_PAGE && (
        <div className="flex items-center justify-center gap-3 text-sm text-gray-600">
          <button
            type="button"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-2 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50 text-xs"
          >
            Previous
          </button>
          <span>Page {page} of {totalPages}</span>
          <button
            type="button"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-2 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50 text-xs"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ==================== Main page component ====================

const DomainDetailPage: React.FC = () => {
  const { appId, domainId } = useParams<{ appId: string; domainId: string }>();
  const navigate = useNavigate();
  const { hasMinRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);

  const [domain, setDomain] = useState<DomainDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('configuration');

  // URLs tab state
  const [selectedUrlId, setSelectedUrlId] = useState<number | null>(null);
  const [latestJob, setLatestJob] = useState<CrawlJob | null>(null);
  const [latestJobLoading, setLatestJobLoading] = useState(true);

  // Global notifications
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const numericAppId = Number.parseInt(appId!);
  const numericDomainId = Number.parseInt(domainId!);

  const loadDomain = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiService.getDomain(numericAppId, numericDomainId);
      setDomain(data);
      setError(null);
    } catch {
      setError('Failed to load domain');
    } finally {
      setLoading(false);
    }
  }, [numericAppId, numericDomainId]);

  const loadLatestJob = useCallback(async () => {
    try {
      setLatestJobLoading(true);
      const resp = await apiService.listCrawlJobs(numericAppId, numericDomainId, { page: 1, per_page: 1 });
      setLatestJob(resp.items[0] ?? null);
    } catch {
      // Silently ignore — panel will show "No crawl jobs yet"
    } finally {
      setLatestJobLoading(false);
    }
  }, [numericAppId, numericDomainId]);

  useEffect(() => {
    if (appId && domainId) {
      void loadDomain();
      void loadLatestJob();
    }
  }, [appId, domainId, loadDomain, loadLatestJob]);

  const handleJobTriggered = (job: CrawlJob) => {
    setLatestJob(job);
    setSuccessMessage('Crawl job queued');
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  if (loading) {
    return (
      <LoadingState variant="page" />
    );
  }

  if (error || !domain) {
    return (
      <div className="p-6">
        <Alert type="error" message={error ?? 'Domain not found'} className="mb-4" />
        <ButtonApp
          label="Back to App"
          variant="secondary"
          size="medium"
          onClick={() => navigate(`/apps/${appId}`)}
        />
      </div>
    );
  }

  const statusIcons = {
    COMPLETED: <CheckCircle2 className="w-4 h-4 text-green-500" />,
    FAILED: <XCircle className="w-4 h-4 text-red-500" />,
  };
  void statusIcons; // suppress unused warning

  return (
    <div className="p-6">
      {successMessage && <Alert type="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} className="mb-4" />}
      {errorMessage && <Alert type="error" message={errorMessage} onDismiss={() => setErrorMessage(null)} className="mb-4" />}

      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <Title
          variant="titPrincipal"
          titulo={domain.name}
          subtitulo={`${domain.description}\n${domain.base_url}`}
          subtitleMarginBottom={20}
        />
        <div className="flex gap-2">
          <ButtonApp
            label="Edit domain"
            variant="primary"
            size="medium"
            onClick={() => navigate(`/apps/${appId}/domains/${domainId}`)}
          />
          
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab} className="mb-6" />

      {/* Tab: Configuration */}
      {activeTab === 'configuration' && (
        <div className="space-y-6">
          {/* Scraping config (read-only display) */}
          <CardApp className="p-6">
            <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">Scraping configuration</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs font-medium uppercase tracking-wide">Content tag</span>
                <p className="text-fg dark:text-fg-dark mt-0.5">{domain.content_tag || 'body'}</p>
              </div>
              <div>
                <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs font-medium uppercase tracking-wide">Content class</span>
                <p className="text-fg dark:text-fg-dark mt-0.5">{domain.content_class || '—'}</p>
              </div>
              <div>
                <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs font-medium uppercase tracking-wide">Content ID</span>
                <p className="text-fg dark:text-fg-dark mt-0.5">{domain.content_id || '—'}</p>
              </div>
            </div>
          </CardApp>

          {/* Crawl policy */}
          <CardApp className="p-6">
            <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">Crawl policy</h2>
            <CrawlPolicyForm
              appId={numericAppId}
              domainId={numericDomainId}
              canEdit={canEdit}
              onSaved={() => {
                setSuccessMessage('Crawl policy saved');
                setTimeout(() => setSuccessMessage(null), 3000);
              }}
            />
          </CardApp>
        </div>
      )}

      {/* Tab: URLs */}
      {activeTab === 'urls' && (
        <div className="space-y-6">
          {/* Crawl job controls */}
          <CardApp className=" p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-fg dark:text-fg-dark">Crawl job</h2>
              {canEdit && (
                <RunCrawlNowButton
                  appId={numericAppId}
                  domainId={numericDomainId}
                  onJobTriggered={handleJobTriggered}
                  disabled={latestJobLoading}
                />
              )}
            </div>
            {!latestJobLoading && (
              <CrawlJobProgressPanel
                appId={numericAppId}
                domainId={numericDomainId}
                initialJob={latestJob}
                canEdit={canEdit}
                onJobUpdate={setLatestJob}
              />
            )}
          </CardApp>

          {/* URL table */}
          <CardApp className="bg-white border border-gray-200 rounded-lg p-4">
            <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">URLs ({domain.url_count})</h2>
            <DomainUrlsTable
              appId={numericAppId}
              domainId={numericDomainId}
              canEdit={canEdit}
              onViewUrl={setSelectedUrlId}
            />
          </CardApp>

          {/* URL detail drawer */}
          <DomainUrlDrawer
            appId={numericAppId}
            domainId={numericDomainId}
            urlId={selectedUrlId}
            canEdit={canEdit}
            onClose={() => setSelectedUrlId(null)}
          />
        </div>
      )}

      {/* Tab: Job history */}
      {activeTab === 'job-history' && (
        <CardApp className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">Crawl job history</h2>
          <JobHistoryTab appId={numericAppId} domainId={numericDomainId} />
        </CardApp>
      )}
    </div>
  );
};

export default DomainDetailPage;
