import { useMemo } from 'react';
import { MetricsDashboard } from './MetricsDashboard';
import { metricsApi } from '../../services/metrics';

interface AgentMetricsTabProps {
  appId: number;
  agentId: number;
  agentType?: string;
}

export function AgentMetricsTab({ appId, agentId, agentType }: AgentMetricsTabProps) {
  const api = useMemo(() => metricsApi.agent(appId, agentId), [appId, agentId]);
  return <MetricsDashboard api={api} dimensions={['channel', 'model', 'user']} variant={agentType === 'system_one_agent' ? 'system_one' : 'default'} />;
}
