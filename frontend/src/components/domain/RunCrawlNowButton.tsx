import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Play } from 'lucide-react';
import { apiService } from '../../services/api';
import type { CrawlJob } from '../../types/crawl';
import { ButtonApp } from '../ui/ButtonApp';

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
  const { t } = useTranslation('common');
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
      <ButtonApp
        label={loading ? t('domainDetailPage.runCrawl.starting') : t('domainDetailPage.runCrawl.runNow')}
        onClick={() => { void handleClick(); }}
        disabled={disabled}
        loading={loading}
        icon={<Play className="w-4 h-4" />}
      />
      {conflictNotice && (
        <p className="text-xs text-bronze dark:text-bronze-dark bg-bronze-bg dark:bg-bronze-bg-dark border border-bronze-border dark:border-bronze-border-dark px-3 py-2 rounded-lg">
          {t('domainDetailPage.runCrawl.alreadyActive')}
        </p>
      )}
    </div>
  );
}
