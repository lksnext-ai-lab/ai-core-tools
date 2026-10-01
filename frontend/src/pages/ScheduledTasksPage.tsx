import { useCallback, useEffect, useState } from 'react';
import { CalendarClock, LoaderCircle, Pause, Pencil, Play, PlayCircle, Trash2 } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { apiService, type ScheduledTask } from '../services/api';

export default function ScheduledTasksPage() {
  const { appId } = useParams();
  const numericAppId = Number.parseInt(appId ?? '0', 10);
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
        setAgentNames(Object.fromEntries(agents.map((agent) => [agent.agent_id, agent.name])));
      } catch {
        // Keep the task list available if agent metadata cannot be loaded.
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'No se pudieron cargar las tareas programadas');
    } finally {
      setLoading(false);
    }
  }, [numericAppId]);

  useEffect(() => { void load(); }, [load]);

  const toggle = async (task: ScheduledTask) => {
    try {
      await apiService.updateScheduledTask(numericAppId, task.id, { status: task.status === 'active' ? 'paused' : 'active' });
      await load();
    } catch (error) { toast.error(error instanceof Error ? error.message : 'No se pudo actualizar la tarea'); }
  };

  const remove = async (task: ScheduledTask) => {
    if (!window.confirm(`¿Eliminar la tarea «${task.name}»?`)) return;
    try { await apiService.deleteScheduledTask(numericAppId, task.id); await load(); }
    catch (error) { toast.error(error instanceof Error ? error.message : 'No se pudo eliminar la tarea'); }
  };

  const runNow = async (task: ScheduledTask) => {
    setRunningTaskId(task.id);
    try {
      await apiService.runScheduledTaskNow(numericAppId, task.id);
      toast.success(`«${task.name}» puesta en cola para ejecución inmediata`);
    } catch (error) { toast.error(error instanceof Error ? error.message : 'No se pudo ejecutar la tarea'); }
    finally { setRunningTaskId(null); }
  };

  return <div className="space-y-6">
    <div className="flex items-center justify-between"><div><h1 className="text-2xl font-bold text-gray-900">Tareas programadas</h1><p className="text-gray-600">Automatiza ejecuciones de agentes sin modificar el agente.</p></div><Link to={`/apps/${appId}/scheduled-tasks/new`} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">Nueva tarea programada</Link></div>
    {loading ? <div className="rounded-xl bg-white p-8 text-center text-gray-500">Cargando tareas…</div> : tasks.length === 0 ? <div className="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center text-gray-600">No hay tareas programadas en este workspace.</div> : <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white"><table className="min-w-full text-sm"><thead><tr className="border-b text-left text-xs uppercase text-gray-500"><th className="px-5 py-3">Tarea</th><th className="px-5 py-3">Agente</th><th className="px-5 py-3">Próxima ejecución</th><th className="px-5 py-3">Estado</th><th className="px-5 py-3 text-right">Acciones</th></tr></thead><tbody className="divide-y divide-gray-100">{tasks.map((task) => <tr key={task.id}><td className="px-5 py-4 font-medium text-gray-900"><Link className="hover:text-blue-600" to={`/apps/${appId}/scheduled-tasks/${task.id}`}>{task.name}</Link><div className="text-xs font-normal text-gray-500">{task.conversation_mode === 'continuous' ? 'Conversación continua' : 'Conversación nueva por ejecución'}</div></td><td className="px-5 py-4"><Link className="text-blue-600 hover:underline" to={`/apps/${appId}/agents/${task.agent_id}`}>{agentNames[task.agent_id] ?? `Agente #${task.agent_id}`}</Link></td><td className="px-5 py-4"><span className="inline-flex items-center gap-2"><CalendarClock className="h-4 w-4 text-blue-600" />{task.next_run_at ? new Date(task.next_run_at).toLocaleString() : 'Sin próxima ejecución'}</span></td><td className="px-5 py-4"><span className={`rounded-full px-2 py-1 text-xs font-medium ${task.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700'}`}>{task.status === 'active' ? 'Activa' : 'Pausada'}</span></td><td className="px-5 py-4 text-right"><Link aria-label="Editar tarea" title="Editar tarea" to={`/apps/${appId}/scheduled-tasks/${task.id}/edit`} className="mr-2 inline-flex rounded p-2 text-gray-500 hover:bg-blue-50 hover:text-blue-600"><Pencil className="h-4 w-4" /></Link>{task.status === 'active' && <button type="button" aria-label="Ejecutar ahora" title="Ejecutar ahora" disabled={runningTaskId === task.id} onClick={() => { void runNow(task); }} className="mr-2 rounded p-2 text-gray-500 hover:bg-blue-50 hover:text-blue-600 disabled:opacity-50">{runningTaskId === task.id ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}</button>}<button type="button" aria-label={task.status === 'active' ? 'Pausar tarea' : 'Reanudar tarea'} onClick={() => { void toggle(task); }} className="mr-2 rounded p-2 text-gray-500 hover:bg-blue-50 hover:text-blue-600">{task.status === 'active' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</button><button type="button" aria-label="Eliminar tarea" onClick={() => { void remove(task); }} className="rounded p-2 text-gray-500 hover:bg-red-50 hover:text-red-600"><Trash2 className="h-4 w-4" /></button></td></tr>)}</tbody></table></div>}
  </div>;
}
