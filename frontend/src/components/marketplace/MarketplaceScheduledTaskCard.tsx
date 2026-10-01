import { CalendarClock } from 'lucide-react';
import type { MarketplaceScheduledTask } from '../../services/api';
import { RunStatusBadge } from '../scheduled-tasks/RunStatusBadge';
import { describeSchedule, formatDateTime } from '../scheduled-tasks/format';

interface Props {
  readonly task: MarketplaceScheduledTask;
  readonly onClick: (taskId: number) => void;
}

/** Card for a published scheduled task in the marketplace catalog. */
export function MarketplaceScheduledTaskCard({ task, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={() => onClick(task.id)}
      className="flex h-full w-full flex-col rounded-lg border bg-white p-5 text-left shadow-md transition-all duration-200 hover:border-blue-300 hover:shadow-lg dark:border-gray-700 dark:bg-gray-800"
    >
      <div className="mb-3 flex items-start gap-3">
        <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/30">
          <CalendarClock className="h-5 w-5 text-blue-500" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">{task.name}</h3>
          <p className="truncate text-xs text-gray-500 dark:text-gray-400">{task.app_name}</p>
        </div>
      </div>
      <p className="mb-4 line-clamp-3 flex-1 text-sm text-gray-600 dark:text-gray-300">
        {task.description || 'Sin descripción.'}
      </p>
      <div className="space-y-1 text-xs text-gray-500 dark:text-gray-400">
        <div>{describeSchedule(task.cron_expression)} · {task.timezone}</div>
        <div className="flex flex-wrap items-center gap-2">
          {task.last_run_at ? (
            <>
              <span>Última: {formatDateTime(task.last_run_at)}</span>
              <RunStatusBadge status={task.last_run_status} />
            </>
          ) : (
            <span>Sin ejecuciones todavía</span>
          )}
        </div>
      </div>
    </button>
  );
}
