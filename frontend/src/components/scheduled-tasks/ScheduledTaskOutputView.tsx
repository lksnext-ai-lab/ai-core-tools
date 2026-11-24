import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import Alert from '../ui/Alert';
import type { ScheduledTaskRun } from '../../services/api';
import { RunFiles } from './RunFiles';
import { RunOutput } from './RunOutput';
import { CardApp } from '../ui/CardApp';

export interface ScheduledTaskOutputSource {
  /** Loads the runs to show: one run, or every run of a continuous conversation (newest first). */
  load: () => Promise<ScheduledTaskRun[]>;
  resolveFileUrl: (runId: number, fileId: string) => Promise<string>;
}

interface Props {
  title: string;
  subtitle?: string;
  backHref: string;
  backLabel: string;
  source: ScheduledTaskOutputSource;
  /** Continuous conversation: list every answer and gather their files. */
  timeline?: boolean;
}

/** Read-only output of a scheduled task run (or conversation). Shared by the app and the marketplace. */
export function ScheduledTaskOutputView({ title, subtitle, backHref, backLabel, source, timeline = false }: Readonly<Props>) {
  const { t } = useTranslation('common');
  const [runs, setRuns] = useState<ScheduledTaskRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRuns(null);
    setError(null);
    source.load()
      .then((items) => { if (!cancelled) setRuns(items); })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : t('scheduledTaskDetailPage.results.outputLoadFailed')); });
    return () => { cancelled = true; };
  }, [source, t]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="min-w-0">
        <Link to={backHref} className="mb-3 items-center gap-2 text-sm text-bronze  dark:text-bronze-dark inline-block">
          <ArrowLeft className="w-4 h-4 inline-block ml-1" aria-hidden="true" />
          {backLabel}
        </Link>
        <h1 className="break-words text-2xl font-bold text-fg dark:text-fg-dark">{title}</h1>
        {subtitle && <p className="text-secondary  dark:text-secondary-dark">{subtitle}</p>}
      </div>

      {error && <Alert type="error" message={error} />}
      {!error && runs === null && (
        <CardApp className=" p-8 text-center text-secondary  dark:text-secondary-dark ">{t('scheduledTaskDetailPage.results.outputLoading')}</CardApp>
      )}
      {runs !== null && runs.length === 0 && (
        <CardApp className="p-8 text-center text-secondary  dark:text-secondary-dark">{t('scheduledTaskDetailPage.results.outputEmpty')}</CardApp>
      )}
      {runs !== null && runs.length > 0 && (
        <>
          <div className="space-y-4">
            {runs.map((run) => <RunOutput key={run.id} run={run} resolveFileUrl={source.resolveFileUrl} />)}
          </div>
          <RunFiles runs={runs} resolveFileUrl={source.resolveFileUrl} showRunDate={timeline} />
        </>
      )}
    </div>
  );
}
