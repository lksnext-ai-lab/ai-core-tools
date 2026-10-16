import { ChevronRight, MessagesSquare, Paperclip } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ScheduledTaskRun } from '../../services/api';
import { RunStatusBadge } from './RunStatusBadge';
import { formatDateTime, outputPreview } from './format';
import CardApp from '../ui/CardApp';
import Badge from '../ui/Badge';

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
  'flex min-w-0 items-center gap-3 rounded-lg border border-line dark:border-line-dark p-3 text-sm hover:bg-surface-tint dark:hover:bg-surface-tint-dark ';

/**
 * Results of a scheduled task: one entry per run, or a single entry for a
 * continuous conversation (its detail lists every answer).
 */
export function ScheduledTaskResults({ conversationMode, runs, maxRunsRetained, runHref, conversationHref }: Readonly<Props>) {
  const continuous = conversationMode === 'continuous';
  return (
    <CardApp>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold text-fg dark:text-fg-dark">
          {continuous ? 'Conversación' : 'Ejecuciones'}
        </h3>
        {maxRunsRetained !== undefined && (
          <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">Se conservan las últimas {maxRunsRetained} ejecuciones</span>
        )}
      </div>
      {runs === null && <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Cargando ejecuciones…</p>}
      {runs !== null && runs.length === 0 && (
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">No hay ejecuciones todavía.</p>
      )}
      {runs !== null && runs.length > 0 && continuous && <ContinuousEntry runs={runs} href={conversationHref} />}
      {runs !== null && runs.length > 0 && !continuous && (
        <ul className="space-y-2">
          {runs.map((run) => (
            <li key={run.id}>
              <Link to={runHref(run)} className={entryClass}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-fg dark:text-fg-dark">{formatDateTime(run.scheduled_time)}</span>
                    <RunStatusBadge status={run.status} />
                    {run.output_files?.length > 0 && <FileCount count={run.output_files.length} />}
                  </div>
                  <p className="mt-1 truncate text-fg-secondary dark:text-fg-secondary-dark">
                    {run.status === 'failed' ? run.error_summary : outputPreview(run.output_text)}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 flex-shrink-0 text-gray-400" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </CardApp>
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
          <span className="font-medium text-fg dark:text-fg-dark">
            {runs.length} respuesta{runs.length === 1 ? '' : 's'}
          </span>
          <span className="text-fg-secondary dark:text-fg-secondary-dark">· última {formatDateTime(latest.scheduled_time)}</span>
          {failed > 0 && (
            <Badge
              label={`${failed} fallida${failed === 1 ? '' : 's'}`}
              variant="error"
            />
          )}
          {files > 0 && <FileCount count={files} />}
        </div>
        <p className="mt-1 truncate text-fg-secondary dark:text-fg-secondary-dark">
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
