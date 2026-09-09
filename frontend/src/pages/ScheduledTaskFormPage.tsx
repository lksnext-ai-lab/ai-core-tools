import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { MessageCircle } from 'lucide-react';
import { toast } from 'sonner';
import { apiService, type ScheduledTask, type ScheduledTaskRun } from '../services/api';

interface AgentOption { agent_id: number; name: string; }
type Frequency = 'interval' | 'daily' | 'weekly' | 'monthly';

function applyCronToSimpleSchedule(cronExpression: string, setFrequency: (value: Frequency) => void, setInterval: (value: number) => void, setTime: (value: string) => void, setWeekday: (value: string) => void, setMonthDay: (value: string) => void) {
  const fields = cronExpression.trim().split(/\s+/);
  if (fields.length !== 5) return;
  const [minute, hour, dayOfMonth, , dayOfWeek] = fields;
  const hourValue = Number(hour);
  const minuteValue = Number(minute);
  if (minute.startsWith('*/') && hour === '*') {
    setFrequency('interval'); setInterval(Number(minute.slice(2))); return;
  }
  if (minute === '0' && hour.startsWith('*/')) {
    setFrequency('interval'); setInterval(Number(hour.slice(2)) * 60); return;
  }
  if (Number.isInteger(hourValue) && Number.isInteger(minuteValue)) {
    setTime(`${String(hourValue).padStart(2, '0')}:${String(minuteValue).padStart(2, '0')}`);
  }
  if (dayOfWeek !== '*') { setFrequency('weekly'); setWeekday(dayOfWeek); return; }
  if (dayOfMonth !== '*') { setFrequency('monthly'); setMonthDay(dayOfMonth); return; }
  setFrequency('daily');
}

