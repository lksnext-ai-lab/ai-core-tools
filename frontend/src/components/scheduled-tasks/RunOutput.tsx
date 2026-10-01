import { AlertTriangle } from 'lucide-react';
import MessageContent from '../playground/MessageContent';
import type { ScheduledTaskRun } from '../../services/api';
import { RunStatusBadge } from './RunStatusBadge';
import { formatDateTime, runDuration } from './format';

interface Props {
  run: ScheduledTaskRun;
  resolveFileUrl: (runId: number, fileId: string) => Promise<string>;
}

/** Read-only answer of one run: the agent's text (with inline images/files) or its error. */
export function RunOutput({ run, resolveFileUrl }: Readonly<Props>) {
  const duration = runDuration(run);
  return (
    <article className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
      <header className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <time dateTime={run.scheduled_time} className="font-medium text-gray-900 dark:text-gray-100">
          {formatDateTime(run.scheduled_time)}
        </time>
        <RunStatusBadge status={run.status} />
        {duration && <span className="text-xs text-gray-500 dark:text-gray-400">Duración {duration}</span>}
      </header>
      {run.status === 'failed' && (
        <div role="alert" className="mb-3 flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
          <span className="min-w-0 whitespace-pre-wrap break-words">{run.error_summary || 'La ejecución falló.'}</span>
        </div>
      )}
      {run.output_text ? (
        <MessageContent content={run.output_text} resolveFileUrl={(fileId) => resolveFileUrl(run.id, fileId)} />
      ) : (
        run.status !== 'failed' && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {run.status === 'succeeded' ? 'El agente no devolvió texto.' : 'La ejecución todavía no ha terminado.'}
          </p>
        )
      )}
    </article>
  );
}
