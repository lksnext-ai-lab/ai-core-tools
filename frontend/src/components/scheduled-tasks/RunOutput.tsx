import Alert from '../ui/Alert';
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
    <article className="rounded-md border border-line bg-surface-tint p-4 dark:border-line-dark dark:bg-surface-tint-dark">
      <header className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <time dateTime={run.scheduled_time} className="font-medium text-fg dark:text-fg-dark">
          {formatDateTime(run.scheduled_time)}
        </time>
        <RunStatusBadge status={run.status} />
        {duration && <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">Duración {duration}</span>}
      </header>
      {run.status === 'failed' && (
        <Alert
          type="error"
          className="mb-3"
          message={<span className="whitespace-pre-wrap break-words">{run.error_summary || 'La ejecución falló.'}</span>}
        />
      )}
      {run.output_text ? (
        <MessageContent content={run.output_text} resolveFileUrl={(fileId) => resolveFileUrl(run.id, fileId)} />
      ) : (
        run.status !== 'failed' && (
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
            {run.status === 'succeeded' ? 'El agente no devolvió texto.' : 'La ejecución todavía no ha terminado.'}
          </p>
        )
      )}
    </article>
  );
}
