import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
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

function jobStatusBadge(status: CrawlJobStatus) {
  switch (status) {
    case 'QUEUED': return { text: 'Queued', className: 'bg-yellow-100 text-yellow-800' };
    case 'RUNNING': return { text: 'Running', className: 'bg-blue-100 text-blue-800', spinner: true };
    case 'COMPLETED': return { text: 'Completed', className: 'bg-green-100 text-green-800' };
    case 'FAILED': return { text: 'Failed', className: 'bg-red-100 text-red-800' };
    case 'CANCELLED': return { text: 'Cancelled', className: 'bg-gray-100 text-gray-600' };
    default: return { text: status, className: 'bg-gray-100 text-gray-600' };
  }
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

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
    <div className="flex justify-center items-center py-12">
      <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
      <span className="ml-2 text-sm text-gray-500">Loading job history...</span>
    </div>
  );

  if (error) return <Alert type="error" message={error} onDismiss={() => setError(null)} />;

  if (jobs.length === 0) return (
    <div className="text-center py-12 text-gray-500 text-sm">No crawl jobs yet.</div>
  );

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Triggered by</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Finished</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Discovered</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Indexed</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Skipped</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Failed</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {jobs.map(job => {
              const badge = jobStatusBadge(job.status as CrawlJobStatus);
              return (
                <tr key={job.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-gray-500">#{job.id}</td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${badge.className}`}>
                      {(badge as any).spinner && <Loader2 className="w-3 h-3 animate-spin" />}
                      {badge.text}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500">
                    {job.triggered_by === 'MANUAL' ? 'Manual' : 'Scheduled'}
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-500">{formatDate(job.started_at)}</td>
                  <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-500">{formatDate(job.finished_at)}</td>
                  <td className="px-4 py-2 text-xs text-gray-500">{job.discovered_count}</td>
                  <td className="px-4 py-2 text-xs text-gray-500">{job.indexed_count}</td>
                  <td className="px-4 py-2 text-xs text-gray-500">{job.skipped_count}</td>
                  <td className="px-4 py-2 text-xs">
                    {job.failed_count > 0
                      ? <span className="text-red-600 font-medium">{job.failed_count}</span>
                      : job.failed_count}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

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
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (error || !domain) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
          {error ?? 'Domain not found'}
        </div>
        <button
          onClick={() => navigate(`/apps/${appId}`)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
        >
          Back to App
        </button>
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
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{domain.name}</h1>
          {domain.description && <p className="text-gray-600 mt-1">{domain.description}</p>}
          <p className="text-sm text-gray-400 mt-1 font-mono">{domain.base_url}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate(`/apps/${appId}/domains/${domainId}/edit`)}
            className="text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded-lg"
          >
            Edit domain
          </button>
          <button
            onClick={() => navigate(`/apps/${appId}/domains`)}
            className="text-sm bg-gray-600 text-white px-3 py-1.5 rounded-lg hover:bg-gray-700"
          >
            Back to Domains
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab} className="mb-6" />

      {/* Tab: Configuration */}
      {activeTab === 'configuration' && (
        <div className="space-y-6">
          {/* Scraping config (read-only display) */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Scraping configuration</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-gray-500 text-xs font-medium uppercase tracking-wide">Content tag</span>
                <p className="text-gray-900 mt-0.5">{domain.content_tag || 'body'}</p>
              </div>
              <div>
                <span className="text-gray-500 text-xs font-medium uppercase tracking-wide">Content class</span>
                <p className="text-gray-900 mt-0.5">{domain.content_class || '—'}</p>
              </div>
              <div>
                <span className="text-gray-500 text-xs font-medium uppercase tracking-wide">Content ID</span>
                <p className="text-gray-900 mt-0.5">{domain.content_id || '—'}</p>
              </div>
            </div>
          </div>

          {/* Crawl policy */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Crawl policy</h2>
            <CrawlPolicyForm
              appId={numericAppId}
              domainId={numericDomainId}
              canEdit={canEdit}
              onSaved={() => {
                setSuccessMessage('Crawl policy saved');
                setTimeout(() => setSuccessMessage(null), 3000);
              }}
            />
          </div>
        </div>
      )}

      {/* Tab: URLs */}
      {activeTab === 'urls' && (
        <div className="space-y-6">
          {/* Crawl job controls */}
          <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Crawl job</h2>
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
          </div>

          {/* URL table */}
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">URLs ({domain.url_count})</h2>
            <DomainUrlsTable
              appId={numericAppId}
              domainId={numericDomainId}
              canEdit={canEdit}
              onViewUrl={setSelectedUrlId}
            />
          </div>

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
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Crawl job history</h2>
          <JobHistoryTab appId={numericAppId} domainId={numericDomainId} />
        </div>
      )}
    </div>
  );
};

export default DomainDetailPage;
