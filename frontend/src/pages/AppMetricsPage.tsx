import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MetricsDashboard } from '../components/metrics/MetricsDashboard';
import { metricsApi } from '../services/metrics';

function AppMetricsPage() {
  const { t } = useTranslation('common');
  const { appId } = useParams<{ appId: string }>();
  const api = useMemo(() => metricsApi.app(Number(appId)), [appId]);
  return (
    <div className="p-6">
      <MetricsDashboard
        api={api}
        dimensions={['agent', 'model', 'channel', 'user', 'provider']}
        title={t('metricsDashboard.appTitle')}
        description={t('metricsDashboard.appDescription')}
      />
    </div>
  );
}

export default AppMetricsPage;
