import { useEffect, useState } from 'react';
import { ArrowLeft, CalendarClock } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { apiService, type MarketplaceScheduledTask, type ScheduledTaskRun } from '../services/api';
import { ScheduledTaskResults } from '../components/scheduled-tasks/ScheduledTaskResults';
import { conversationModeLabel, describeSchedule, formatDateTime } from '../components/scheduled-tasks/format';

/** Marketplace detail of a published scheduled task: what it is and its results (never its input). */
export default function MarketplaceScheduledTaskPage() {
  const { taskId } = useParams();
  const numericTaskId = Number.parseInt(taskId ?? '0', 10);
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

  const back = (
    <Link to="/marketplace?tab=tasks" className="mb-3 inline-flex items-center gap-2 text-sm text-gray-500 hover:text-blue-600 dark:text-gray-400">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />Volver al marketplace
    </Link>
  );
  if (error) return <div className="mx-auto max-w-4xl">{back}<div role="alert" className="rounded-xl bg-white p-8 text-center text-gray-600 dark:bg-gray-800">{error}</div></div>;
  if (!task) return <div className="rounded-xl bg-white p-8 text-center text-gray-500 dark:bg-gray-800">Cargando tarea…</div>;

  const base = `/marketplace/scheduled-tasks/${task.id}`;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="min-w-0">
        {back}
        <h1 className="break-words text-2xl font-bold text-gray-900 dark:text-gray-100">{task.name}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">{task.app_name}</p>
        {task.description && <p className="mt-2 whitespace-pre-wrap text-gray-700 dark:text-gray-300">{task.description}</p>}
      </div>
      <dl className="grid gap-4 rounded-xl border border-gray-200 bg-white p-6 text-sm sm:grid-cols-3 dark:border-gray-700 dark:bg-gray-800">
        <div>
          <dt className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Programación</dt>
          <dd className="mt-1 inline-flex items-center gap-2 text-gray-900 dark:text-gray-100"><CalendarClock className="h-4 w-4 text-blue-600" aria-hidden="true" />{describeSchedule(task.cron_expression)}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Próxima ejecución</dt>
          <dd className="mt-1 text-gray-900 dark:text-gray-100">{task.status === 'active' ? formatDateTime(task.next_run_at) : 'Pausada'}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Modo</dt>
          <dd className="mt-1 text-gray-900 dark:text-gray-100">{conversationModeLabel(task.conversation_mode)}</dd>
        </div>
      </dl>
      <ScheduledTaskResults
        conversationMode={task.conversation_mode}
        runs={runs}
        runHref={(run) => `${base}/runs/${run.id}`}
        conversationHref={`${base}/conversation`}
      />
    </div>
  );
}
