// What the services table shows as the Status of a service: derived from a read-only reachability check.

export type ServiceStatusKind = 'checking' | 'connected' | 'unverifiable' | 'token_rejected' | 'unreachable' | 'model_required';

export interface StatusCheck {
  status: 'success' | 'error';
  message: string;
  /** False when the server has no health or model endpoint: it answered, but token and model are not proven. */
  verifiable: boolean;
}

export function serviceStatus(model: string, check: StatusCheck | null | undefined): ServiceStatusKind {
  if (!model.trim()) return 'model_required';
  if (!check) return 'checking';
  if (check.status === 'success') return check.verifiable ? 'connected' : 'unverifiable';
  return /token/i.test(check.message) ? 'token_rejected' : 'unreachable';
}

export const STATUS_LABEL: Record<ServiceStatusKind, string> = {
  checking: 'Checking...',
  connected: 'Connected',
  unverifiable: 'Not verifiable',
  token_rejected: 'Token rejected',
  unreachable: 'Unreachable',
  model_required: 'Model required',
};

export interface AgentRowStatus {
  kind: 'active' | 'inoperative';
  label: string;
  detail?: string;
}

/**
 * Status of an agent in the agents list. Every agent used to read "Active"; a System One agent whose service was
 * deleted cannot evaluate anything, so it says so. Other agent types are untouched.
 */
export function agentRowStatus(agent: { type: string; system_one_service?: unknown }): AgentRowStatus {
  if (agent.type === 'system_one_agent' && !agent.system_one_service) {
    return { kind: 'inoperative', label: 'Inoperative', detail: 'This agent has no System One service: choose one in its settings' };
  }
  return { kind: 'active', label: 'Active' };
}

/** The backend refuses to schedule a System One agent (it evaluates on demand), so the picker must not offer it. */
export function canBeScheduled(agent: { type: string }): boolean {
  return agent.type !== 'system_one_agent';
}
