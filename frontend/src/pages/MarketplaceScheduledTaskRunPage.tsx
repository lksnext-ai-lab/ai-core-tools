import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { apiService, type MarketplaceScheduledTask } from '../services/api';
import { ScheduledTaskOutputView, type ScheduledTaskOutputSource } from '../components/scheduled-tasks/ScheduledTaskOutputView';

/** Marketplace: read-only result of a run (/runs/:runId) or of a continuous conversation (/conversation). */
export default function MarketplaceScheduledTaskRunPage() {
  const { t } = useTranslation('common');
  const { taskId, runId } = useParams();
  const numericTaskId = Number.parseInt(taskId ?? '0', 10);
  const numericRunId = runId ? Number.parseInt(runId, 10) : null;
  const [task, setTask] = useState<MarketplaceScheduledTask | null>(null);

  useEffect(() => {
    apiService.getMarketplaceScheduledTask(numericTaskId).then(setTask).catch(() => setTask(null));
  }, [numericTaskId]);

  const source = useMemo<ScheduledTaskOutputSource>(() => ({
    load: async () => numericRunId === null
      ? (await apiService.getMarketplaceScheduledTaskRuns(numericTaskId, 1, 200)).items
      : [await apiService.getMarketplaceScheduledTaskRun(numericTaskId, numericRunId)],
    resolveFileUrl: (run, fileId) => apiService.getMarketplaceScheduledTaskRunFileUrl(numericTaskId, run, fileId),
  }), [numericTaskId, numericRunId]);

  return (
    <ScheduledTaskOutputView
      title={task?.name ?? t('scheduledTaskDetailPage.results.taskFallback')}
      subtitle={numericRunId === null ? t('scheduledTaskDetailPage.results.conversationSubtitle') : t('scheduledTaskDetailPage.results.runSubtitle')}
      backHref={`/marketplace/scheduled-tasks/${taskId}`}
      backLabel={t('scheduledTaskDetailPage.results.backToTask')}
      source={source}
      timeline={numericRunId === null}
    />
  );
}
