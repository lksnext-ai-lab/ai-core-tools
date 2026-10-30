import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { AlertTriangle, ArrowRight, CalendarClock, Pencil, PlayCircle } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { apiService, type Agent, type ScheduledTask, type ScheduledTaskRun } from '../services/api';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';
import { ScheduledTaskResults } from '../components/scheduled-tasks/ScheduledTaskResults';
import { describeSchedule, formatDateTime } from '../components/scheduled-tasks/format';
import Title from '../components/ui/Title';
import ButtonApp from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import CardApp from '../components/ui/CardApp';
import Badge from '../components/ui/Badge';
import { SegmentedTabs } from '../components/ui/SegmentedTabs';

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
  const { t } = useTranslation('common');
  const [tab, setTab] = useState<PanelTab>('info');
  const lastRun = runs?.[0];
  const lastRunFailed = lastRun?.status === 'failed';
  const panelTabs: { id: PanelTab; label: string }[] = [
    { id: 'info', label: t('scheduledTaskDetailPage.tabs.info') },
    { id: 'runs', label: t('scheduledTaskDetailPage.tabs.runs') },
  ];
  const visibilityLabels: Record<string, string> = {
    unpublished: t('scheduledTaskDetailPage.visibility.unpublished'),
    private: t('scheduledTaskDetailPage.visibility.private'),
    public: t('scheduledTaskDetailPage.visibility.public'),
  };

  return (
    <div className="space-y-4 px-4 py-4">
      <ServiceLifecycleAlert warnings={task.lifecycle_warnings} variant="full" />
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-3">
          <h3 className="min-w-0 font-display text-[22px] leading-tight text-fg dark:text-fg-dark break-words">{task.name}</h3>
          <span className="flex-shrink-0">
            <Badge
              label={task.status === 'active' ? t('scheduledTaskDetailPage.status.active') : t('scheduledTaskDetailPage.status.paused')}
              variant={task.status === 'active' ? 'success' : 'warning'}
            />
          </span>
        </div>
        {task.description && (
          <p className="mt-1 text-sm text-fg-tertiary dark:text-fg-tertiary-dark break-words">{task.description}</p>
        )}
      </div>

      <ButtonLink
        label={t('scheduledTaskDetailPage.editSchedule')}
        to={`${base}/edit`}
        variant="primary"
        size="medium"
        className="w-full"
        icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
      />

      <SegmentedTabs
        tabs={panelTabs}
        activeTab={tab}
        onChange={setTab}
        ariaLabel={t('scheduledTaskDetailPage.tabs.ariaLabel')}
      />

      {tab === 'info' ? (
        <>
          <CardApp>
            <h4 className={PANEL_CARD_TITLE}>{t('scheduledTaskDetailPage.generalConfiguration')}</h4>
            <dl className="divide-y divide-line dark:divide-line-dark">
              <div className={PANEL_ROW}>
                <dt className={PANEL_DT}>{t('scheduledTaskDetailPage.fields.agent')}</dt>
                <dd className={PANEL_DD}>{agent?.name ?? t('scheduledTaskDetailPage.agentFallback', { id: task.agent_id })}</dd>
              </div>
              <div className={PANEL_ROW}>
                <dt className={PANEL_DT}>{t('scheduledTaskDetailPage.fields.schedule')}</dt>
                <dd className={PANEL_DD}>{describeSchedule(task.cron_expression, (key, options) => t(key, options))}</dd>
              </div>
              <div className={PANEL_ROW}>
                <dt className={PANEL_DT}>{t('scheduledTaskDetailPage.fields.conversationMode')}</dt>
                <dd className={PANEL_DD}>{t(task.conversation_mode === 'continuous' ? 'scheduledTaskDetailPage.conversationModes.continuous' : 'scheduledTaskDetailPage.conversationModes.newPerRun')}</dd>
              </div>
              <div className={PANEL_ROW}>
                <dt className={PANEL_DT}>{t('scheduledTaskDetailPage.fields.visibility')}</dt>
                <dd className={PANEL_DD}>{visibilityLabels[task.marketplace_visibility] ?? task.marketplace_visibility}</dd>
              </div>
              <div className="py-3.5 last:pb-0">
                <dt className={PANEL_DT}>{t('scheduledTaskDetailPage.fields.nextRun')}</dt>
                <dd className={`${PANEL_DD} mt-1`}>
                  {formatDateTime(task.next_run_at)}{' '}
                  <span className="text-xs font-normal text-fg-tertiary dark:text-fg-tertiary-dark">({task.timezone})</span>
                </dd>
              </div>
            </dl>
          </CardApp>

          <CardApp>
            <h4 className={PANEL_CARD_TITLE}>{t('scheduledTaskDetailPage.fields.taskInput')}</h4>
            <span className="block whitespace-pre-wrap break-words text-sm text-fg-secondary dark:text-fg-secondary-dark">
              {formatInput(task.input)}
            </span>
          </CardApp>

          {lastRunFailed && (
            <div className="space-y-2 px-1">
              <h4 className="flex items-center gap-2 text-sm font-medium text-fg dark:text-fg-dark">
                <AlertTriangle className="h-4 w-4 text-error dark:text-error-dark" aria-hidden="true" />
                {t('scheduledTaskDetailPage.lastRunFailed')}
              </h4>
              {lastRun?.error_summary && (
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark break-words">{lastRun.error_summary}</p>
              )}
              <button
                type="button"
                onClick={() => setTab('runs')}
                className="flex w-full items-center justify-center gap-2 rounded-full border border-line px-4 py-2 text-xs font-medium text-fg-secondary transition-colors hover:bg-surface-hover dark:border-line-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
              >
                {t('scheduledTaskDetailPage.viewHistory')}
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
  const { t } = useTranslation('common');
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
        .catch((error) => toast.error(error instanceof Error ? error.message : t('scheduledTaskDetailPage.loadFailed')))
      .finally(() => setLoading(false));
      }, [numericAppId, numericTaskId, loadRuns, t]);

  const runNow = async () => {
    if (!task) return;
    setRunning(true);
    try {
      await apiService.runScheduledTaskNow(numericAppId, task.id);
      toast.success(t('scheduledTaskDetailPage.runQueued'));
      setTimeout(() => { void loadRuns(); }, 3000);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('scheduledTaskDetailPage.runFailed'));
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return isPanel
      ? <p className="px-4 py-6 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{t('scheduledTaskDetailPage.loading')}</p>
      : <div className="rounded-xl bg-white p-8 text-center text-gray-500 dark:bg-gray-800">{t('scheduledTaskDetailPage.loading')}</div>;
  }
  if (!task) {
    return isPanel
      ? <p className="px-4 py-6 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{t('scheduledTaskDetailPage.notFound')}</p>
      : <div className="rounded-xl bg-white p-8 text-center text-gray-600 dark:bg-gray-800">{t('scheduledTaskDetailPage.notFound')}</div>;
  }

  const base = `/apps/${appId}/scheduled-tasks/${task.id}`;
  const visibilityLabels: Record<string, string> = {
    unpublished: t('scheduledTaskDetailPage.visibility.unpublished'),
    private: t('scheduledTaskDetailPage.visibility.private'),
    public: t('scheduledTaskDetailPage.visibility.public'),
  };
  if (isPanel) return <ScheduledTaskPanelView task={task} agent={agent} runs={runs} base={base} />;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <ServiceLifecycleAlert warnings={task.lifecycle_warnings} variant="full" />
      <div className="flex flex-wrap items-end justify-between gap-4">
        <Title variant="titSecundario" titulo={task.name} subtitulo={task.description || t('scheduledTaskDetailPage.subtitle')} />
        <div className="flex gap-2">
          {task.status === 'active' && (
            <ButtonApp
              label={t('scheduledTaskDetailPage.runNow')}
              type="button"
              variant="secondary"
              size="medium"
              onClick={() => { void runNow(); }}
              loading={running}
              icon={<PlayCircle className="h-4 w-4" aria-hidden="true" />}
            />
          )}
          <ButtonLink
            label={t('scheduledTaskDetailPage.edit')}
            to={`${base}/edit`}
            variant="primary"
            size="medium"
            icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
          />
        </div>
      </div>
      <CardApp>
        <dl className="grid gap-4 p-6 sm:grid-cols-2 ">
          <Field label={t('scheduledTaskDetailPage.fields.agent')}>{agent?.name ?? t('scheduledTaskDetailPage.agentFallback', { id: task.agent_id })}</Field>
          <Field label={t('scheduledTaskDetailPage.fields.status')}>
            <Badge
              label={task.status === 'active' ? t('scheduledTaskDetailPage.status.active') : t('scheduledTaskDetailPage.status.paused')}
              variant={task.status === 'active' ? 'success' : 'default'}
            />
          </Field>
          <Field label={t('scheduledTaskDetailPage.fields.schedule')}>
            <span className="inline-flex items-center gap-2"><CalendarClock className="h-4 w-4 text-fg dark:text-fg-dark" aria-hidden="true" />{describeSchedule(task.cron_expression, (key, options) => t(key, options))}</span>
          </Field>
          <Field label={t('scheduledTaskDetailPage.fields.nextRun')}>{formatDateTime(task.next_run_at)} <span className="text-xs text-gray-500">({task.timezone})</span></Field>
          <Field label={t('scheduledTaskDetailPage.fields.conversationMode')}>{t(task.conversation_mode === 'continuous' ? 'scheduledTaskDetailPage.conversationModes.continuous' : 'scheduledTaskDetailPage.conversationModes.newPerRun')}</Field>
          <Field label={t('scheduledTaskDetailPage.fields.visibility')}>{visibilityLabels[task.marketplace_visibility] ?? task.marketplace_visibility}</Field>
          <Field label={t('scheduledTaskDetailPage.fields.taskInput')} wide>
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
