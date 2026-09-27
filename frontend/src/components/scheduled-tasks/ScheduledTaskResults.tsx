import { ChevronRight, MessagesSquare, Paperclip } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ScheduledTaskRun } from '../../services/api';
import { RunStatusBadge } from './RunStatusBadge';
import { formatDateTime, outputPreview } from './format';

interface Props {
  conversationMode: string;
  runs: ScheduledTaskRun[] | null;
  maxRunsRetained?: number;
  /** Detail of one run (one conversation per run). */
  runHref: (run: ScheduledTaskRun) => string;
  /** Timeline of every run of a continuous conversation. */
  conversationHref: string;
}

const entryClass =
  'flex min-w-0 items-center gap-3 rounded-lg border border-gray-200 p-3 text-sm hover:border-blue-300 hover:bg-blue-50/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-gray-700 dark:hover:border-blue-700 dark:hover:bg-blue-900/10';

/**
 * Results of a scheduled task: one entry per run, or a single entry for a
 * continuous conversation (its detail lists every answer).
 */
export function ScheduledTaskResults({ conversationMode, runs, maxRunsRetained, runHref, conversationHref }: Readonly<Props>) {
  const continuous = conversationMode === 'continuous';
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {continuous ? 'Conversación' : 'Ejecuciones'}
        </h2>
        {maxRunsRetained !== undefined && (
          <span className="text-xs text-gray-500 dark:text-gray-400">Se conservan las últimas {maxRunsRetained} ejecuciones</span>
        )}
      </div>
      {runs === null && <p className="text-sm text-gray-500 dark:text-gray-400">Cargando ejecuciones…</p>}
      {runs !== null && runs.length === 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">No hay ejecuciones todavía.</p>
      )}
      {runs !== null && runs.length > 0 && continuous && <ContinuousEntry runs={runs} href={conversationHref} />}
      {runs !== null && runs.length > 0 && !continuous && (
        <ul className="space-y-2">
          {runs.map((run) => (
            <li key={run.id}>
              <Link to={runHref(run)} className={entryClass}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-gray-900 dark:text-gray-100">{formatDateTime(run.scheduled_time)}</span>
                    <RunStatusBadge status={run.status} />
                    {run.output_files?.length > 0 && <FileCount count={run.output_files.length} />}
                  </div>
                  <p className="mt-1 truncate text-gray-600 dark:text-gray-400">
                    {run.status === 'failed' ? run.error_summary : outputPreview(run.output_text)}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 flex-shrink-0 text-gray-400" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ContinuousEntry({ runs, href }: Readonly<{ runs: ScheduledTaskRun[]; href: string }>) {
  const latest = runs[0];
  const files = runs.reduce((count, run) => count + (run.output_files?.length ?? 0), 0);
  const failed = runs.filter((run) => run.status === 'failed').length;
  return (
    <Link to={href} className={entryClass}>
      <MessagesSquare className="h-5 w-5 flex-shrink-0 text-blue-600" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-gray-900 dark:text-gray-100">
            {runs.length} respuesta{runs.length === 1 ? '' : 's'}
          </span>
          <span className="text-gray-500 dark:text-gray-400">· última {formatDateTime(latest.scheduled_time)}</span>
          {failed > 0 && (
            <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-900/40 dark:text-red-300">
              {failed} fallida{failed === 1 ? '' : 's'}
            </span>
          )}
          {files > 0 && <FileCount count={files} />}
        </div>
        <p className="mt-1 truncate text-gray-600 dark:text-gray-400">
          {latest.status === 'failed' ? latest.error_summary : outputPreview(latest.output_text)}
        </p>
      </div>
      <ChevronRight className="h-4 w-4 flex-shrink-0 text-gray-400" aria-hidden="true" />
    </Link>
  );
}

function FileCount({ count }: Readonly<{ count: number }>) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
      <Paperclip className="h-3 w-3" aria-hidden="true" />
      {count} archivo{count === 1 ? '' : 's'}
    </span>
  );
}
