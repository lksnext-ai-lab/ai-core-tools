import { useEffect, useState } from 'react';
import { ArrowLeft, CalendarClock, MessageCircle, Pencil } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { apiService, type Agent, type ScheduledTask, type ScheduledTaskRun } from '../services/api';

function describeSchedule(cron: string): string {
  const [minute, hour, dayOfMonth, , dayOfWeek] = cron.trim().split(/\s+/);
  if (minute?.startsWith('*/') && hour === '*') return `Cada ${minute.slice(2)} minutos`;
  if (minute === '0' && hour?.startsWith('*/')) return `Cada ${hour.slice(2)} horas`;
  const time = Number.isInteger(Number(hour)) && Number.isInteger(Number(minute))
    ? `a las ${String(Number(hour)).padStart(2, '0')}:${String(Number(minute)).padStart(2, '0')}`
    : 'en el horario configurado';
  if (dayOfWeek !== '*') return `Semanalmente ${time}`;
  if (dayOfMonth !== '*') return `Mensualmente, el día ${dayOfMonth} ${time}`;
  return `Diariamente ${time}`;
}

function formatInput(input: Record<string, unknown>): string {
  return input.message ? String(input.message) : JSON.stringify(input, null, 2);
}

export default function ScheduledTaskDetailPage() {
  const { appId, taskId } = useParams();
  const numericAppId = Number.parseInt(appId ?? '0', 10);
  const numericTaskId = Number.parseInt(taskId ?? '0', 10);
  const [task, setTask] = useState<ScheduledTask | null>(null);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [runs, setRuns] = useState<ScheduledTaskRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void Promise.all([
      apiService.getScheduledTasks(numericAppId),
      apiService.getAgents(numericAppId),
      apiService.getScheduledTaskRuns(numericAppId, numericTaskId),
    ]).then(([tasks, agents, runList]) => {
      const found = tasks.find((item) => item.id === numericTaskId);
      if (!found) { toast.error('Tarea no encontrada'); return; }
      setTask(found);
      setAgent(agents.find((item) => item.agent_id === found.agent_id) ?? null);
      setRuns(runList.items);
    }).catch((error) => toast.error(error instanceof Error ? error.message : 'No se pudo cargar el detalle de la tarea'))
      .finally(() => setLoading(false));
  }, [numericAppId, numericTaskId]);

  if (loading) return <div className="rounded-xl bg-white p-8 text-center text-gray-500">Cargando tarea…</div>;
  if (!task) return <div className="rounded-xl bg-white p-8 text-center text-gray-600">No se encontró la tarea programada.</div>;

  return <div className="mx-auto max-w-4xl space-y-6">
    <div className="flex items-center justify-between gap-4">
      <div><Link className="mb-3 inline-flex items-center gap-2 text-sm text-gray-500 hover:text-blue-600" to={`/apps/${appId}/scheduled-tasks`}><ArrowLeft className="h-4 w-4" />Volver a tareas</Link><h1 className="text-2xl font-bold text-gray-900">{task.name}</h1><p className="text-gray-600">Detalle de la tarea programada</p></div>
      <Link aria-label="Editar tarea" title="Editar tarea" to={`/apps/${appId}/scheduled-tasks/${task.id}/edit`} className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-blue-600 hover:bg-blue-50"><Pencil className="h-4 w-4" />Editar</Link>
    </div>
    <section className="grid gap-4 rounded-xl border border-gray-200 bg-white p-6 sm:grid-cols-2">
      <div><dt className="text-xs font-medium uppercase text-gray-500">Agente</dt><dd className="mt-1 text-gray-900">{agent?.name ?? `Agente #${task.agent_id}`}</dd></div>
      <div><dt className="text-xs font-medium uppercase text-gray-500">Estado</dt><dd className="mt-1"><span className={`rounded-full px-2 py-1 text-xs font-medium ${task.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700'}`}>{task.status === 'active' ? 'Activa' : 'Pausada'}</span></dd></div>
      <div><dt className="text-xs font-medium uppercase text-gray-500">Programación</dt><dd className="mt-1 inline-flex items-center gap-2 text-gray-900"><CalendarClock className="h-4 w-4 text-blue-600" />{describeSchedule(task.cron_expression)}</dd></div>
      <div><dt className="text-xs font-medium uppercase text-gray-500">Zona horaria</dt><dd className="mt-1 text-gray-900">{task.timezone}</dd></div>
      <div><dt className="text-xs font-medium uppercase text-gray-500">Modo de conversación</dt><dd className="mt-1 text-gray-900">{task.conversation_mode === 'continuous' ? 'Conversación continua' : 'Conversación nueva por ejecución'}</dd></div>
      <div className="sm:col-span-2"><dt className="text-xs font-medium uppercase text-gray-500">Input de la tarea</dt><dd className="mt-1 whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm text-gray-700">{formatInput(task.input)}</dd></div>
    </section>
    <section className="rounded-xl border border-gray-200 bg-white p-6"><h2 className="mb-4 text-lg font-semibold">Historial de ejecuciones</h2>{runs.length === 0 ? <p className="text-sm text-gray-500">No hay ejecuciones todavía.</p> : <div className="space-y-2">{runs.map((run) => <div key={run.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm"><div><div className="text-gray-900">{new Date(run.scheduled_time).toLocaleString()}</div><div className="text-xs text-gray-500">{run.status}</div></div>{run.conversation_id ? <Link aria-label="Abrir conversación" title="Abrir conversación" className="rounded p-2 text-blue-600 hover:bg-blue-50" to={`/apps/${appId}/agents/${task.agent_id}/playground?conversation_id=${run.conversation_id}`}><MessageCircle className="h-4 w-4" /></Link> : <span className="text-red-600">{run.error_summary ?? 'Sin conversación'}</span>}</div>)}</div>}</section>
  </div>;
}
