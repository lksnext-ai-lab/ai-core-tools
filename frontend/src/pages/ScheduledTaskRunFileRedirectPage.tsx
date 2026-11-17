import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiService } from '../services/api';
import { CardApp } from '../components/ui/CardApp';

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
  return <CardApp className="p-8 text-center text-fg dark:text-fg-dark ">{error || 'Abriendo archivo…'}</CardApp>;
}
