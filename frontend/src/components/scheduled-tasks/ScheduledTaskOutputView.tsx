import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ScheduledTaskRun } from '../../services/api';
import { RunFiles } from './RunFiles';
import { RunOutput } from './RunOutput';

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
  const [runs, setRuns] = useState<ScheduledTaskRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRuns(null);
    setError(null);
    source.load()
      .then((items) => { if (!cancelled) setRuns(items); })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : 'No se pudo cargar el resultado'); });
    return () => { cancelled = true; };
  }, [source]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="min-w-0">
        <Link to={backHref} className="mb-3 inline-flex items-center gap-2 text-sm text-gray-500 hover:text-blue-600 dark:text-gray-400">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          {backLabel}
        </Link>
        <h1 className="break-words text-2xl font-bold text-gray-900 dark:text-gray-100">{title}</h1>
        {subtitle && <p className="text-gray-600 dark:text-gray-400">{subtitle}</p>}
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}
      {!error && runs === null && (
        <div className="rounded-xl bg-white p-8 text-center text-gray-500 dark:bg-gray-800 dark:text-gray-400">Cargando…</div>
      )}
      {runs !== null && runs.length === 0 && (
        <div className="rounded-xl bg-white p-8 text-center text-gray-500 dark:bg-gray-800 dark:text-gray-400">No hay respuestas todavía.</div>
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
