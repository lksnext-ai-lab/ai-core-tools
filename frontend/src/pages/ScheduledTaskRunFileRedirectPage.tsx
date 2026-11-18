import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiService } from '../services/api';

export default function ScheduledTaskRunFileRedirectPage() {
  const { appId, taskId, runId, fileId } = useParams();
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    apiService.getScheduledTaskRunFileUrl(Number(appId), Number(taskId), Number(runId), fileId ?? '')
      .then((url) => { if (active) globalThis.location.replace(url); })
      .catch(() => { if (active) setError('Este archivo ya no está disponible o no tienes acceso.'); });
    return () => { active = false; };
  }, [appId, taskId, runId, fileId]);
  return <div className="rounded-xl bg-white p-8 text-center text-gray-600 dark:bg-gray-800">{error || 'Abriendo archivo…'}</div>;
}
