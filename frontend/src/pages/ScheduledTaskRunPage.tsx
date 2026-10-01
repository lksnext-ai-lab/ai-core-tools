import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiService, type ScheduledTask } from '../services/api';
import { ScheduledTaskOutputView, type ScheduledTaskOutputSource } from '../components/scheduled-tasks/ScheduledTaskOutputView';

/** Read-only result of a run (/runs/:runId) or of a continuous conversation (/conversation). */
export default function ScheduledTaskRunPage() {
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
    <ScheduledTaskOutputView
      title={task?.name ?? 'Tarea programada'}
      subtitle={numericRunId === null ? 'Respuestas de la conversación continua' : 'Resultado de la ejecución'}
      backHref={`/apps/${appId}/scheduled-tasks/${taskId}`}
      backLabel="Volver a la tarea"
      source={source}
      timeline={numericRunId === null}
    />
  );
}
