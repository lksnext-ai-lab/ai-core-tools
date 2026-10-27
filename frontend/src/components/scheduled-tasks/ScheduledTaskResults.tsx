import { ChevronDown, MessagesSquare, Paperclip } from 'lucide-react';
import type { ScheduledTaskRun } from '../../services/api';
import { RunStatusBadge } from './RunStatusBadge';
import { formatDateTime, outputPreview } from './format';
import { RunOutput } from './RunOutput';
import { RunFiles } from './RunFiles';
import Badge from '../ui/Badge';

interface Props {
  conversationMode: string;
  runs: ScheduledTaskRun[] | null;
  maxRunsRetained?: number;
  resolveFileUrl: (runId: number, fileId: string) => Promise<string>;
}

const accordionClass =
  'group overflow-hidden rounded-md border border-line bg-surface dark:border-line-dark dark:bg-surface-dark';
const accordionSummaryClass =
  'flex min-w-0 cursor-pointer list-none items-center gap-3 p-3 text-sm transition-colors hover:bg-surface-tint dark:hover:bg-surface-tint-dark [&::-webkit-details-marker]:hidden';

/**
 * Results of a scheduled task: one entry per run, or a single entry for a
 * continuous conversation (its detail lists every answer).
 */
export function ScheduledTaskResults({ conversationMode, runs, maxRunsRetained, resolveFileUrl }: Readonly<Props>) {
  const continuous = conversationMode === 'continuous';
  return (
    <div>
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
      {runs !== null && runs.length > 0 && continuous && (
        <ContinuousEntry runs={runs} resolveFileUrl={resolveFileUrl} />
      )}
      {runs !== null && runs.length > 0 && !continuous && (
        <ul className="space-y-2">
          {runs.map((run) => (
            <li key={run.id}>
              <RunAccordion run={run} resolveFileUrl={resolveFileUrl} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RunAccordion({
  run,
  resolveFileUrl,
}: Readonly<{ run: ScheduledTaskRun; resolveFileUrl: Props['resolveFileUrl'] }>) {
  return (
    <details className={accordionClass}>
      <summary className={accordionSummaryClass}>
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
        <ChevronDown className="h-4 w-4 flex-shrink-0 text-fg-tertiary transition-transform group-open:rotate-180 dark:text-fg-tertiary-dark" aria-hidden="true" />
      </summary>
      <div className="space-y-3 border-t border-line p-3 dark:border-line-dark">
        <RunOutput run={run} resolveFileUrl={resolveFileUrl} />
        <RunFiles runs={[run]} resolveFileUrl={resolveFileUrl} />
      </div>
    </details>
  );
}

function ContinuousEntry({
  runs,
  resolveFileUrl,
}: Readonly<{ runs: ScheduledTaskRun[]; resolveFileUrl: Props['resolveFileUrl'] }>) {
  const latest = runs[0];
  const files = runs.reduce((count, run) => count + (run.output_files?.length ?? 0), 0);
  const failed = runs.filter((run) => run.status === 'failed').length;
  return (
    <details className={accordionClass}>
      <summary className={accordionSummaryClass}>
        <MessagesSquare className="h-5 w-5 flex-shrink-0 text-bronze dark:text-bronze dark:text-bronze-dark" aria-hidden="true" />
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
        <ChevronDown className="h-4 w-4 flex-shrink-0 text-fg-tertiary transition-transform group-open:rotate-180 dark:text-fg-tertiary-dark" aria-hidden="true" />
      </summary>
      <div className="space-y-3 border-t border-line p-3 dark:border-line-dark">
        {runs.map((run) => <RunOutput key={run.id} run={run} resolveFileUrl={resolveFileUrl} />)}
        <RunFiles runs={runs} resolveFileUrl={resolveFileUrl} showRunDate />
      </div>
    </details>
  );
}

function FileCount({ count }: Readonly<{ count: number }>) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
      <Paperclip className="h-3 w-3" aria-hidden="true" />
      {count} archivo{count === 1 ? '' : 's'}
    </span>
  );
}
