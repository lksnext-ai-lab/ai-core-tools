import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiService, type MarketplaceScheduledTask } from '../services/api';
import { ScheduledTaskOutputView, type ScheduledTaskOutputSource } from '../components/scheduled-tasks/ScheduledTaskOutputView';

/** Marketplace: read-only result of a run (/runs/:runId) or of a continuous conversation (/conversation). */
export default function MarketplaceScheduledTaskRunPage() {
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
      title={task?.name ?? 'Tarea programada'}
      subtitle={numericRunId === null ? 'Respuestas de la conversación continua' : 'Resultado de la ejecución'}
      backHref={`/marketplace/scheduled-tasks/${taskId}`}
      backLabel="Volver a la tarea"
      source={source}
      timeline={numericRunId === null}
    />
  );
}
