import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { ArrowLeft, CalendarClock, LoaderCircle, Pencil, PlayCircle } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { apiService, type Agent, type ScheduledTask, type ScheduledTaskRun } from '../services/api';
import { ScheduledTaskResults } from '../components/scheduled-tasks/ScheduledTaskResults';
import { conversationModeLabel, describeSchedule, formatDateTime } from '../components/scheduled-tasks/format';

const VISIBILITY_LABELS: Record<string, string> = {
  unpublished: 'No publicada',
  private: 'Marketplace · miembros de la app',
  public: 'Marketplace · público',
};

function formatInput(input: Record<string, unknown>): string {
  return input.message ? String(input.message) : JSON.stringify(input, null, 2);
}

function Field({ label, children, wide = false }: Readonly<{ label: string; children: ReactNode; wide?: boolean }>) {
  return (
    <div className={wide ? 'sm:col-span-2' : undefined}>
      <dt className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="mt-1 text-gray-900 dark:text-gray-100">{children}</dd>
    </div>
  );
}

export default function ScheduledTaskDetailPage() {
  const { appId, taskId } = useParams();
  const numericAppId = Number.parseInt(appId ?? '0', 10);
  const numericTaskId = Number.parseInt(taskId ?? '0', 10);
  const [task, setTask] = useState<ScheduledTask | null>(null);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [runs, setRuns] = useState<ScheduledTaskRun[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const loadRuns = useCallback(() => apiService.getScheduledTaskRuns(numericAppId, numericTaskId)
    .then((result) => setRuns(result.items))
    .catch(() => setRuns([])), [numericAppId, numericTaskId]);

  useEffect(() => {
    setLoading(true);
    apiService.getScheduledTask(numericAppId, numericTaskId)
      .then((found) => {
        setTask(found);
        void loadRuns();
        apiService.getAgents(numericAppId)
          .then((agents) => setAgent(agents.find((item) => item.agent_id === found.agent_id) ?? null))
          .catch(() => undefined);
      })
      .catch((error) => toast.error(error instanceof Error ? error.message : 'No se pudo cargar el detalle de la tarea'))
      .finally(() => setLoading(false));
  }, [numericAppId, numericTaskId, loadRuns]);

  const runNow = async () => {
    if (!task) return;
    setRunning(true);
    try {
      await apiService.runScheduledTaskNow(numericAppId, task.id);
      toast.success('Ejecución puesta en cola. Aparecerá en el historial al terminar.');
      setTimeout(() => { void loadRuns(); }, 3000);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'No se pudo ejecutar la tarea');
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <div className="rounded-xl bg-white p-8 text-center text-gray-500 dark:bg-gray-800">Cargando tarea…</div>;
  if (!task) return <div className="rounded-xl bg-white p-8 text-center text-gray-600 dark:bg-gray-800">No se encontró la tarea programada.</div>;

  const base = `/apps/${appId}/scheduled-tasks/${task.id}`;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link className="mb-3 inline-flex items-center gap-2 text-sm text-gray-500 hover:text-blue-600" to={`/apps/${appId}/scheduled-tasks`}>
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />Volver a tareas
          </Link>
          <h1 className="break-words text-2xl font-bold text-gray-900 dark:text-gray-100">{task.name}</h1>
          <p className="text-gray-600 dark:text-gray-400">{task.description || 'Detalle de la tarea programada'}</p>
        </div>
        <div className="flex gap-2">
          {task.status === 'active' && (
            <button type="button" disabled={running} onClick={() => { void runNow(); }}
              className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-blue-600 hover:bg-blue-50 disabled:opacity-50 dark:border-gray-600">
              {running ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : <PlayCircle className="h-4 w-4" aria-hidden="true" />}
              Ejecutar ahora
            </button>
          )}
          <Link to={`${base}/edit`} className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-blue-600 hover:bg-blue-50 dark:border-gray-600">
            <Pencil className="h-4 w-4" aria-hidden="true" />Editar
          </Link>
        </div>
      </div>
      <dl className="grid gap-4 rounded-xl border border-gray-200 bg-white p-6 sm:grid-cols-2 dark:border-gray-700 dark:bg-gray-800">
        <Field label="Agente">{agent?.name ?? `Agente #${task.agent_id}`}</Field>
        <Field label="Estado">
          <span className={`rounded-full px-2 py-1 text-xs font-medium ${task.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700'}`}>
            {task.status === 'active' ? 'Activa' : 'Pausada'}
          </span>
        </Field>
        <Field label="Programación">
          <span className="inline-flex items-center gap-2"><CalendarClock className="h-4 w-4 text-blue-600" aria-hidden="true" />{describeSchedule(task.cron_expression)}</span>
        </Field>
        <Field label="Próxima ejecución">{formatDateTime(task.next_run_at)} <span className="text-xs text-gray-500">({task.timezone})</span></Field>
        <Field label="Modo de conversación">{conversationModeLabel(task.conversation_mode)}</Field>
        <Field label="Visibilidad">{VISIBILITY_LABELS[task.marketplace_visibility] ?? task.marketplace_visibility}</Field>
        <Field label="Input de la tarea" wide>
          <span className="block whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-3 text-sm text-gray-700 dark:bg-gray-900 dark:text-gray-300">{formatInput(task.input)}</span>
        </Field>
      </dl>
      <ScheduledTaskResults
        conversationMode={task.conversation_mode}
        runs={runs}
        maxRunsRetained={task.max_runs_retained}
        runHref={(run) => `${base}/runs/${run.id}`}
        conversationHref={`${base}/conversation`}
      />
    </div>
  );
}
