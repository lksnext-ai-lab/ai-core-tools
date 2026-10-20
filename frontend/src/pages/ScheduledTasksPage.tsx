import { useCallback, useEffect, useState } from "react";
import {
  CalendarClock,
  Pause,
  Pencil,
  Play,
  PlayCircle,
  Trash2,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { apiService, type ScheduledTask } from "../services/api";
import Title from "../components/ui/Title";
import LoadingState from "../components/ui/LoadingState";
import Table, { type TableColumn } from "../components/ui/Table";
import Badge from "../components/ui/Badge";
import ButtonLink from "../components/ui/ButtonLink";
import { Spinner } from "../components/ui/Spinner";

export default function ScheduledTasksPage() {
  const { appId } = useParams();
  const numericAppId = Number.parseInt(appId ?? "0", 10);
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [agentNames, setAgentNames] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [runningTaskId, setRunningTaskId] = useState<number | null>(null);

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
          : "No se pudieron cargar las tareas programadas",
      );
    } finally {
      setLoading(false);
    }
  }, [numericAppId]);

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
          : "No se pudo actualizar la tarea",
      );
    }
  };

  const remove = async (task: ScheduledTask) => {
    if (!window.confirm(`¿Eliminar la tarea «${task.name}»?`)) return;
    try {
      await apiService.deleteScheduledTask(numericAppId, task.id);
      await load();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "No se pudo eliminar la tarea",
      );
    }
  };

  const runNow = async (task: ScheduledTask) => {
    setRunningTaskId(task.id);
    try {
      await apiService.runScheduledTaskNow(numericAppId, task.id);
      toast.success(`«${task.name}» puesta en cola para ejecución inmediata`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "No se pudo ejecutar la tarea",
      );
    } finally {
      setRunningTaskId(null);
    }
  };

  const columns: TableColumn<ScheduledTask>[] = [
    {
      header: "Tarea",
      className: "px-5 py-4 font-medium text-gray-900",
      render: (task) => (
        <>
          <Link
            className="text-sm font-medium text-fg dark:text-fg-dark"
            to={`/apps/${appId}/scheduled-tasks/${task.id}`}
          >
            {task.name}
          </Link>
          <div className="text-xs font-normal text-fg-secondary dark:text-fg-secondary-dark">
            {task.conversation_mode === "continuous"
              ? "Conversación continua"
              : "Conversación nueva por ejecución"}
          </div>
        </>
      ),
    },
    {
      header: "Agente",
      className: "px-5 py-4",
      render: (task) => (
        <Link
          className="text-sm font-medium text-fg dark:text-fg-dark"
          to={`/apps/${appId}/agents/${task.agent_id}`}
        >
          {agentNames[task.agent_id] ?? `Agente #${task.agent_id}`}
        </Link>
      ),
    },
    {
      header: "Próxima ejecución",
      className: "px-5 py-4",
      render: (task) => (
        <span className="inline-flex items-center gap-2 text-xs text-fg-secondary dark:text-fg-secondary-dark">
          <CalendarClock className="h-4 w-4 text-bronze dark:text-bronze-dark" />
          {task.next_run_at
            ? new Date(task.next_run_at).toLocaleString()
            : "Sin próxima ejecución"}
        </span>
      ),
    },
    {
      header: "Estado",
      className: "px-5 py-4",
      render: (task) => (
        <Badge
          label={task.status === "active" ? "Activa" : "Pausada"}
          variant={task.status === "active" ? "success" : "default"}
        />
      ),
    },
    {
      header: "Acciones",
      headerClassName: "text-center",
      className: "px-5 py-4 text-right",
      render: (task) => (
        <>
          <Link
            aria-label="Editar tarea"
            title="Editar tarea"
            to={`/apps/${appId}/scheduled-tasks/${task.id}/edit`}
            className="mr-2 inline-flex rounded p-2 text-fg-secondary dark:text-fg-secondary-dark"
          >
            <Pencil className="h-4 w-4" />
          </Link>
          {task.status === "active" && (
            <button
              type="button"
              aria-label="Ejecutar ahora"
              title="Ejecutar ahora"
              disabled={runningTaskId === task.id}
              onClick={() => {
                void runNow(task);
              }}
              className="mr-2 rounded p-2 text-fg-secondary dark:text-fg-secondary-dark"
            >
              {runningTaskId === task.id ? (
                <Spinner size="sm" tone="current" />
              ) : (
                <PlayCircle className="h-4 w-4" />
              )}
            </button>
          )}
          <button
            type="button"
            aria-label={
              task.status === "active" ? "Pausar tarea" : "Reanudar tarea"
            }
            onClick={() => {
              void toggle(task);
            }}
            className="mr-2 rounded p-2 text-fg-secondary dark:text-fg-secondary-dark"
          >
            {task.status === "active" ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </button>
          <button
            type="button"
            aria-label="Eliminar tarea"
            onClick={() => {
              void remove(task);
            }}
            className="rounded p-2 text-fg-secondary dark:text-fg-secondary-dark"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title
          variant="titSecundario"
          titulo="Tareas programadas"
          subtitulo="Automatiza ejecuciones de agentes sin modificar el agente."
        />

        <ButtonLink
          to={`/apps/${appId}/scheduled-tasks/new`}
          label="Nueva tarea programada"
          variant="primary"
          size="medium"
        />
      </div>
      {loading ? (
        <LoadingState variant="page" message="Cargando tareas…" />
      ) : tasks.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center text-fg dark:text-fg-dark">
          No hay tareas programadas en este workspace.
        </div>
      ) : (
        <Table
          columns={columns}
          data={tasks}
          keyExtractor={(task) => task.id}
          emptyMessage="No hay tareas programadas en este workspace."
        />
      )}
    </div>
  );
}
