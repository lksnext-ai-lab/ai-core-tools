import { CalendarClock } from 'lucide-react';
import type { MarketplaceScheduledTask } from '../../services/api';
import { ButtonCard } from '../ui/ButtonCard';
import { RunStatusBadge } from '../scheduled-tasks/RunStatusBadge';
import { describeSchedule, formatDateTime } from '../scheduled-tasks/format';

interface Props {
  readonly task: MarketplaceScheduledTask;
  readonly onClick: (taskId: number) => void;
}

/** Card for a published scheduled task in the marketplace catalog. */
export function MarketplaceScheduledTaskCard({ task, onClick }: Props) {
  return (
    <ButtonCard
      onClick={() => onClick(task.id)}
      ariaLabel={`Open scheduled task ${task.name}`}
    >


      <div className="mb-3 flex min-w-0 items-center gap-3">
        <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center overflow-hidden rounded-md border-[0.8px] border-[#FF682C] text-sm font-medium">
          <CalendarClock className="w-5 h-5 text-fg dark:text-fg-dark" aria-hidden="true" />
        </div>
        <div className="min-w-0 text-[18px] leading-tight">
          <span className="block text-ink dark:text-ink-dark">{task.name}</span>
          <span className="block text-[12.5px] text-fg-secondary dark:text-fg-secondary-dark">{task.app_name}</span>
        </div>
      </div>
      <p className="mb-4 whitespace-pre-line text-[13.5px] leading-[1.45] text-fg-secondary dark:text-fg-secondary-dark">
        {task.description || 'Sin descripción.'}
      </p>
      <div className="space-y-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
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
    </ButtonCard>
  );
}
