import i18n from '../i18n';

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

/** Read lazily (getters) so the label follows the current language. */
export const STATUS_LABEL: Record<ServiceStatusKind, string> = {
  get checking() { return i18n.t('systemOne.status.checking'); },
  get connected() { return i18n.t('systemOne.status.connected'); },
  get unverifiable() { return i18n.t('systemOne.status.unverifiable'); },
  get token_rejected() { return i18n.t('systemOne.status.tokenRejected'); },
  get unreachable() { return i18n.t('systemOne.status.unreachable'); },
  get model_required() { return i18n.t('systemOne.status.modelRequired'); },
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
    return { kind: 'inoperative', label: i18n.t('systemOne.agentStatus.inoperative'), detail: i18n.t('systemOne.agentStatus.inoperativeDetail') };
  }
  return { kind: 'active', label: i18n.t('agentsPage.active') };
}

/** The backend refuses to schedule a System One agent (it evaluates on demand), so the picker must not offer it. */
export function canBeScheduled(agent: { type: string }): boolean {
  return agent.type !== 'system_one_agent';
}
