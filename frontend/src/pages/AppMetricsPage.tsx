import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { MetricsDashboard } from '../components/metrics/MetricsDashboard';
import { metricsApi } from '../services/metrics';

function AppMetricsPage() {
  const { appId } = useParams<{ appId: string }>();
  const api = useMemo(() => metricsApi.app(Number(appId)), [appId]);
  return (
    <div className="p-6">
      <MetricsDashboard
        api={api}
        dimensions={['agent', 'model', 'channel', 'user', 'provider']}
        title="Metrics"
        description="Usage, performance and reliability of this app's agents."
      />
    </div>
  );
}

export default AppMetricsPage;
