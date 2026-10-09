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
  // A System One agent calls an LLM only to summarize long texts: that is what its "calls" are.
  const callsLabel = agentType === 'system_one_agent' ? 'summarization calls' : undefined;
  return <MetricsDashboard api={api} dimensions={['channel', 'model', 'user']} callsLabel={callsLabel} />;
}
