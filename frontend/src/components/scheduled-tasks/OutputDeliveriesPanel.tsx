import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { apiService, type OutputDelivery } from '../../services/api';
import CardApp from '../ui/CardApp';
import ButtonApp from '../ui/ButtonApp';
import Alert from '../ui/Alert';
import ExpansionDetails from '../ui/ExpansionDetails';

interface Props { appId: number; taskId: number; runId: number; }

const STATUS_TRANSLATION_KEYS: Record<string, string> = {
  pending: 'scheduledTaskDetailPage.results.outputDeliveries.status.pending',
  sending: 'scheduledTaskDetailPage.results.outputDeliveries.status.sending',
  retry_wait: 'scheduledTaskDetailPage.results.outputDeliveries.status.retryWait',
  accepted: 'scheduledTaskDetailPage.results.outputDeliveries.status.accepted',
  delivered: 'scheduledTaskDetailPage.results.outputDeliveries.status.delivered',
  failed: 'scheduledTaskDetailPage.results.outputDeliveries.status.failed',
  unknown: 'scheduledTaskDetailPage.results.outputDeliveries.status.unknown',
  cancelled: 'scheduledTaskDetailPage.results.outputDeliveries.status.cancelled',
};

export function OutputDeliveriesPanel({ appId, taskId, runId }: Readonly<Props>) {
  const { t } = useTranslation('common');
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
    if (delivery.status === 'unknown' && !globalThis.confirm(t('scheduledTaskDetailPage.results.outputDeliveries.confirmUnknownRetry'))) return;
    setRetrying(delivery.id);
    try {
      await apiService.retryScheduledTaskDelivery(appId, taskId, runId, delivery.id);
      toast.success(t('scheduledTaskDetailPage.results.outputDeliveries.retryQueued'));
      await load();
    } catch (error) { toast.error(error instanceof Error ? error.message : t('scheduledTaskDetailPage.results.outputDeliveries.retryFailed')); }
    finally { setRetrying(null); }
  };

  if (loading || deliveries.length === 0) return null;
  return <CardApp className="mt-6 p-6 " titulo={t('scheduledTaskDetailPage.results.outputDeliveries.title')}>
    <ul className="space-y-3">{deliveries.map((delivery) => <li key={delivery.id} className="rounded-md border border-line p-3 dark:border-line-dark">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="font-medium">{delivery.destination_name}</span>
          <span className="ml-2 text-sm text-fg-secondary dark:text-fg-secondary-dark">{STATUS_TRANSLATION_KEYS[delivery.status] ? t(STATUS_TRANSLATION_KEYS[delivery.status]) : delivery.status}</span>
        </div>
        {['failed', 'unknown'].includes(delivery.status) && 
          <ButtonApp
            label={retrying === delivery.id ? t('scheduledTaskDetailPage.results.outputDeliveries.retrying') : t('scheduledTaskDetailPage.results.outputDeliveries.retry')}
            variant="primary"
            size="small"
            icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
            loading={retrying === delivery.id}
            onClick={() => { void retry(delivery); }}
          />
        }
      </div>
      {delivery.error_summary && <Alert type="error" className="mt-2" message={<span className="whitespace-pre-wrap break-words">{delivery.error_summary}</span>} />}
      {delivery.next_attempt_at && (
        <Alert
          type="info"
          className="mt-1"
          message={`${t('scheduledTaskDetailPage.results.outputDeliveries.nextAttempt')}: ${new Date(delivery.next_attempt_at).toLocaleString()}`}
        />
      )}
      {delivery.attempts.length > 0 && (
        <ExpansionDetails
          header={t('scheduledTaskDetailPage.results.outputDeliveries.attempts', { count: delivery.attempt_count })}
          defaultOpen={false}
        >
          <ul className="space-y-1 break-words text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {delivery.attempts.map((attempt) => (
              <li key={attempt.attempt_number}>
                #{attempt.attempt_number} · {STATUS_TRANSLATION_KEYS[attempt.status] ? t(STATUS_TRANSLATION_KEYS[attempt.status]) : attempt.status}
                {attempt.http_status ? ` · HTTP ${attempt.http_status}` : ''}
                {attempt.error_summary ? ` · ${attempt.error_summary}` : ''}
              </li>
            ))}
          </ul>
        </ExpansionDetails>
      )}
    </li>)}</ul>
  </CardApp>;
}
