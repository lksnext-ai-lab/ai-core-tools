import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Briefcase, CheckCircle2, XCircle } from 'lucide-react';
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
import TablePagination from '../components/ui/TablePagination';
import BackgroundImage from '../components/ui/BackgroundImage';

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

// ==================== Job history table ====================

function jobStatusBadge(status: CrawlJobStatus): { text: string; variant: BadgeVariant; spinner?: boolean } {
  switch (status) {
    case 'QUEUED': return { text: 'queued', variant: 'warning' };
    case 'RUNNING': return { text: 'running', variant: 'info', spinner: true };
    case 'COMPLETED': return { text: 'completed', variant: 'success' };
    case 'FAILED': return { text: 'failed', variant: 'error' };
    case 'CANCELLED': return { text: 'cancelled', variant: 'default' };
    default: return { text: status, variant: 'default' };
  }
}

function formatDate(iso: string | null | undefined, language?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(language);
}

interface JobHistoryTabProps {
  appId: number;
  domainId: number;
}

function JobHistoryTab({ appId, domainId }: Readonly<JobHistoryTabProps>) {
  const { t, i18n } = useTranslation('common');
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
      setError(err?.message ?? t('domainDetailPage.jobHistory.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [appId, domainId, t]);

  useEffect(() => {
    void fetchJobs(page);
  }, [fetchJobs, page]);

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  const columns: TableColumn<CrawlJob>[] = [
    { header: t('domainDetailPage.jobHistory.columns.id'), render: job => <span className="text-fg-secondary dark:text-fg-secondary-dark">#{job.id}</span> },
    {
      header: t('domainDetailPage.jobHistory.columns.status'),
      render: job => {
        const badge = jobStatusBadge(job.status as CrawlJobStatus);
        return (
          <Badge
            label={t(`domainDetailPage.jobStatuses.${badge.text}`, { defaultValue: badge.text })}
            variant={badge.variant}
            icon={badge.spinner ? <Spinner size="xs" tone="current" /> : undefined}
          />
        );
      },
    },
    {
      header: t('domainDetailPage.jobHistory.columns.triggeredBy'),
      render: job => (
        <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
          {job.triggered_by === 'MANUAL' ? t('domainDetailPage.jobHistory.manual') : t('domainDetailPage.jobHistory.scheduled')}
        </span>
      ),
    },
    {
      header: t('domainDetailPage.jobHistory.columns.started'),
      render: job => <span className="whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark">{formatDate(job.started_at, i18n.resolvedLanguage)}</span>,
    },
    {
      header: t('domainDetailPage.jobHistory.columns.finished'),
      render: job => <span className="whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark">{formatDate(job.finished_at, i18n.resolvedLanguage)}</span>,
    },
    { header: t('domainDetailPage.jobHistory.columns.discovered'), accessor: 'discovered_count' },
    { header: t('domainDetailPage.jobHistory.columns.indexed'), accessor: 'indexed_count' },
    { header: t('domainDetailPage.jobHistory.columns.skipped'), accessor: 'skipped_count' },
    {
      header: t('domainDetailPage.jobHistory.columns.failed'),
      render: job => job.failed_count > 0
        ? <span className="font-medium text-red-600">{job.failed_count}</span>
        : job.failed_count,
    },
  ];

  if (loading) return (
    <LoadingState variant="section" message={t('domainDetailPage.jobHistory.loading')} />
  );

  if (error) return <Alert type="error" message={error} onDismiss={() => setError(null)} />;

  return (
    <div className="space-y-4">
      <Table
        columns={columns}
        data={jobs}
        keyExtractor={job => job.id}
        emptyMessage={t('domainDetailPage.jobHistory.empty')}
        emptyIcon={<BackgroundImage icon={Briefcase} size={40} iconSize={20} />}
      />

      <TablePagination page={page} totalPages={totalPages} onPageChange={setPage} />
    </div>
  );
}

// ==================== Main page component ====================

const DomainDetailPage: React.FC = () => {
  const { appId, domainId } = useParams<{ appId: string; domainId: string }>();
  const { t } = useTranslation('common');
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
      setError(t('domainDetailPage.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [numericAppId, numericDomainId, t]);

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
    setSuccessMessage(t('domainDetailPage.crawlJobQueued'));
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  if (loading) {
    return (
      <LoadingState variant="page" message={t('domainDetailPage.loading')} />
    );
  }

  if (error || !domain) {
    return (
      <div className="p-6">
        <Alert type="error" message={error ?? t('domainDetailPage.notFound')} className="mb-4" />
        <ButtonApp
          label={t('domainDetailPage.backToApp')}
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
            label={t('domainDetailPage.editDomain')}
            variant="primary"
            size="medium"
            onClick={() => navigate(`/apps/${appId}/domains/${domainId}`)}
          />
          
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        tabs={[
          { id: 'configuration', label: t('domainDetailPage.tabs.configuration') },
          { id: 'urls', label: t('domainDetailPage.tabs.urls') },
          { id: 'job-history', label: t('domainDetailPage.tabs.jobHistory') },
        ]}
        activeTab={activeTab}
        onChange={setActiveTab}
        className="mb-6"
      />

      {/* Tab: Configuration */}
      {activeTab === 'configuration' && (
        <div className="space-y-6">
          {/* Scraping config (read-only display) */}
          <CardApp className="p-6">
            <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">{t('domainDetailPage.configuration.title')}</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs font-medium uppercase tracking-wide">{t('domainDetailPage.configuration.contentTag')}</span>
                <p className="text-fg dark:text-fg-dark mt-0.5">{domain.content_tag || 'body'}</p>
              </div>
              <div>
                <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs font-medium uppercase tracking-wide">{t('domainDetailPage.configuration.contentClass')}</span>
                <p className="text-fg dark:text-fg-dark mt-0.5">{domain.content_class || '—'}</p>
              </div>
              <div>
                <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs font-medium uppercase tracking-wide">{t('domainDetailPage.configuration.contentId')}</span>
                <p className="text-fg dark:text-fg-dark mt-0.5">{domain.content_id || '—'}</p>
              </div>
            </div>
          </CardApp>

          {/* Crawl policy */}
          <CardApp className="p-6">
            <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">{t('domainDetailPage.crawlPolicy')}</h2>
            <CrawlPolicyForm
              appId={numericAppId}
              domainId={numericDomainId}
              canEdit={canEdit}
              onSaved={() => {
                setSuccessMessage(t('domainDetailPage.crawlPolicySaved'));
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
              <h2 className="text-lg font-semibold text-fg dark:text-fg-dark">{t('domainDetailPage.crawlJob')}</h2>
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
          <CardApp>
            <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">{t('domainDetailPage.urlsCount', { count: domain.url_count })}</h2>
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
        <CardApp>
          <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">{t('domainDetailPage.crawlJobHistory')}</h2>
          <JobHistoryTab appId={numericAppId} domainId={numericDomainId} />
        </CardApp>
      )}
    </div>
  );
};

export default DomainDetailPage;
