import { apiService } from './api';
import type {
  TimeRange,
  AppSummaryResponse,
  AppExecutionsResponse,
  AppAgentsResponse,
  AppModelsResponse,
  AppUsersResponse,
  AgentSummaryResponse,
  AgentExecutionsResponse,
  AgentTokensResponse,
  AgentErrorsResponse,
  AgentLatencyResponse,
  AgentToolsResponse,
  AgentUsersResponse,
} from '../types/metrics';

const appBase = (appId: number) => `/internal/apps/${appId}/metrics`;
const agentBase = (appId: number, agentId: number) =>
  `/internal/apps/${appId}/agents/${agentId}/metrics`;

export const metricsApi = {
  // App-level
  appSummary: (appId: number, range: TimeRange): Promise<AppSummaryResponse> =>
    apiService.request(`${appBase(appId)}/summary?range=${range}`),

  appExecutions: (
    appId: number,
    range: TimeRange,
    callerType?: string,
  ): Promise<AppExecutionsResponse> => {
    const qs = callerType
      ? `?range=${range}&caller_type=${callerType}`
      : `?range=${range}`;
    return apiService.request(`${appBase(appId)}/executions${qs}`);
  },

  appAgents: (appId: number, range: TimeRange): Promise<AppAgentsResponse> =>
    apiService.request(`${appBase(appId)}/agents?range=${range}`),

  appModels: (appId: number, range: TimeRange): Promise<AppModelsResponse> =>
    apiService.request(`${appBase(appId)}/models?range=${range}`),

  appUsers: (appId: number, range: TimeRange): Promise<AppUsersResponse> =>
    apiService.request(`${appBase(appId)}/users?range=${range}`),

  // Per-agent
  agentSummary: (
    appId: number,
    agentId: number,
    range: TimeRange,
  ): Promise<AgentSummaryResponse> =>
    apiService.request(`${agentBase(appId, agentId)}/summary?range=${range}`),

  agentExecutions: (
    appId: number,
    agentId: number,
    range: TimeRange,
  ): Promise<AgentExecutionsResponse> =>
    apiService.request(`${agentBase(appId, agentId)}/executions?range=${range}`),

  agentTokens: (
    appId: number,
    agentId: number,
    range: TimeRange,
  ): Promise<AgentTokensResponse> =>
    apiService.request(`${agentBase(appId, agentId)}/tokens?range=${range}`),

  agentErrors: (
    appId: number,
    agentId: number,
    range: TimeRange,
  ): Promise<AgentErrorsResponse> =>
    apiService.request(`${agentBase(appId, agentId)}/errors?range=${range}`),

  agentLatency: (
    appId: number,
    agentId: number,
    range: TimeRange,
  ): Promise<AgentLatencyResponse> =>
    apiService.request(`${agentBase(appId, agentId)}/latency?range=${range}`),

  agentTools: (
    appId: number,
    agentId: number,
    range: TimeRange,
  ): Promise<AgentToolsResponse> =>
    apiService.request(`${agentBase(appId, agentId)}/tools?range=${range}`),

  agentUsers: (
    appId: number,
    agentId: number,
    range: TimeRange,
  ): Promise<AgentUsersResponse> =>
    apiService.request(`${agentBase(appId, agentId)}/users?range=${range}`),
};
