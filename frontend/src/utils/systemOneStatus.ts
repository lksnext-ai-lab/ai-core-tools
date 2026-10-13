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
