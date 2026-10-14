import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { apiService, type OutputDelivery } from '../../services/api';

interface Props { appId: number; taskId: number; runId: number; }

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente', sending: 'Enviando', retry_wait: 'Reintento programado',
  accepted: 'Aceptado por Teams Workflows', delivered: 'Entregado', failed: 'Fallido',
  unknown: 'Resultado incierto', cancelled: 'Cancelado',
};

export function OutputDeliveriesPanel({ appId, taskId, runId }: Readonly<Props>) {
  const [deliveries, setDeliveries] = useState<OutputDelivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState<number | null>(null);
  const load = useCallback(() => apiService.getScheduledTaskRunDeliveries(appId, taskId, runId)
    .then((response) => setDeliveries(response.deliveries))
    .catch(() => setDeliveries([]))
    .finally(() => setLoading(false)), [appId, taskId, runId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!deliveries.some((item) => ['pending', 'sending', 'retry_wait'].includes(item.status))) return undefined;
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => window.clearInterval(timer);
  }, [deliveries, load]);

  const retry = async (delivery: OutputDelivery) => {
    if (delivery.status === 'unknown' && !globalThis.confirm('Teams pudo haber recibido esta tarjeta. Reenviarla podría publicar un duplicado. ¿Quieres continuar?')) return;
    setRetrying(delivery.id);
    try {
      await apiService.retryScheduledTaskDelivery(appId, taskId, runId, delivery.id);
      toast.success('Reintento puesto en cola');
      await load();
    } catch (error) { toast.error(error instanceof Error ? error.message : 'No se pudo reintentar el envío'); }
    finally { setRetrying(null); }
  };

  if (loading || deliveries.length === 0) return null;
  return <section className="mt-6 rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
    <h2 className="mb-3 text-lg font-semibold text-gray-900 dark:text-gray-100">Notificaciones de salida</h2>
    <ul className="space-y-3">{deliveries.map((delivery) => <li key={delivery.id} className="rounded-lg border p-3 dark:border-gray-700">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><span className="font-medium">{delivery.destination_name}</span><span className="ml-2 text-sm text-gray-500">{STATUS_LABELS[delivery.status] ?? delivery.status}</span></div>{['failed', 'unknown'].includes(delivery.status) && <button type="button" disabled={retrying === delivery.id} onClick={() => { void retry(delivery); }} className="inline-flex items-center gap-1 rounded border px-2 py-1 text-sm text-blue-700 disabled:opacity-50"><RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />{retrying === delivery.id ? 'En cola…' : 'Reintentar'}</button>}</div>
      {delivery.error_summary && <p className="mt-2 text-sm text-red-700">{delivery.error_summary}</p>}
      {delivery.next_attempt_at && <p className="mt-1 text-xs text-gray-500">Próximo intento: {new Date(delivery.next_attempt_at).toLocaleString()}</p>}
      {delivery.attempts.length > 0 && <details className="mt-2 text-xs text-gray-500"><summary className="cursor-pointer">Intentos ({delivery.attempt_count})</summary><ul className="mt-1 space-y-1">{delivery.attempts.map((attempt) => <li key={attempt.attempt_number}>#{attempt.attempt_number} · {STATUS_LABELS[attempt.status] ?? attempt.status}{attempt.http_status ? ` · HTTP ${attempt.http_status}` : ''}{attempt.error_summary ? ` · ${attempt.error_summary}` : ''}</li>)}</ul></details>}
    </li>)}</ul>
  </section>;
}
