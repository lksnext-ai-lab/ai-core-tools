import { useMemo } from 'react';
import { MetricsDashboard } from '../../components/metrics/MetricsDashboard';
import { metricsApi } from '../../services/metrics';

function AdminMetricsPage() {
  const api = useMemo(() => metricsApi.system(), []);
  return (
    <div className="p-6">
      <MetricsDashboard
        api={api}
        dimensions={['app', 'agent', 'model', 'provider', 'channel']}
        title="Platform metrics"
        description="Agent usage, performance and reliability across every app."
        systemScope
      />
    </div>
  );
}

export default AdminMetricsPage;
