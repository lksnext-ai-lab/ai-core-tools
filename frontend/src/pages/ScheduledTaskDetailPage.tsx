import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { AlertTriangle, ArrowRight, CalendarClock, Pencil, PlayCircle } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { apiService, type Agent, type ScheduledTask, type ScheduledTaskRun } from '../services/api';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';
import { ScheduledTaskResults } from '../components/scheduled-tasks/ScheduledTaskResults';
import { conversationModeLabel, describeSchedule, formatDateTime } from '../components/scheduled-tasks/format';
import Title from '../components/ui/Title';
import ButtonApp from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import CardApp from '../components/ui/CardApp';
import Badge from '../components/ui/Badge';
import { SegmentedTabs } from '../components/ui/SegmentedTabs';

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

type PanelTab = 'info' | 'runs';

const PANEL_TABS: { id: PanelTab; label: string }[] = [
  { id: 'info', label: 'Información' },
  { id: 'runs', label: 'Ejecuciones' },
];

const PANEL_CARD_TITLE = 'font-display text-[17px] font-medium text-fg dark:text-fg-dark mb-3';
const PANEL_DT = 'text-sm text-fg-tertiary dark:text-fg-tertiary-dark';
const PANEL_DD = 'text-sm font-medium text-fg dark:text-fg-dark';
const PANEL_ROW = 'flex items-center justify-between gap-4 py-3.5 first:pt-0 last:pb-0';

interface PanelViewProps {
  readonly task: ScheduledTask;
  readonly agent: Agent | null;
  readonly runs: ScheduledTaskRun[] | null;
  readonly base: string;
}

/** Compact single-column task detail shown in the scheduled tasks side panel. */
function ScheduledTaskPanelView({ task, agent, runs, base }: Readonly<PanelViewProps>) {
  const [tab, setTab] = useState<PanelTab>('info');
  const lastRun = runs?.[0];
  const lastRunFailed = lastRun?.status === 'failed';

  return (
    <div className="space-y-4 px-4 py-4">
      <ServiceLifecycleAlert warnings={task.lifecycle_warnings} variant="full" />
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-3">
          <h3 className="min-w-0 font-display text-[22px] leading-tight text-fg dark:text-fg-dark break-words">{task.name}</h3>
          <span className="flex-shrink-0">
            <Badge
              label={task.status === 'active' ? 'Activa' : 'Pausada'}
              variant={task.status === 'active' ? 'success' : 'warning'}
            />
          </span>
        </div>
        {task.description && (
          <p className="mt-1 text-sm text-fg-tertiary dark:text-fg-tertiary-dark break-words">{task.description}</p>
        )}
      </div>

      <ButtonLink
        label="Editar programación"
        to={`${base}/edit`}
        variant="primary"
        size="medium"
        className="w-full"
        icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
      />

      <SegmentedTabs
        tabs={PANEL_TABS}
        activeTab={tab}
        onChange={setTab}
        ariaLabel="Scheduled task details"
      />

      {tab === 'info' ? (
        <>
          <CardApp>
            <h4 className={PANEL_CARD_TITLE}>Configuración general</h4>
            <dl className="divide-y divide-line dark:divide-line-dark">
              <div className={PANEL_ROW}>
                <dt className={PANEL_DT}>Agente</dt>
                <dd className={PANEL_DD}>{agent?.name ?? `Agente #${task.agent_id}`}</dd>
              </div>
              <div className={PANEL_ROW}>
                <dt className={PANEL_DT}>Programación</dt>
                <dd className={PANEL_DD}>{describeSchedule(task.cron_expression)}</dd>
              </div>
              <div className={PANEL_ROW}>
                <dt className={PANEL_DT}>Modo de conversación</dt>
                <dd className={PANEL_DD}>{conversationModeLabel(task.conversation_mode)}</dd>
              </div>
              <div className={PANEL_ROW}>
                <dt className={PANEL_DT}>Visibilidad</dt>
                <dd className={PANEL_DD}>{VISIBILITY_LABELS[task.marketplace_visibility] ?? task.marketplace_visibility}</dd>
              </div>
              <div className="py-3.5 last:pb-0">
                <dt className={PANEL_DT}>Próxima ejecución</dt>
                <dd className={`${PANEL_DD} mt-1`}>
                  {formatDateTime(task.next_run_at)}{' '}
                  <span className="text-xs font-normal text-fg-tertiary dark:text-fg-tertiary-dark">({task.timezone})</span>
                </dd>
              </div>
            </dl>
          </CardApp>

          <CardApp>
            <h4 className={PANEL_CARD_TITLE}>Input de la tarea</h4>
            <span className="block whitespace-pre-wrap break-words text-sm text-fg-secondary dark:text-fg-secondary-dark">
              {formatInput(task.input)}
            </span>
          </CardApp>

          {lastRunFailed && (
            <div className="space-y-2 px-1">
              <h4 className="flex items-center gap-2 text-sm font-medium text-fg dark:text-fg-dark">
                <AlertTriangle className="h-4 w-4 text-error dark:text-error-dark" aria-hidden="true" />
                Última ejecución con errores
              </h4>
              {lastRun?.error_summary && (
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark break-words">{lastRun.error_summary}</p>
              )}
              <button
                type="button"
                onClick={() => setTab('runs')}
                className="flex w-full items-center justify-center gap-2 rounded-full border border-line px-4 py-2 text-xs font-medium text-fg-secondary transition-colors hover:bg-surface-hover dark:border-line-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
              >
                Ver historial
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </div>
          )}
        </>
      ) : (
        <ScheduledTaskResults
          conversationMode={task.conversation_mode}
          runs={runs}
          maxRunsRetained={task.max_runs_retained}
          resolveFileUrl={(runId, fileId) => apiService.getScheduledTaskRunFileUrl(task.app_id, task.id, runId, fileId)}
        />
      )}
    </div>
  );
}

interface DetailPageProps {
  /** Overrides the `:taskId` route param when embedded in the side panel. */
  readonly taskId?: number;
  readonly variant?: 'page' | 'panel';
}

export default function ScheduledTaskDetailPage({ taskId: taskIdProp, variant = 'page' }: Readonly<DetailPageProps>) {
  const { appId, taskId } = useParams();
  const isPanel = variant === 'panel';
  const numericAppId = Number.parseInt(appId ?? '0', 10);
  const numericTaskId = taskIdProp ?? Number.parseInt(taskId ?? '0', 10);
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

  if (loading) {
    return isPanel
      ? <p className="px-4 py-6 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">Cargando tarea…</p>
      : <div className="rounded-xl bg-white p-8 text-center text-gray-500 dark:bg-gray-800">Cargando tarea…</div>;
  }
  if (!task) {
    return isPanel
      ? <p className="px-4 py-6 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">No se encontró la tarea programada.</p>
      : <div className="rounded-xl bg-white p-8 text-center text-gray-600 dark:bg-gray-800">No se encontró la tarea programada.</div>;
  }

  const base = `/apps/${appId}/scheduled-tasks/${task.id}`;
  if (isPanel) return <ScheduledTaskPanelView task={task} agent={agent} runs={runs} base={base} />;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <ServiceLifecycleAlert warnings={task.lifecycle_warnings} variant="full" />
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
        resolveFileUrl={(runId, fileId) => apiService.getScheduledTaskRunFileUrl(numericAppId, task.id, runId, fileId)}
      />
    </div>
  );
}
