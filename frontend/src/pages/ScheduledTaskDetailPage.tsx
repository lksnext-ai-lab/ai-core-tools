import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { CalendarClock, Pencil, PlayCircle } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { apiService, type Agent, type ScheduledTask, type ScheduledTaskRun } from '../services/api';
import { ScheduledTaskResults } from '../components/scheduled-tasks/ScheduledTaskResults';
import { conversationModeLabel, describeSchedule, formatDateTime } from '../components/scheduled-tasks/format';
import Title from '../components/ui/Title';
import ButtonApp from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import CardApp from '../components/ui/CardApp';
import Badge from '../components/ui/Badge';

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
      <dt className="text-xs font-medium uppercase text-fg-secondary dark:text-fg-secondary-dark">{label}</dt>
      <dd className="mt-1 text-fg dark:text-fg-dark">{children}</dd>
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
    <div className="max-w-4xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <Title variant="titSecundario" titulo={task.name} subtitulo={task.description || 'Detalle de la tarea programada'} />
        <div className="flex gap-2">
          {task.status === 'active' && (
            <ButtonApp
              label="Ejecutar ahora"
              type="button"
              variant="secondary"
              size="medium"
              onClick={() => { void runNow(); }}
              loading={running}
              icon={<PlayCircle className="h-4 w-4" aria-hidden="true" />}
            />
          )}
          <ButtonLink
            label="Editar"
            to={`${base}/edit`}
            variant="primary"
            size="medium"
            icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
          />
        </div>
      </div>
      <CardApp>
        <dl className="grid gap-4 p-6 sm:grid-cols-2 ">
          <Field label="Agente">{agent?.name ?? `Agente #${task.agent_id}`}</Field>
          <Field label="Estado">
            <Badge
              label={task.status === 'active' ? 'Activa' : 'Pausada'}
              variant={task.status === 'active' ? 'success' : 'default'}
            />
          </Field>
          <Field label="Programación">
            <span className="inline-flex items-center gap-2"><CalendarClock className="h-4 w-4 text-fg dark:text-fg-dark" aria-hidden="true" />{describeSchedule(task.cron_expression)}</span>
          </Field>
          <Field label="Próxima ejecución">{formatDateTime(task.next_run_at)} <span className="text-xs text-gray-500">({task.timezone})</span></Field>
          <Field label="Modo de conversación">{conversationModeLabel(task.conversation_mode)}</Field>
          <Field label="Visibilidad">{VISIBILITY_LABELS[task.marketplace_visibility] ?? task.marketplace_visibility}</Field>
          <Field label="Input de la tarea" wide>
            <span className="block whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-3 text-sm text-gray-700 dark:bg-gray-900 dark:text-gray-300">{formatInput(task.input)}</span>
          </Field>
        </dl>
      </CardApp>
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
