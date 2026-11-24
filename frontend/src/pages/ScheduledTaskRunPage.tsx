import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { apiService, type ScheduledTask } from '../services/api';
import { ScheduledTaskOutputView, type ScheduledTaskOutputSource } from '../components/scheduled-tasks/ScheduledTaskOutputView';
import { OutputDeliveriesPanel } from '../components/scheduled-tasks/OutputDeliveriesPanel';

/** Read-only result of a run (/runs/:runId) or of a continuous conversation (/conversation). */
export default function ScheduledTaskRunPage() {
  const { t } = useTranslation('common');
  const { appId, taskId, runId } = useParams();
  const numericAppId = Number.parseInt(appId ?? '0', 10);
  const numericTaskId = Number.parseInt(taskId ?? '0', 10);
  const numericRunId = runId ? Number.parseInt(runId, 10) : null;
  const [task, setTask] = useState<ScheduledTask | null>(null);

  useEffect(() => {
    apiService.getScheduledTask(numericAppId, numericTaskId).then(setTask).catch(() => setTask(null));
  }, [numericAppId, numericTaskId]);

  const source = useMemo<ScheduledTaskOutputSource>(() => ({
    load: async () => numericRunId === null
      ? (await apiService.getScheduledTaskRuns(numericAppId, numericTaskId, 1, 200)).items
      : [await apiService.getScheduledTaskRun(numericAppId, numericTaskId, numericRunId)],
    resolveFileUrl: (run, fileId) => apiService.getScheduledTaskRunFileUrl(numericAppId, numericTaskId, run, fileId),
  }), [numericAppId, numericTaskId, numericRunId]);

  return (
    <>
    <ScheduledTaskOutputView
      title={task?.name ?? t('scheduledTaskDetailPage.results.taskFallback')}
      subtitle={numericRunId === null ? t('scheduledTaskDetailPage.results.conversationSubtitle') : t('scheduledTaskDetailPage.results.runSubtitle')}
      backHref={`/apps/${appId}/scheduled-tasks/${taskId}`}
      backLabel={t('scheduledTaskDetailPage.results.backToTask')}
      source={source}
      timeline={numericRunId === null}
    />
    {numericRunId !== null && <OutputDeliveriesPanel appId={numericAppId} taskId={numericTaskId} runId={numericRunId} />}
    </>
  );
}
