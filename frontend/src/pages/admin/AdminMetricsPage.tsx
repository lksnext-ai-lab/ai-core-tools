import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { MetricsDashboard } from '../../components/metrics/MetricsDashboard';
import { metricsApi } from '../../services/metrics';

function AdminMetricsPage() {
  const { t } = useTranslation('common');
  const api = useMemo(() => metricsApi.system(), []);
  return (
    <div className="p-6">
      <MetricsDashboard
        api={api}
        dimensions={['app', 'agent', 'model', 'provider', 'channel']}
        title={t('metricsDashboard.platformTitle')}
        description={t('metricsDashboard.platformDescription')}
        systemScope
      />
    </div>
  );
}

export default AdminMetricsPage;
