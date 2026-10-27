import { useEffect, useState } from 'react';
import { ArrowLeft, CalendarClock } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { apiService, type MarketplaceScheduledTask, type ScheduledTaskRun } from '../services/api';
import { ScheduledTaskResults } from '../components/scheduled-tasks/ScheduledTaskResults';
import { conversationModeLabel, describeSchedule, formatDateTime } from '../components/scheduled-tasks/format';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import BackgroundImage from '../components/ui/BackgroundImage';
import CardApp from '../components/ui/CardApp';

interface MarketplaceScheduledTaskPageProps {
  /** Task to show. Defaults to the `:taskId` route param. */
  readonly taskId?: number;
  /** `panel` renders a compact single-column layout for the marketplace side panel. */
  readonly variant?: 'page' | 'panel';
}

/** Marketplace detail of a published scheduled task: what it is and its results (never its input). */
export default function MarketplaceScheduledTaskPage({
  taskId: taskIdProp,
  variant = 'page',
}: MarketplaceScheduledTaskPageProps = {}) {
  const { taskId } = useParams();
  const numericTaskId = taskIdProp ?? Number.parseInt(taskId ?? '0', 10);
  const isPanel = variant === 'panel';
  const [task, setTask] = useState<MarketplaceScheduledTask | null>(null);
  const [runs, setRuns] = useState<ScheduledTaskRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiService.getMarketplaceScheduledTask(numericTaskId)
      .then((found) => {
        setTask(found);
        apiService.getMarketplaceScheduledTaskRuns(numericTaskId).then((r) => setRuns(r.items)).catch(() => setRuns([]));
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Scheduled task not found'));
  }, [numericTaskId]);

  if (isPanel) {
    if (error) return <ErrorState error={error} />;
    if (!task) return <LoadingState message="Cargando tarea…" />;
    return <MarketplaceScheduledTaskPanelView task={task} runs={runs} />;
  }

  const back = (
    <Link to="/marketplace?tab=tasks" className="mb-3 inline-flex items-center gap-2 text-sm text-fg-secondary hover:text-accent dark:text-fg-secondary-dark dark:hover:text-accent-dark">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />Volver al marketplace
    </Link>
  );
  if (error) return <div className="mx-auto max-w-4xl">{back}<div role="alert" className="rounded-xl border border-line bg-surface p-8 text-center text-fg-secondary dark:border-line-dark dark:bg-surface-dark dark:text-fg-secondary-dark">{error}</div></div>;
  if (!task) return <div className="rounded-xl border border-line bg-surface p-8 text-center text-fg-secondary dark:border-line-dark dark:bg-surface-dark dark:text-fg-secondary-dark">Cargando tarea…</div>;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="min-w-0">
        {back}
        <h1 className="break-words font-display text-[28px] leading-tight text-fg dark:text-fg-dark">{task.name}</h1>
        <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{task.app_name}</p>
        {task.description && <p className="mt-2 whitespace-pre-wrap text-fg-secondary dark:text-fg-secondary-dark">{task.description}</p>}
      </div>
      <dl className="grid gap-4 rounded-xl border border-line bg-surface p-6 text-sm sm:grid-cols-3 dark:border-line-dark dark:bg-surface-dark">
        <div>
          <dt className="text-[11px] uppercase tracking-[0.06em] text-fg-tertiary dark:text-fg-tertiary-dark">Programación</dt>
          <dd className="mt-1 inline-flex items-center gap-2 text-fg dark:text-fg-dark"><CalendarClock className="h-4 w-4 text-accent dark:text-accent-dark" aria-hidden="true" />{describeSchedule(task.cron_expression)}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.06em] text-fg-tertiary dark:text-fg-tertiary-dark">Próxima ejecución</dt>
          <dd className="mt-1 text-fg dark:text-fg-dark">{task.status === 'active' ? formatDateTime(task.next_run_at) : 'Pausada'}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.06em] text-fg-tertiary dark:text-fg-tertiary-dark">Modo</dt>
          <dd className="mt-1 text-fg dark:text-fg-dark">{conversationModeLabel(task.conversation_mode)}</dd>
        </div>
      </dl>
      <ScheduledTaskResults
        conversationMode={task.conversation_mode}
        runs={runs}
        resolveFileUrl={(runId, fileId) => apiService.getMarketplaceScheduledTaskRunFileUrl(task.id, runId, fileId)}
      />
    </div>
  );
}

const PANEL_CARD =
  'rounded-xl border border-line dark:border-line-dark bg-surface dark:bg-surface-dark p-6';
const PANEL_CARD_TITLE =
  'font-display text-[17px] font-medium text-fg dark:text-fg-dark mb-3';
const PANEL_DT = 'text-fg-tertiary dark:text-fg-tertiary-dark';
const PANEL_DD = 'font-medium text-right text-fg dark:text-fg-dark';

interface MarketplaceScheduledTaskPanelViewProps {
  readonly task: MarketplaceScheduledTask;
  readonly runs: ScheduledTaskRun[] | null;
}

/** Compact single-column scheduled task view shown in the marketplace side panel. */
function MarketplaceScheduledTaskPanelView({ task, runs }: MarketplaceScheduledTaskPanelViewProps) {
  return (
    <div className="space-y-5 px-4 py-4">
      {/* Header */}
      <div className="flex items-start gap-4">
        <BackgroundImage icon={CalendarClock} alt={task.name} size={70} variant="vacio" />
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-[28px] leading-tight text-fg dark:text-fg-dark break-words">
            {task.name}
          </h3>
          <p className="text-[16px] text-fg-tertiary dark:text-fg-tertiary-dark">by {task.app_name}</p>
        </div>
      </div>

      {/* About */}
      <CardApp className={PANEL_CARD}>
        <h4 className={PANEL_CARD_TITLE}>Descripción</h4>
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-fg-secondary dark:text-fg-secondary-dark">
          {task.description || 'Sin descripción.'}
        </p>
      </CardApp>

      {/* Details */}
      <CardApp className={PANEL_CARD}>
        <h4 className={PANEL_CARD_TITLE}>Detalles</h4>
        <dl className="space-y-3 text-[15px]">
          <div className="flex justify-between gap-4">
            <dt className={PANEL_DT}>Programación</dt>
            <dd className={PANEL_DD}>{describeSchedule(task.cron_expression)} · {task.timezone}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className={PANEL_DT}>Próxima ejecución</dt>
            <dd className={PANEL_DD}>{task.status === 'active' ? formatDateTime(task.next_run_at) : 'Pausada'}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className={PANEL_DT}>Modo</dt>
            <dd className={PANEL_DD}>{conversationModeLabel(task.conversation_mode)}</dd>
          </div>
        </dl>
      </CardApp>

      {/* Results */}
      <ScheduledTaskResults
        conversationMode={task.conversation_mode}
        runs={runs}
        resolveFileUrl={(runId, fileId) => apiService.getMarketplaceScheduledTaskRunFileUrl(task.id, runId, fileId)}
      />
    </div>
  );
}
