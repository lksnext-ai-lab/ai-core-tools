import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  CalendarClock,
  Clock3,
  Edit3,
  Eye,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
  AlertTriangle,
} from 'lucide-react';
import { apiService, type AgentRunSummary, type AgentSchedule } from '../../services/api';
import Modal from '../ui/Modal';

interface AgentSchedulePanelProps {
  readonly appId: number;
  readonly agentId: number;
  readonly canEdit?: boolean;
}

type Frequency = 'interval' | 'daily' | 'weekly' | 'monthly';
type RunFilter = 'all' | 'queued' | 'running' | 'completed' | 'failed';

const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

function formatDate(value?: string | null, timezone = localTimezone): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: timezone,
  }).format(new Date(value));
}

function relativeTime(value?: string | null): string {
  if (!value) return 'Sin ejecuciones';
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60000);
  if (minutes < 1) return 'Ahora';
  if (minutes < 60) return `Hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `Hace ${hours} h`;
  return `Hace ${Math.round(hours / 24)} d`;
}

function describeCron(cron: string, timezone: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return `Expresión cron (${timezone})`;
  const [minute, hour, day, monthDay, month] = parts;
  if (minute.startsWith('*/') && hour === '*') return `Cada ${minute.slice(2)} minutos (${timezone})`;
  if (minute === '0' && hour.startsWith('*/')) return `Cada ${hour.slice(2)} horas (${timezone})`;
  if (day === '*' && monthDay === '*' && month === '*') return `Cada día a las ${hour.padStart(2, '0')}:${minute.padStart(2, '0')} (${timezone})`;
  if (monthDay !== '*') return `El día ${monthDay} de cada mes a las ${hour}:${minute.padStart(2, '0')} (${timezone})`;
  if (day !== '*') return `Cada semana, día ${day}, a las ${hour}:${minute.padStart(2, '0')} (${timezone})`;
  return `Programación personalizada (${timezone})`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: 'En cola', running: 'Ejecutando', completed: 'Completado', succeeded: 'Completado',
    failed: 'Falló', retrying: 'Reintentando',
  };
  return labels[status.toLowerCase()] ?? status;
}

function runStatusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === 'completed' || normalized === 'succeeded') return 'bg-green-100 text-green-800';
  if (normalized === 'failed') return 'bg-red-100 text-red-800';
  if (normalized === 'running' || normalized === 'retrying') return 'bg-blue-100 text-blue-800';
  return 'bg-gray-100 text-gray-700';
}

function duration(run: AgentRunSummary): string {
  if (!run.started_at) return 'No iniciado';
  if (!run.finished_at) return 'En curso';
  const seconds = Math.max(0, Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function defaultForm() {
  return { frequency: 'daily' as Frequency, interval: 30, time: '08:00', weekday: '1', monthDay: '1', cron: '0 8 * * *', timezone: localTimezone, context: '' };
}

export default function AgentSchedulePanel({ appId, agentId, canEdit = true }: AgentSchedulePanelProps) {
  const [schedules, setSchedules] = useState<AgentSchedule[]>([]);
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [editing, setEditing] = useState<AgentSchedule | null>(null);
  const [form, setForm] = useState(defaultForm);
  const [advanced, setAdvanced] = useState(false);
  const [filter, setFilter] = useState<RunFilter>('all');
  const [selectedRun, setSelectedRun] = useState<AgentRunSummary | null>(null);
  const [rerunning, setRerunning] = useState(false);
  const [page, setPage] = useState(1);

  const loadSchedules = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const loaded = await apiService.getAgentSchedules(appId, agentId);
      setSchedules(loaded);
      const runPages = await Promise.all(loaded.map((schedule) => apiService.getAgentScheduleRuns(appId, agentId, schedule.id, 1, 20)));
      setRuns(runPages.flatMap((result) => result.items).sort((a, b) => new Date(b.scheduled_time).getTime() - new Date(a.scheduled_time).getTime()));
    } catch (error) {
      if (!silent) toast.error(error instanceof Error ? error.message : 'No se pudieron cargar las programaciones');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [agentId, appId]);

  useEffect(() => { void loadSchedules(); }, [loadSchedules]);

  const hasLiveRuns = runs.some((run) => ['queued', 'running', 'retrying'].includes(run.status.toLowerCase()));
  useEffect(() => {
    if (!hasLiveRuns) return undefined;
    const timer = window.setInterval(() => { void loadSchedules(true); }, 15000);
    return () => window.clearInterval(timer);
  }, [hasLiveRuns, loadSchedules]);

  const filteredRuns = useMemo(() => filter === 'all' ? runs : runs.filter((run) => {
    const status = run.status.toLowerCase();
    return filter === 'queued' ? status === 'queued' : filter === 'running' ? ['running', 'retrying'].includes(status) : filter === 'completed' ? ['completed', 'succeeded'].includes(status) : status === 'failed';
  }), [filter, runs]);

  const cronFromSimple = () => {
    const [hour, minute] = form.time.split(':');
    if (form.frequency === 'interval') return form.interval % 60 === 0 ? `0 */${Math.max(1, form.interval / 60)} * * *` : `*/${form.interval} * * * *`;
    if (form.frequency === 'weekly') return `${minute} ${hour} * * ${form.weekday}`;
    if (form.frequency === 'monthly') return `${minute} ${hour} ${form.monthDay} * *`;
    return `${minute} ${hour} * * *`;
  };

  const openCreate = () => { setEditing(null); setForm(defaultForm()); setAdvanced(false); setShowEditor(true); };
  const openEdit = (schedule: AgentSchedule) => {
    setEditing(schedule); setAdvanced(true); setForm({ ...defaultForm(), cron: schedule.cron_expression, timezone: schedule.timezone, context: schedule.input_context ? JSON.stringify(schedule.input_context, null, 2) : '' }); setShowEditor(true);
  };

  const saveSchedule = async () => {
    const cron = advanced ? form.cron.trim() : cronFromSimple();
    if (cron.split(/\s+/).length !== 5) { toast.error('La expresión cron debe tener 5 campos.'); return; }
    let context: Record<string, unknown> | null = null;
    if (form.context.trim()) {
      try { context = JSON.parse(form.context) as Record<string, unknown>; } catch { toast.error('El contexto debe ser un JSON válido.'); return; }
    }
    setSaving(true);
    try {
      const payload = { cron_expression: cron, timezone: form.timezone, input_context: context, max_concurrent_runs: 1 };
      if (editing) await apiService.updateAgentSchedule(appId, agentId, editing.id, payload);
      else await apiService.createAgentSchedule(appId, agentId, payload);
      setShowEditor(false); toast.success(editing ? 'Programación actualizada' : 'Programación creada y activada'); await loadSchedules(true);
    } catch (error) { toast.error(error instanceof Error ? error.message : 'No se pudo guardar la programación'); }
    finally { setSaving(false); }
  };

  const toggleSchedule = async (schedule: AgentSchedule) => {
    try { await apiService.updateAgentSchedule(appId, agentId, schedule.id, { status: schedule.status === 'active' ? 'paused' : 'active' }); toast.success(schedule.status === 'active' ? 'Programación pausada' : 'Programación reanudada'); await loadSchedules(true); }
    catch (error) { toast.error(error instanceof Error ? error.message : 'No se pudo actualizar la programación'); }
  };

  const removeSchedule = async (schedule: AgentSchedule) => {
    if (!window.confirm('¿Eliminar esta programación? Esta acción no se puede deshacer.')) return;
    try { await apiService.deleteAgentSchedule(appId, agentId, schedule.id); toast.success('Programación eliminada'); await loadSchedules(true); }
    catch (error) { toast.error(error instanceof Error ? error.message : 'No se pudo eliminar la programación'); }
  };

  const rerunNow = async () => {
    if (!selectedRun) return;
    const schedule = schedules.find((item) => item.id === selectedRun.agent_schedule_id);
    if (!schedule) return;
    setRerunning(true);
    try {
      const message = schedule.input_context && Object.keys(schedule.input_context).length > 0
        ? JSON.stringify(schedule.input_context)
        : 'Ejecuta la tarea programada ahora.';
      await apiService.chatWithAgent(appId, agentId, message);
      toast.success('Ejecución manual iniciada');
      setSelectedRun(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'No se pudo iniciar la ejecución');
    } finally {
      setRerunning(false);
    }
  };

  const hasConsecutiveFailures = schedules.some((schedule) => {
    const scheduleRuns = runs
      .filter((run) => run.agent_schedule_id === schedule.id)
      .sort((a, b) => new Date(b.scheduled_time).getTime() - new Date(a.scheduled_time).getTime());
    return scheduleRuns.length >= 3
      && scheduleRuns.slice(0, 3).every((run) => run.status.toLowerCase() === 'failed');
  });

  if (loading) return <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center text-gray-500"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />Cargando programación…</div>;

  return <div className="space-y-6">
    {hasConsecutiveFailures && <div role="alert" className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" /><div><p className="font-semibold">Esta programación ha fallado tres veces seguidas</p><p className="mt-1 text-sm">Revisa la configuración del agente y el detalle de las ejecuciones recientes.</p></div></div>}
    <section className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
        <div><div className="flex items-center gap-3"><CalendarClock className="w-6 h-6 text-blue-600" /><h2 className="text-xl font-semibold text-gray-900">Programaciones activas</h2></div><p className="text-sm text-gray-500 mt-1">Ejecuta este agente automáticamente en el horario que elijas.</p></div>
        {canEdit && <button type="button" onClick={openCreate} className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium"><Plus className="w-4 h-4" />Programar ejecución periódica</button>}
      </div>
      {schedules.length === 0 ? <div className="border border-dashed border-gray-300 rounded-xl p-8 text-center"><Clock3 className="w-8 h-8 text-gray-400 mx-auto mb-2" /><p className="text-gray-600">Este agente todavía no tiene una programación.</p></div> : <div className="space-y-3">{schedules.map((schedule) => {
        const latest = runs.find((run) => run.agent_schedule_id === schedule.id);
        return <div key={schedule.id} className={`border rounded-xl p-4 ${schedule.status === 'paused' ? 'opacity-65 bg-gray-50' : 'border-gray-200'}`}><div className="flex flex-wrap items-center justify-between gap-4"><div><p className="font-medium text-gray-900">{describeCron(schedule.cron_expression, schedule.timezone)}</p><p className="text-xs text-gray-500 mt-1">{schedule.status === 'paused' ? 'Pausada · sin próxima ejecución' : `Próxima ejecución: ${formatDate(schedule.next_run_at, localTimezone)} (${localTimezone})`}</p>{latest && <p className="text-xs text-gray-500 mt-2">Última ejecución: <span className={latest.status.toLowerCase() === 'failed' ? 'text-red-600 font-medium' : 'text-gray-700'}>{statusLabel(latest.status)} · {relativeTime(latest.finished_at ?? latest.started_at ?? latest.scheduled_time)}</span></p>}</div><div className="flex items-center gap-2">{canEdit && <><button type="button" aria-label={schedule.status === 'active' ? 'Pausar programación' : 'Reanudar programación'} onClick={() => { void toggleSchedule(schedule); }} title={schedule.status === 'active' ? 'Pausar' : 'Reanudar'} className="p-2 text-gray-500 hover:text-blue-600 rounded-lg hover:bg-blue-50">{schedule.status === 'active' ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}</button><button type="button" aria-label="Editar programación" onClick={() => openEdit(schedule)} title="Editar" className="p-2 text-gray-500 hover:text-blue-600 rounded-lg hover:bg-blue-50"><Edit3 className="w-4 h-4" /></button><button type="button" aria-label="Eliminar programación" onClick={() => { void removeSchedule(schedule); }} title="Eliminar" className="p-2 text-gray-500 hover:text-red-600 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4" /></button></>}</div></div></div>;
      })}</div>}
    </section>

    <section className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4"><div><h2 className="text-xl font-semibold text-gray-900">Historial de ejecuciones</h2><p className="text-sm text-gray-500 mt-1">Se actualiza automáticamente mientras haya ejecuciones en curso.</p></div><button type="button" onClick={() => { void loadSchedules(true); }} className="p-2 text-gray-500 hover:text-blue-600 rounded-lg hover:bg-blue-50" title="Actualizar"><RefreshCw className="w-4 h-4" /></button></div>
      <div className="flex flex-wrap gap-2 mb-4">{(['all', 'queued', 'running', 'completed', 'failed'] as RunFilter[]).map((value) => <button type="button" key={value} onClick={() => { setFilter(value); setPage(1); }} className={`px-3 py-1.5 rounded-full text-xs font-medium ${filter === value ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>{value === 'all' ? 'Todos' : statusLabel(value)}</button>)}</div>
      {filteredRuns.length === 0 ? <p className="text-sm text-gray-500 py-8 text-center">No hay ejecuciones para este filtro.</p> : <div className="overflow-x-auto"><table className="min-w-full text-sm"><thead><tr className="text-left text-xs uppercase tracking-wide text-gray-500 border-b"><th className="py-3 pr-4">Programada</th><th className="py-3 pr-4">Estado</th><th className="py-3 pr-4">Duración</th><th className="py-3 pr-4">Resumen</th><th className="py-3 text-right"> </th></tr></thead><tbody className="divide-y divide-gray-100">{filteredRuns.slice((page - 1) * 10, page * 10).map((run) => <tr key={run.id}><td className="py-3 pr-4 whitespace-nowrap">{formatDate(run.scheduled_time)}</td><td className="py-3 pr-4"><span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${runStatusClass(run.status)}`}>{run.status.toLowerCase() === 'running' && <Loader2 className="w-3 h-3 animate-spin" />}{statusLabel(run.status)}</span></td><td className="py-3 pr-4 text-gray-600">{duration(run)}</td><td className="py-3 pr-4 max-w-xs truncate text-gray-600">{run.error_summary ?? (run.output_summary ? JSON.stringify(run.output_summary) : '—')}</td><td className="py-3 text-right"><button type="button" onClick={() => setSelectedRun(run)} className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 text-xs font-medium"><Eye className="w-4 h-4" />Ver detalle</button></td></tr>)}</tbody></table></div>}
      {filteredRuns.length > 10 && <div className="flex justify-end gap-2 mt-4"><button type="button" disabled={page === 1} onClick={() => setPage((current) => current - 1)} className="px-3 py-1.5 text-xs border rounded disabled:opacity-40">Anterior</button><button type="button" disabled={page * 10 >= filteredRuns.length} onClick={() => setPage((current) => current + 1)} className="px-3 py-1.5 text-xs border rounded disabled:opacity-40">Siguiente</button></div>}
    </section>

    <Modal isOpen={showEditor} onClose={() => setShowEditor(false)} title={editing ? 'Editar programación' : 'Configurar programación'} size="medium"><div className="space-y-5">
      <div className="flex items-center justify-between"><div><p className="text-sm font-medium text-gray-900">Modo de configuración</p><p className="text-xs text-gray-500">Usa el modo simple si no conoces cron.</p></div><button type="button" onClick={() => setAdvanced((value) => !value)} className="text-sm text-blue-600 hover:text-blue-800">{advanced ? 'Usar modo simple' : 'Usar expresión cron'}</button></div>
      {advanced ? <div><label htmlFor="schedule-cron" className="block text-sm font-medium text-gray-700 mb-1">Expresión cron</label><input id="schedule-cron" value={form.cron} onChange={(event) => setForm((current) => ({ ...current, cron: event.target.value }))} placeholder="0 8 * * 1" className="w-full px-3 py-2 border rounded-lg font-mono" /><p className="text-xs text-gray-500 mt-1">Cinco campos: minuto hora día-del-mes mes día-de-la-semana.</p></div> : <div className="space-y-4"><div><label htmlFor="schedule-frequency" className="block text-sm font-medium text-gray-700 mb-1">Frecuencia</label><select id="schedule-frequency" value={form.frequency} onChange={(event) => setForm((current) => ({ ...current, frequency: event.target.value as Frequency }))} className="w-full px-3 py-2 border rounded-lg"><option value="interval">Cada X minutos/horas</option><option value="daily">Diariamente</option><option value="weekly">Semanalmente</option><option value="monthly">Mensualmente</option></select></div>{form.frequency === 'interval' && <div><label htmlFor="schedule-interval" className="block text-sm font-medium text-gray-700 mb-1">Intervalo (minutos)</label><input id="schedule-interval" type="number" min="1" max="1440" value={form.interval} onChange={(event) => setForm((current) => ({ ...current, interval: Number(event.target.value) }))} className="w-full px-3 py-2 border rounded-lg" /></div>}{form.frequency !== 'interval' && <div><label htmlFor="schedule-time" className="block text-sm font-medium text-gray-700 mb-1">Hora</label><input id="schedule-time" type="time" value={form.time} onChange={(event) => setForm((current) => ({ ...current, time: event.target.value }))} className="w-full px-3 py-2 border rounded-lg" /></div>}{form.frequency === 'weekly' && <div><label htmlFor="schedule-weekday" className="block text-sm font-medium text-gray-700 mb-1">Día de la semana</label><select id="schedule-weekday" value={form.weekday} onChange={(event) => setForm((current) => ({ ...current, weekday: event.target.value }))} className="w-full px-3 py-2 border rounded-lg"><option value="1">Lunes</option><option value="2">Martes</option><option value="3">Miércoles</option><option value="4">Jueves</option><option value="5">Viernes</option><option value="6">Sábado</option><option value="0">Domingo</option></select></div>}{form.frequency === 'monthly' && <div><label htmlFor="schedule-month-day" className="block text-sm font-medium text-gray-700 mb-1">Día del mes</label><input id="schedule-month-day" type="number" min="1" max="28" value={form.monthDay} onChange={(event) => setForm((current) => ({ ...current, monthDay: event.target.value }))} className="w-full px-3 py-2 border rounded-lg" /></div>}</div>}
      <div><label htmlFor="schedule-timezone" className="block text-sm font-medium text-gray-700 mb-1">Zona horaria</label><input id="schedule-timezone" value={form.timezone} onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))} className="w-full px-3 py-2 border rounded-lg" /></div>
      <div><label htmlFor="schedule-context" className="block text-sm font-medium text-gray-700 mb-1">Contexto de entrada <span className="font-normal text-gray-500">(opcional, JSON)</span></label><textarea id="schedule-context" rows={4} value={form.context} onChange={(event) => setForm((current) => ({ ...current, context: event.target.value }))} placeholder={'{\n  "period": "weekly"\n}'} className="w-full px-3 py-2 border rounded-lg font-mono text-sm" /></div>
      <div className="flex justify-end gap-3 pt-2"><button type="button" onClick={() => setShowEditor(false)} className="px-4 py-2 border rounded-lg text-sm">Cancelar</button><button type="button" disabled={saving} onClick={() => { void saveSchedule(); }} className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm disabled:opacity-50">{saving && <Loader2 className="w-4 h-4 animate-spin" />}{editing?.status === 'paused' ? 'Guardar (permanece pausada)' : 'Guardar y activar'}</button></div>
    </div></Modal>

    <Modal isOpen={!!selectedRun} onClose={() => setSelectedRun(null)} title="Detalle de ejecución" size="medium">{selectedRun && <div className="space-y-4 text-sm"><div className="grid grid-cols-2 gap-3"><div><span className="text-gray-500">Estado</span><p className="font-medium">{statusLabel(selectedRun.status)}</p></div><div><span className="text-gray-500">Intentos</span><p className="font-medium">{selectedRun.attempt_count}</p></div><div><span className="text-gray-500">Hora programada</span><p className="font-medium">{formatDate(selectedRun.scheduled_time)}</p></div><div><span className="text-gray-500">Duración</span><p className="font-medium">{duration(selectedRun)}</p></div></div>{selectedRun.error_summary && <div className="bg-red-50 text-red-800 rounded-lg p-3"><div className="flex gap-2 items-start"><XCircle className="w-4 h-4 mt-0.5 shrink-0" /><span>{selectedRun.error_summary}</span></div></div>}{selectedRun.output_summary && <div><h4 className="font-medium text-gray-900 mb-2">Salida</h4><pre className="bg-gray-50 rounded-lg p-3 overflow-auto text-xs whitespace-pre-wrap">{JSON.stringify(selectedRun.output_summary, null, 2)}</pre></div>}<p className="text-xs text-gray-500">ID de ejecución: {selectedRun.orchestrator_run_id}</p><div className="flex justify-end"><button type="button" onClick={() => { void rerunNow(); }} disabled={rerunning} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">{rerunning && <Loader2 className="h-4 w-4 animate-spin" />}Volver a ejecutar ahora</button></div></div>}</Modal>
  </div>;
}
