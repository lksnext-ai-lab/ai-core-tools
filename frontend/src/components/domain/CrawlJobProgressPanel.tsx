import { useState, useEffect, useRef } from 'react';
import { Loader2, CheckCircle2, XCircle, Ban, Clock } from 'lucide-react';
import { apiService } from '../../services/api';
import type { CrawlJob, CrawlJobStatus } from '../../types/crawl';

interface CrawlJobProgressPanelProps {
  appId: number;
  domainId: number;
  initialJob?: CrawlJob | null;
  canEdit: boolean;
  onJobUpdate?: (job: CrawlJob) => void;
}

const ACTIVE_STATUSES: CrawlJobStatus[] = ['QUEUED', 'RUNNING'];
const POLL_INTERVAL_MS = 2000;

function statusBadge(status: CrawlJobStatus) {
  switch (status) {
    case 'QUEUED':
      return { text: 'Queued', className: 'bg-yellow-100 text-yellow-800', icon: <Clock className="w-3 h-3" /> };
    case 'RUNNING':
      return { text: 'Running', className: 'bg-blue-100 text-blue-800', icon: <Loader2 className="w-3 h-3 animate-spin" /> };
    case 'COMPLETED':
      return { text: 'Completed', className: 'bg-green-100 text-green-800', icon: <CheckCircle2 className="w-3 h-3" /> };
    case 'FAILED':
      return { text: 'Failed', className: 'bg-red-100 text-red-800', icon: <XCircle className="w-3 h-3" /> };
    case 'CANCELLED':
      return { text: 'Cancelled', className: 'bg-gray-100 text-gray-600', icon: <Ban className="w-3 h-3" /> };
    default:
      return { text: status, className: 'bg-gray-100 text-gray-600', icon: null };
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      <div className="text-center py-8 text-gray-500 text-sm">
        No crawl jobs yet. Use "Run crawl now" to start the first crawl.
      </div>
    );
  }

  const badge = statusBadge(currentJob.status);
  const isActive = ACTIVE_STATUSES.includes(currentJob.status);

  return (
    <div className="border border-gray-200 rounded-lg p-4 space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${badge.className}`}>
            {badge.icon}
            {badge.text}
          </span>
          <span className="text-xs text-gray-500">Job #{currentJob.id}</span>
          <span className="text-xs text-gray-400">
            {currentJob.triggered_by === 'MANUAL' ? 'Manual trigger' : 'Scheduled'}
          </span>
        </div>

        {canEdit && isActive && (
          <button
            type="button"
            onClick={() => { void handleCancel(); }}
            disabled={cancelling}
            className="text-xs text-red-600 hover:text-red-800 disabled:opacity-50 border border-red-300 rounded px-2 py-0.5"
          >
            {cancelling ? 'Cancelling...' : 'Cancel'}
          </button>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 md:grid-cols-5 gap-2 text-center">
        {(
          [
            { label: 'Discovered', value: currentJob.discovered_count },
            { label: 'Indexed', value: currentJob.indexed_count },
            { label: 'Skipped', value: currentJob.skipped_count },
            { label: 'Failed', value: currentJob.failed_count },
            { label: 'Removed', value: currentJob.removed_count },
          ] as const
        ).map(({ label, value }) => (
          <div key={label} className="bg-gray-50 rounded p-2">
            <p className="text-lg font-semibold text-gray-800">{value}</p>
            <p className="text-xs text-gray-500">{label}</p>
          </div>
        ))}
      </div>

      {/* Timing */}
      <div className="text-xs text-gray-500 flex gap-4">
        <span>Duration: {formatDuration(currentJob.started_at, currentJob.finished_at)}</span>
        {currentJob.started_at && (
          <span>Started: {new Date(currentJob.started_at).toLocaleString()}</span>
        )}
      </div>

      {/* Error log (terminal failure only) */}
      {currentJob.status === 'FAILED' && currentJob.error_log && (
        <div className="bg-red-50 border border-red-200 rounded p-2 text-xs text-red-700 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
          {currentJob.error_log}
        </div>
      )}
    </div>
  );
}
