import { useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { apiService } from '../../services/api';
import type { CrawlJob } from '../../types/crawl';

interface RunCrawlNowButtonProps {
  appId: number;
  domainId: number;
  onJobTriggered: (job: CrawlJob) => void;
  disabled?: boolean;
}

export default function RunCrawlNowButton({
  appId,
  domainId,
  onJobTriggered,
  disabled = false,
}: Readonly<RunCrawlNowButtonProps>) {
  const [loading, setLoading] = useState(false);
  const [conflictNotice, setConflictNotice] = useState(false);

  const handleClick = async () => {
    if (loading || disabled) return;
    try {
      setLoading(true);
      setConflictNotice(false);
      const response = await apiService.triggerCrawl(appId, domainId);
      // Fetch the created job detail so callers get a CrawlJob object
      const job = await apiService.getCrawlJob(appId, domainId, response.job_id);
      onJobTriggered(job);
    } catch (err: any) {
      const msg = String(err?.message ?? '');
      if (msg.includes('409') || msg.toLowerCase().includes('already queued') || msg.toLowerCase().includes('already running')) {
        setConflictNotice(true);
        setTimeout(() => setConflictNotice(false), 5000);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={() => { void handleClick(); }}
        disabled={disabled || loading}
        className="flex items-center gap-2 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Play className="w-4 h-4" />
        )}
        {loading ? 'Starting...' : 'Run crawl now'}
      </button>
      {conflictNotice && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-1 rounded">
          A crawl job is already queued or running.
        </p>
      )}
    </div>
  );
}
