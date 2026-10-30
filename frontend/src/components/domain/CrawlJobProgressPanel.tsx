import { useState, useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, XCircle, Ban, Clock } from 'lucide-react';
import { apiService } from '../../services/api';
import type { CrawlJob, CrawlJobStatus } from '../../types/crawl';
import { Spinner } from '../ui/Spinner';
import { Badge, type BadgeVariant } from '../ui/Badge';
import { ButtonApp } from '../ui/ButtonApp';
import CardApp from '../ui/CardApp';
import { Alert } from '../..';

interface CrawlJobProgressPanelProps {
  appId: number;
  domainId: number;
  initialJob?: CrawlJob | null;
  canEdit: boolean;
  onJobUpdate?: (job: CrawlJob) => void;
}

const ACTIVE_STATUSES: CrawlJobStatus[] = ['QUEUED', 'RUNNING'];
const POLL_INTERVAL_MS = 2000;

function statusBadge(status: CrawlJobStatus): { text: string; variant: BadgeVariant; icon: ReactNode } {
  switch (status) {
    case 'QUEUED':
      return { text: 'queued', variant: 'warning', icon: <Clock className="w-3 h-3" /> };
    case 'RUNNING':
      return { text: 'running', variant: 'info', icon: <Spinner size="xs" tone="current" /> };
    case 'COMPLETED':
      return { text: 'completed', variant: 'success', icon: <CheckCircle2 className="w-3 h-3" /> };
    case 'FAILED':
      return { text: 'failed', variant: 'error', icon: <XCircle className="w-3 h-3" /> };
    case 'CANCELLED':
      return { text: 'cancelled', variant: 'default', icon: <Ban className="w-3 h-3" /> };
    default:
      return { text: status, variant: 'default', icon: null };
  }
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return '—';
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

export default function CrawlJobProgressPanel({
  appId,
  domainId,
  initialJob = null,
  canEdit,
  onJobUpdate,
}: Readonly<CrawlJobProgressPanelProps>) {
  const { t, i18n } = useTranslation('common');
  const [currentJob, setCurrentJob] = useState<CrawlJob | null>(initialJob ?? null);
  const [cancelling, setCancelling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Sync initialJob changes from parent (e.g. when a new job is triggered)
  useEffect(() => {
    setCurrentJob(initialJob ?? null);
  }, [initialJob]);

  // Polling while job is active
  useEffect(() => {
    if (!currentJob || !ACTIVE_STATUSES.includes(currentJob.status)) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const updated = await apiService.getCrawlJob(appId, domainId, currentJob.id);
        setCurrentJob(updated);
        onJobUpdate?.(updated);
        if (!ACTIVE_STATUSES.includes(updated.status)) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch {
        // Silently ignore poll errors; will retry next interval
      }
    };

    intervalRef.current = setInterval(() => { void poll(); }, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [appId, domainId, currentJob?.id, currentJob?.status]);

  const handleCancel = async () => {
    if (!currentJob || cancelling) return;
    try {
      setCancelling(true);
      const updated = await apiService.cancelCrawl(appId, domainId, currentJob.id);
      setCurrentJob(updated);
      onJobUpdate?.(updated);
    } catch {
      // Error shown via status update on next poll
    } finally {
      setCancelling(false);
    }
  };

  if (!currentJob) {
    return (
      <div className="text-center py-8 text-fg-secondary dark:text-fg-secondary-dark text-sm">
        {t('domainDetailPage.crawlProgress.noJobs', { action: t('domainDetailPage.runCrawl.runNow') })}
      </div>
    );
  }

  const badge = statusBadge(currentJob.status);
  const isActive = ACTIVE_STATUSES.includes(currentJob.status);

  return (
    <div className=" p-4 space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge label={t(`domainDetailPage.jobStatuses.${badge.text}`, { defaultValue: badge.text })} variant={badge.variant} icon={badge.icon} />
          <span className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('domainDetailPage.crawlProgress.job', { id: currentJob.id })}</span>
          <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {currentJob.triggered_by === 'MANUAL' ? t('domainDetailPage.crawlProgress.manualTrigger') : t('domainDetailPage.crawlProgress.scheduled')}
          </span>
        </div>

        

        {canEdit && isActive && (
          <ButtonApp
            label={cancelling ? t('domainDetailPage.crawlProgress.cancelling') : t('domainDetailPage.crawlProgress.cancel')}
            variant="danger"
            size="medium"
            onClick={() => { void handleCancel(); }}
            disabled={cancelling}
          />
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 md:grid-cols-5 gap-2 text-center">
        {(
          [
            { label: t('domainDetailPage.crawlProgress.discovered'), value: currentJob.discovered_count },
            { label: t('domainDetailPage.crawlProgress.indexed'), value: currentJob.indexed_count },
            { label: t('domainDetailPage.crawlProgress.skipped'), value: currentJob.skipped_count },
            { label: t('domainDetailPage.crawlProgress.failed'), value: currentJob.failed_count },
            { label: t('domainDetailPage.crawlProgress.removed'), value: currentJob.removed_count },
          ] as const
        ).map(({ label, value }) => (
          <CardApp variant="white" key={label} className=" p-2">
            <p className="text-xs font-medium uppercase tracking-wide text-fg dark:text-fg-dark">{label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-fg dark:text-fg-dark">{value}</p>
          </CardApp>
        ))}
      </div>

      {/* Timing */}
      <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark flex gap-4">
        <span>{t('domainDetailPage.crawlProgress.duration')}: {formatDuration(currentJob.started_at, currentJob.finished_at)}</span>
        {currentJob.started_at && (
          <span>{t('domainDetailPage.crawlProgress.started')}: {new Date(currentJob.started_at).toLocaleString(i18n.resolvedLanguage)}</span>
        )}
      </div>
        
      {/* Error log (terminal failure only) */}
      {currentJob.status === 'FAILED' && currentJob.error_log && (
        <Alert type="error" title="" message={currentJob.error_log} />
      )}
    </div>
  );
}