export default function ScheduledTaskFormPage() {
  const { appId, taskId } = useParams();
  const navigate = useNavigate();
  const numericAppId = Number.parseInt(appId ?? '0', 10);
  const editing = taskId !== undefined && taskId !== 'new';
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [task, setTask] = useState<ScheduledTask | null>(null);
  const [name, setName] = useState('');
  const [agentId, setAgentId] = useState('');
  const [input, setInput] = useState('');
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  const [mode, setMode] = useState<'new_per_run' | 'continuous'>('new_per_run');
  const [frequency, setFrequency] = useState<Frequency>('daily');
  const [interval, setInterval] = useState(60);
  const [time, setTime] = useState('08:00');
  const [weekday, setWeekday] = useState('1');
  const [monthDay, setMonthDay] = useState('1');
  const [runs, setRuns] = useState<ScheduledTaskRun[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void apiService.getAgents(numericAppId).then((items) => setAgents(items.map((item) => ({ agent_id: item.agent_id, name: item.name })))).catch(() => toast.error('No se pudieron cargar los agentes'));
    if (editing) {
      void apiService.getScheduledTasks(numericAppId).then((items) => {
        const found = items.find((item) => item.id === Number(taskId));
        if (!found) { toast.error('Tarea no encontrada'); return; }
        setTask(found); setName(found.name); setAgentId(String(found.agent_id)); setInput(found.input?.message ? String(found.input.message) : JSON.stringify(found.input ?? {}, null, 2)); setTimezone(found.timezone); setMode(found.conversation_mode === 'continuous' ? 'continuous' : 'new_per_run');
        applyCronToSimpleSchedule(found.cron_expression, setFrequency, setInterval, setTime, setWeekday, setMonthDay);
        void apiService.getScheduledTaskRuns(numericAppId, found.id).then((result) => setRuns(result.items)).catch(() => toast.error('No se pudo cargar el historial'));
      }).catch(() => toast.error('No se pudo cargar la tarea'));
    }
  }, [editing, numericAppId, taskId]);

  const simpleCron = () => {
    const [hour, minute] = time.split(':').map(Number);
    if (frequency === 'interval') {
      return interval >= 60 && interval % 60 === 0 ? `0 */${interval / 60} * * *` : `*/${interval} * * * *`;
    }
    if (frequency === 'weekly') return `${minute} ${hour} * * ${weekday}`;
    if (frequency === 'monthly') return `${minute} ${hour} ${monthDay} * *`;
    return `${minute} ${hour} * * *`;
  };

  const save = async () => {
    const effectiveCron = simpleCron();
    if (!name.trim() || !agentId || !effectiveCron) { toast.error('Completa el nombre, el agente y la programación'); return; }
    let parsedInput: Record<string, unknown> = {};
    if (input.trim()) {
      try { parsedInput = JSON.parse(input) as Record<string, unknown>; }
      catch { parsedInput = { message: input.trim() }; }
    }
    setSaving(true);
    try {
      if (task) await apiService.updateScheduledTask(numericAppId, task.id, { name, input: parsedInput, cron_expression: effectiveCron, timezone });
      else await apiService.createScheduledTask(numericAppId, { name, agent_id: Number(agentId), input: parsedInput, cron_expression: effectiveCron, timezone, conversation_mode: mode, max_concurrent_runs: 1 });
      toast.success(task ? 'Tarea actualizada' : 'Tarea creada');
      navigate(`/apps/${appId}/scheduled-tasks`);
    } catch (error) { toast.error(error instanceof Error ? error.message : 'No se pudo guardar la tarea'); }
    finally { setSaving(false); }
  };

  return <div className="mx-auto max-w-3xl space-y-6"><div><h1 className="text-2xl font-bold text-gray-900">{task ? 'Editar tarea programada' : 'Nueva tarea programada'}</h1><p className="text-gray-600">Configura qué agente ejecutar y con qué periodicidad.</p></div><div className="space-y-5 rounded-xl border border-gray-200 bg-white p-6"><div><label htmlFor="task-name" className="mb-1 block text-sm font-medium text-gray-700">Nombre de la tarea</label><input id="task-name" value={name} onChange={(event) => setName(event.target.value)} className="w-full rounded-lg border px-3 py-2" placeholder="Informe diario" /></div><div><label htmlFor="task-agent" className="mb-1 block text-sm font-medium text-gray-700">Agente</label><select id="task-agent" value={agentId} disabled={Boolean(task)} onChange={(event) => setAgentId(event.target.value)} className="w-full rounded-lg border px-3 py-2"><option value="">Selecciona un agente</option>{agents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.name}</option>)}</select></div><div><label htmlFor="task-input" className="mb-1 block text-sm font-medium text-gray-700">Input de la tarea</label><textarea id="task-input" value={input} onChange={(event) => setInput(event.target.value)} rows={5} className="w-full rounded-lg border px-3 py-2" placeholder="Escribe el mensaje inicial o un objeto JSON…" /></div><fieldset disabled={Boolean(task)}><legend className="mb-2 text-sm font-medium text-gray-700">Modo de conversación</legend><label className="mb-2 flex gap-2 text-sm"><input type="radio" checked={mode === 'new_per_run'} onChange={() => setMode('new_per_run')} />Cada ejecución empieza una conversación nueva</label><label className="flex gap-2 text-sm"><input type="radio" checked={mode === 'continuous'} onChange={() => setMode('continuous')} />Todas las ejecuciones continúan la misma conversación</label>{mode === 'continuous' && <p className="mt-1 text-xs text-gray-500">El agente verá lo ocurrido en ejecuciones anteriores, como en una conversación normal.</p>}</fieldset><section className="rounded-lg border border-blue-100 bg-blue-50/40 p-4"><div className="mb-3"><h2 className="text-sm font-semibold text-gray-800">Programación</h2><p className="text-xs text-gray-500">Define la frecuencia sin tener que escribir CRON.</p></div><div className="space-y-3"><div><label htmlFor="task-frequency" className="mb-1 block text-sm font-medium text-gray-700">Frecuencia</label><select id="task-frequency" value={frequency} onChange={(event) => setFrequency(event.target.value as Frequency)} className="w-full rounded-lg border px-3 py-2"><option value="interval">Cada X minutos/horas</option><option value="daily">Diariamente</option><option value="weekly">Semanalmente</option><option value="monthly">Mensualmente</option></select></div>{frequency === 'interval' && <div><label htmlFor="task-interval" className="mb-1 block text-sm font-medium text-gray-700">Intervalo (minutos)</label><input id="task-interval" type="number" min="1" max="1440" value={interval} onChange={(event) => setInterval(Number(event.target.value))} className="w-full rounded-lg border px-3 py-2" /></div>}{frequency !== 'interval' && <div><label htmlFor="task-time" className="mb-1 block text-sm font-medium text-gray-700">Hora</label><input id="task-time" type="time" value={time} onChange={(event) => setTime(event.target.value)} className="w-full rounded-lg border px-3 py-2" /></div>}{frequency === 'weekly' && <div><label htmlFor="task-weekday" className="mb-1 block text-sm font-medium text-gray-700">Día de la semana</label><select id="task-weekday" value={weekday} onChange={(event) => setWeekday(event.target.value)} className="w-full rounded-lg border px-3 py-2"><option value="1">Lunes</option><option value="2">Martes</option><option value="3">Miércoles</option><option value="4">Jueves</option><option value="5">Viernes</option><option value="6">Sábado</option><option value="0">Domingo</option></select></div>}{frequency === 'monthly' && <div><label htmlFor="task-month-day" className="mb-1 block text-sm font-medium text-gray-700">Día del mes</label><input id="task-month-day" type="number" min="1" max="28" value={monthDay} onChange={(event) => setMonthDay(event.target.value)} className="w-full rounded-lg border px-3 py-2" /></div>}<p className="text-xs text-gray-500">Se guardará como <code className="rounded bg-white px-1 font-mono">{simpleCron()}</code>.</p></div></section><div><label htmlFor="task-timezone" className="mb-1 block text-sm font-medium text-gray-700">Zona horaria</label><input id="task-timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)} className="w-full rounded-lg border px-3 py-2" /></div><div className="flex justify-end gap-3"><button type="button" onClick={() => navigate(`/apps/${appId}/scheduled-tasks`)} className="rounded-lg border px-4 py-2">Cancelar</button><button type="button" disabled={saving} onClick={() => { void save(); }} className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white disabled:opacity-50">{saving ? 'Guardando…' : 'Guardar y activar'}</button></div></div>{task && <section className="rounded-xl border border-gray-200 bg-white p-6"><h2 className="mb-3 text-lg font-semibold">Historial de ejecuciones</h2>{runs.length === 0 ? <p className="text-sm text-gray-500">No hay ejecuciones todavía.</p> : <div className="space-y-2">{runs.map((run) => <div key={run.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm"><div><div>{new Date(run.scheduled_time).toLocaleString()}</div><div className="text-xs text-gray-500">{run.status}</div></div>{run.conversation_id ? <Link aria-label="Abrir conversación" title="Abrir conversación" className="rounded p-2 text-blue-600 hover:bg-blue-50" to={`/apps/${appId}/agents/${agentId}/playground?conversation_id=${run.conversation_id}`}><MessageCircle className="h-4 w-4" /></Link> : <span className="text-red-600">{run.error_summary ?? 'Sin conversación'}</span>}</div>)}</div>}</section>}</div>;
}
