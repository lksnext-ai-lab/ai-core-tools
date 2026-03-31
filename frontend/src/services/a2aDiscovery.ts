import { apiService } from './api';

export interface AgentSkill {
  id: string;
  name: string;
  description?: string;
  [key: string]: unknown;
}

export interface AgentCard {
  name?: string;
  description?: string;
  skills?: AgentSkill[];
  [key: string]: unknown;
}

export interface A2ADiscoveryResult {
  cardUrl: string;
  remoteAgentId?: string;
  card: AgentCard;
  skills: AgentSkill[];
  documentationUrl?: string | null;
  iconUrl?: string | null;
}

export async function discoverA2ACard(appId: number, rawUrl: string): Promise<A2ADiscoveryResult> {
  const response = await apiService.discoverA2ACard(appId, rawUrl);

  return {
    cardUrl: response.card_url,
    remoteAgentId: response.remote_agent_id,
    card: response.card as AgentCard,
    skills: (response.skills ?? []) as AgentSkill[],
    documentationUrl: response.documentation_url,
    iconUrl: response.icon_url,
  };
}
