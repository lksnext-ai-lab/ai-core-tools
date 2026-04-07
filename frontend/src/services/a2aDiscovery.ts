import { apiService } from './api';

export type A2AAuthSchemeType = 'none' | 'apiKey' | 'http' | 'oauth2' | 'openIdConnect' | 'mtls';

export interface A2AAgentAuthConfig {
  scheme_name?: string | null;
  scheme_type?: A2AAuthSchemeType;
  api_key?: string;
  bearer_token?: string;
  username?: string;
  password?: string;
  client_certificate?: string;
  client_key?: string;
  ca_certificate?: string;
}

export interface AgentSkill {
  id: string;
  name: string;
  description?: string;
  securityRequirements?: Array<Record<string, string[]>>;
  [key: string]: unknown;
}

export interface AgentCard {
  name?: string;
  description?: string;
  skills?: AgentSkill[];
  securitySchemes?: Record<string, unknown>;
  security?: Array<Record<string, string[]>>;
  [key: string]: unknown;
}

export interface A2AAdvertisedSecurityScheme {
  name: string;
  type: Exclude<A2AAuthSchemeType, 'none'>;
  config: Record<string, unknown>;
  raw: Record<string, unknown>;
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

const SECURITY_SCHEME_WRAPPERS: Record<string, Exclude<A2AAuthSchemeType, 'none'>> = {
  apiKeySecurityScheme: 'apiKey',
  httpAuthSecurityScheme: 'http',
  oauth2SecurityScheme: 'oauth2',
  openIdConnectSecurityScheme: 'openIdConnect',
  mutualTlsSecurityScheme: 'mtls',
  mutualTLSSecurityScheme: 'mtls',
  mtlsSecurityScheme: 'mtls',
};

function normalizeSecurityScheme(
  name: string,
  rawScheme: unknown,
): A2AAdvertisedSecurityScheme | null {
  if (!rawScheme || typeof rawScheme !== 'object' || Array.isArray(rawScheme)) {
    return null;
  }

  const raw = rawScheme as Record<string, unknown>;
  for (const [wrapperName, schemeType] of Object.entries(SECURITY_SCHEME_WRAPPERS)) {
    const nested = raw[wrapperName];
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      return {
        name,
        type: schemeType,
        config: nested as Record<string, unknown>,
        raw,
      };
    }
  }

  let rawType = raw.type;
  if (rawType === 'mutualTLS') {
    rawType = 'mtls';
  }

  if (rawType === 'apiKey' || rawType === 'http' || rawType === 'oauth2' || rawType === 'openIdConnect' || rawType === 'mtls') {
    return {
      name,
      type: rawType,
      config: raw,
      raw,
    };
  }

  return null;
}

export function extractA2ASecuritySchemes(card?: AgentCard | null): A2AAdvertisedSecurityScheme[] {
  const rawSchemes = card?.securitySchemes;
  if (!rawSchemes || typeof rawSchemes !== 'object' || Array.isArray(rawSchemes)) {
    return [];
  }

  return Object.entries(rawSchemes)
    .map(([name, rawScheme]) => normalizeSecurityScheme(name, rawScheme))
    .filter((scheme): scheme is A2AAdvertisedSecurityScheme => Boolean(scheme));
}

export function getEffectiveA2ASecurityRequirements(
  card: AgentCard | null | undefined,
  selectedSkillId?: string,
): Array<Record<string, string[]>> {
  const selectedSkill = card?.skills?.find((skill) => skill.id === selectedSkillId);
  const skillRequirements = selectedSkill?.securityRequirements;
  if (Array.isArray(skillRequirements) && skillRequirements.length > 0) {
    return skillRequirements;
  }

  return Array.isArray(card?.security) ? card.security : [];
}
