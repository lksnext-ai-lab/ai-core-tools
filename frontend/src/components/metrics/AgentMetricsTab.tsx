import { useMemo } from 'react';
import { MetricsDashboard } from './MetricsDashboard';
import { metricsApi } from '../../services/metrics';

interface AgentMetricsTabProps {
  appId: number;
  agentId: number;
}

export function AgentMetricsTab({ appId, agentId }: AgentMetricsTabProps) {
  const api = useMemo(() => metricsApi.agent(appId, agentId), [appId, agentId]);
  return <MetricsDashboard api={api} dimensions={['channel', 'model', 'user']} />;
}
