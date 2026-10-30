import { useCallback, useEffect, useState } from "react";
import {
  ArrowUpRight,
  CalendarClock,
  LoaderCircle,
  Pause,
  Pencil,
  Play,
  PlayCircle,
  Trash2,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { apiService, type ScheduledTask } from "../services/api";
import Title from "../components/ui/Title";
import LoadingState from "../components/ui/LoadingState";
import Table, { type TableColumn } from "../components/ui/Table";
import Badge from "../components/ui/Badge";
import ButtonLink from "../components/ui/ButtonLink";
import ActionDropdown from "../components/ui/ActionDropdown";
import ServiceLifecycleAlert from "../components/services/ServiceLifecycleAlert";
import { SidePanel } from "../components/ui/SidePanel";
import ScheduledTaskDetailPage from "./ScheduledTaskDetailPage";
import BackgroundImage from "../components/ui/BackgroundImage";

export default function ScheduledTasksPage() {
  const { t, i18n } = useTranslation("common");
  const { appId } = useParams();
  const navigate = useNavigate();
  const numericAppId = Number.parseInt(appId ?? "0", 10);
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [agentNames, setAgentNames] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [runningTaskId, setRunningTaskId] = useState<number | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const handleClosePanel = useCallback(() => setSelectedTaskId(null), []);

  const load = useCallback(async () => {
    try {
      const taskItems = await apiService.getScheduledTasks(numericAppId);
      setTasks(taskItems);
      try {
        const agents = await apiService.getAgents(numericAppId);
        setAgentNames(
          Object.fromEntries(
            agents.map((agent) => [agent.agent_id, agent.name]),
          ),
        );
      } catch {
        // Keep the task list available if agent metadata cannot be loaded.
      }
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("scheduledTasksPage.loadFailed"),
      );
    } finally {
      setLoading(false);
    }
  }, [numericAppId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (task: ScheduledTask) => {
    try {
      await apiService.updateScheduledTask(numericAppId, task.id, {
        status: task.status === "active" ? "paused" : "active",
      });
      await load();
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("scheduledTasksPage.updateFailed"),
      );
    }
  };

  const remove = async (task: ScheduledTask) => {
    if (!window.confirm(t("scheduledTasksPage.confirmDelete", { name: task.name }))) return;
    try {
      await apiService.deleteScheduledTask(numericAppId, task.id);
      await load();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("scheduledTasksPage.deleteFailed"),
      );
    }
  };

  const runNow = async (task: ScheduledTask) => {
    setRunningTaskId(task.id);
    try {
      await apiService.runScheduledTaskNow(numericAppId, task.id);
      toast.success(t("scheduledTasksPage.runQueued", { name: task.name }));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("scheduledTasksPage.runFailed"),
      );
    } finally {
      setRunningTaskId(null);
    }
  };

  const columns: TableColumn<ScheduledTask>[] = [
    {
      header: t("scheduledTasksPage.columns.task"),
      className: "px-5 py-4",
      render: (task) => (
        <div className="flex items-start gap-2">
          <BackgroundImage icon={CalendarClock} variant="marron" />
          <div className="flex min-w-0 flex-col items-start gap-1">
            <Link
              className="font-medium text-fg dark:text-fg-dark"
              to={`/apps/${appId}/scheduled-tasks/${task.id}`}
              onClick={(event) => {
                // Keep native behaviour for new tab / new window clicks.
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
                event.preventDefault();
                setSelectedTaskId(task.id);
              }}
            >
              {task.name}
            </Link>
            <div className="flex flex-wrap items-center gap-2">
              <ServiceLifecycleAlert
                warnings={task.lifecycle_warnings}
                variant="compact"
              />
              <div className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                {task.conversation_mode === "continuous"
                  ? t("scheduledTasksPage.conversationModes.continuous")
                  : t("scheduledTasksPage.conversationModes.newPerRun")}
              </div>
            </div>
          </div>
        </div>
      ),
    },
    {
      header: t("scheduledTasksPage.columns.agent"),
      className: "px-5 py-4",
      render: (task) => (
        <Link
          className="text-xs text-bronze  dark:text-bronze-dark inline-block"
          to={`/apps/${appId}/agents/${task.agent_id}`}
        >
          {agentNames[task.agent_id] ?? t("scheduledTasksPage.agentFallback", { id: task.agent_id })}{''}<ArrowUpRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />

        </Link>
      ),
    },
    {
      header: t("scheduledTasksPage.columns.nextRun"),
      className: "px-5 py-4  text-fg-secondary dark:text-fg-secondary-dark text-xs",
      render: (task) => (
        <span className="inline-flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-fg-tertiary dark:text-fg-tertiary-dark" />
          {task.next_run_at
            ? new Date(task.next_run_at).toLocaleString(i18n.resolvedLanguage ?? i18n.language)
            : t("scheduledTasksPage.noNextRun")}
        </span>
      ),
    },
    {
      header: t("scheduledTasksPage.columns.status"),
      className: "px-5 py-4",
      render: (task) => (
        <Badge
          label={task.status === "active" ? t("scheduledTasksPage.status.active") : t("scheduledTasksPage.status.paused")}
          variant={task.status === "active" ? "success" : "default"}
        />
      ),
    },
    {
      header: t("scheduledTasksPage.columns.actions"),
      sticky: 'right',
      headerClassName: "text-right",
      className: "px-5 py-4 text-right ",
      render: (task) => (
        <ActionDropdown
          triggerText={t("scheduledTasksPage.actions.trigger")}
          triggerAriaLabel={t("scheduledTasksPage.actions.forTask", { name: task.name })}
          size="sm"
          actions={[
            {
              label: t("scheduledTasksPage.actions.edit"),
              onClick: () => navigate(`/apps/${appId}/scheduled-tasks/${task.id}/edit`),
              icon: <Pencil className="h-4 w-4" />,
            },
            ...(task.status === "active"
              ? [{
                  label: t("scheduledTasksPage.actions.runNow"),
                  onClick: () => { void runNow(task); },
                  icon: runningTaskId === task.id
                    ? <LoaderCircle className="h-4 w-4 animate-spin" />
                    : <PlayCircle className="h-4 w-4" />,
                  disabled: runningTaskId === task.id,
                }]
              : []),
            {
              label: task.status === "active" ? t("scheduledTasksPage.actions.pause") : t("scheduledTasksPage.actions.resume"),
              onClick: () => { void toggle(task); },
              icon: task.status === "active"
                ? <Pause className="h-4 w-4" />
                : <Play className="h-4 w-4" />,
            },
            {
              label: t("scheduledTasksPage.actions.delete"),
              onClick: () => { void remove(task); },
              icon: <Trash2 className="h-4 w-4" />,
              variant: "danger",
            },
          ]}
        />
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title variant="titSecundario" titulo={t("scheduledTasksPage.title")} subtitulo={t("scheduledTasksPage.subtitle")} />
        <ButtonLink
          label={t("scheduledTasksPage.createTask")}
          to={`/apps/${appId}/scheduled-tasks/new`}
          variant="primary"
          size="medium"
        />
      </div>
      {loading ? (
        <LoadingState message={t("scheduledTasksPage.loading")} variant="section" />
      ) : (
        <Table<ScheduledTask>
          stickyEdgeColumns
          columns={columns}
          data={tasks}
          keyExtractor={(task) => task.id}
          emptyMessage={t("scheduledTasksPage.emptyMessage")}
          emptyIcon={<BackgroundImage icon={CalendarClock} size={64} iconSize={32} />}
        />
      )}

      {!loading && tasks.length === 0 && (
        <div className="text-center py-6">
          <ButtonLink
            label={t("scheduledTasksPage.createFirstTask")}
            to={`/apps/${appId}/scheduled-tasks/new`}
            variant="primary"
            size="medium"
          />
        </div>
      )}

      {/* Task detail side panel — fixed wrapper that starts below the 56px (h-14) app header */}
      {selectedTaskId !== null && (
        <div className="fixed inset-x-0 bottom-0 top-14 z-30 !mt-0">
          <SidePanel
            open
            side="right"
            onClose={handleClosePanel}
            title={t("scheduledTasksPage.title")}
            headerActions={(
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] normal-case tracking-normal text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
                {t("scheduledTasksPage.detailView")}
              </span>
            )}
            widthClassName="w-[640px] max-w-full"
          >
            <ScheduledTaskDetailPage key={selectedTaskId} taskId={selectedTaskId} variant="panel" />
          </SidePanel>
        </div>
      )}
    </div>
  );
}
