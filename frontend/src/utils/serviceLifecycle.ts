import type { LifecycleStatus } from '../types/services';

/**
 * End-of-service helpers and centralised strings (NFR-6: no hardcoded copy in components).
 * Lifecycle status is computed by the backend (D-9) — only dates are handled here.
 * Dates are calendar days stored as 00:00 UTC (D-1), so every conversion uses UTC.
 */

/** Date only, user locale, UTC so the picked calendar day never shifts. */
export function formatEndOfServiceDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { timeZone: 'UTC' });
}

/** ISO datetime -> `YYYY-MM-DD` (UTC) for `<input type="date">`. Empty string when unset. */
export function dateInputValueFromIso(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toISOString().slice(0, 10);
}

/** `YYYY-MM-DD` -> `YYYY-MM-DDT00:00:00Z`, or null when empty. */
export function isoFromDateInput(value: string): string | null {
  return value ? `${value}T00:00:00Z` : null;
}

/** Minimal shape of a service offered in a selection dropdown (AI, embedding or sandbox). */
export interface ServiceOptionLike {
  readonly service_id: number;
  readonly name: string;
  readonly lifecycle_status?: LifecycleStatus;
  readonly end_of_service_at?: string | null;
  readonly deprecation_notice?: string | null;
}

/**
 * D-4: retired services are not offered for new selection. A retired service stays in the list only
 * when it is the field's saved value (`currentValue` must come from the loaded entity, not the form).
 */
export function selectableServiceOptions<T extends ServiceOptionLike>(
  options: readonly T[] | null | undefined,
  currentValue: number | null | undefined,
): T[] {
  return (options ?? []).filter(
    (o) => o.lifecycle_status !== 'retired' || (currentValue != null && o.service_id === currentValue),
  );
}

/** Option text: `label` (default the service name) plus "(retired)" / "(ends <date>)" when applicable. */
export function serviceOptionLabel(option: ServiceOptionLike, label: string = option.name): string {
  if (option.lifecycle_status === 'retired') {
    return `${label} ${SERVICE_LIFECYCLE_STRINGS.optionRetired}`;
  }
  if (option.lifecycle_status === 'deprecated' && option.end_of_service_at) {
    return `${label} ${SERVICE_LIFECYCLE_STRINGS.optionEnds(formatEndOfServiceDate(option.end_of_service_at))}`;
  }
  return label;
}

/** True when the picked day is today or earlier (UTC), i.e. saving retires the service now. */
export function isDateInputRetiredNow(value: string): boolean {
  if (!value) return false;
  const todayUtc = new Date().toISOString().slice(0, 10);
  return value <= todayUtc;
}

export const SERVICE_LIFECYCLE_STRINGS = {
  optionRetired: '(retired)',
  optionEnds: (date: string) => `(ends ${date})`,
  optionStatusRetired: (date: string | null) =>
    date ? `This service was retired on ${date}. Choose another one to save a change here.` : 'This service is retired. Choose another one to save a change here.',
  optionStatusDeprecated: (date: string | null) =>
    date ? `This service is deprecated and ends on ${date}.` : 'This service is deprecated.',
  retired: 'Retired',
  retiredOn: (date: string) => `Retired on ${date}`,
  deprecatedNoDate: 'Deprecated',
  deprecated: (date: string) => `Deprecated – ends ${date}`,
  endOfServiceLabel: 'End of service',
  endOfServiceHelp:
    'From this date the service stops working. Deprecated warnings start before it.',
  autoMoveLabel: 'Move agents to another AI service',
  autoMoveHelp:
    'On this date, agents using this service as their main LLM will be moved automatically to the selected service.',
  autoMoveTargetHelp: 'The target must remain active after this service ends.',
  autoMoveTargetUnavailable: (date: string) => `(ends on or before ${date})`,
  noAutoMove: 'Do not move agents automatically',
  noAutoMoveTargets: 'No eligible AI services are available.',
  clearDate: 'Clear',
  clearDateAria: 'Clear end of service date',
  deprecationNoticeLabel: 'Deprecation notice',
  deprecationNoticeHelp: 'Shown next to the service to explain the change. Optional.',
  noticeCounter: (used: number, max: number) => `${used}/${max}`,
  retireImmediately: 'Saving with this date retires the service immediately.',
  embeddingWarning: (date: string) =>
    `Retiring this embedding service makes the silo unusable. Re-index it into another embedding service before ${date}.`,
  aiWarning: (date: string) =>
    `Agents using this AI service stop working on ${date}. Move them to another AI service before then.`,
} as const;

export const SERVICE_WARNING_STRINGS = {
  titleRetired: 'Retired services in use',
  titleDeprecated: 'Deprecated services in use',
  retiredStatus: (date: string) => `Retired on ${date}`,
  deprecatedStatus: (date: string) => `Deprecated, ends ${date}`,
  roles: {
    llm: 'LLM',
    ocr_vision: 'OCR vision',
    transcription: 'Transcription',
    video: 'Video',
    media_embedding: 'Media embedding',
    embedding: 'Embedding',
    sandbox: 'Code interpreter sandbox',
    sandbox_app_default: 'Code interpreter sandbox (app default)',
  },
  silo_embedding: (via: string) => `Embedding (via silo ${via})`,
  middleware: (via: string) => `Middleware ${via}`,
  sandboxWarning: (date: string) =>
    `The code interpreter stops working on ${date}. Select another sandbox service before then.`,
  compactRetired: (n: number) => `Retired ${n === 1 ? 'service' : 'services'} (${n})`,
  compactDeprecated: (n: number) => `Deprecated ${n === 1 ? 'service' : 'services'} (${n})`,
  compactAria: (items: string) => `Service lifecycle: ${items}`,
} as const;

export const SERVICE_USAGE_STRINGS = {
  action: 'Used by',
  title: (name: string) => `Used by: ${name}`,
  loading: 'Loading usage...',
  loadError: 'Could not load what uses this service.',
  retry: 'Retry',
  close: 'Close',
  nothing: 'Nothing uses this service.',
  empty: 'None',
  sections: {
    agents: 'Agents',
    appsDefault: 'Apps using it as default',
    silos: 'Silos',
    repositories: 'Repositories',
    middlewares: 'Middlewares',
    scheduledTasks: 'Scheduled tasks',
  },
  appLabel: (name: string) => `App: ${name}`,
  agentRoles: {
    llm: 'LLM',
    ocr_vision: 'OCR vision',
    transcription: 'Transcription',
    video: 'Video',
    media_embedding: 'Media embedding',
    silo_embedding: 'Via silo',
    sandbox: 'Sandbox',
    sandbox_app_default: 'Sandbox (app default)',
  },
  siloRoles: {
    embedding: 'Embedding',
    transcription: 'Transcription',
    video: 'Video',
  },
  reindexWarning:
    'Retiring this embedding service makes the silos listed here unusable. Re-index each silo into another embedding service before the end-of-service date.',
  moveTitle: 'Move agents to another AI service',
  moveCount: (n: number) => `${n} ${n === 1 ? 'agent uses' : 'agents use'} this service as their main LLM`,
  moveNone: 'No agents use this service as their main LLM.',
  moveTargetLabel: 'Target AI service',
  moveTargetPlaceholder: 'Select a service...',
  moveTargetEnds: (name: string, date: string) => `${name} (ends ${date})`,
  moveNoTargets: 'There is no other available AI service to move the agents to.',
  moveButton: 'Move agents...',
  moveConfirm: (n: number, from: string, to: string) =>
    `Move ${n} ${n === 1 ? 'agent' : 'agents'} from ${from} to ${to}?`,
  moveConfirmButton: 'Confirm move',
  moveConfirming: 'Moving...',
  moveCancel: 'Cancel',
  moveSuccess: (n: number) => `Moved ${n} ${n === 1 ? 'agent' : 'agents'}`,
  moveCountChanged: (n: number) =>
    `The number of agents changed (now ${n}). Review the list and confirm again.`,
  moveNote:
    'Transcription, video, OCR vision and middleware references are not moved. They are listed above and must be changed manually.',
  moveError: 'Could not move the agents.',
  moveSandboxTitle: 'Move usage to another sandbox service',
  targetsLoading: 'Loading available services...',
  targetsLoadError: 'Could not load available services.',
  moveSandboxSummary: (agents: number, apps: number) =>
    agents === 0 && apps === 0
      ? 'No agents or app defaults use this service.'
      : [
          agents > 0 && `${agents} ${agents === 1 ? 'agent is' : 'agents are'} directly assigned to it`,
          apps > 0 && `${apps} ${apps === 1 ? 'app uses' : 'apps use'} it as the default sandbox`,
        ].filter(Boolean).join('; ') + '.',
  moveSandboxTargetLabel: 'Target sandbox service',
  moveSandboxNoTargets: 'There is no other available sandbox service to move this usage to.',
  moveSandboxButton: 'Move sandbox usage...',
  moveSandboxConfirm: (
    agents: number,
    apps: number,
    inherited: number,
    from: string,
    to: string,
  ) => {
    const changes = [
      `${agents} directly assigned ${agents === 1 ? 'agent' : 'agents'}`,
      apps > 0 ? 'the app default sandbox' : 'no app default',
    ];
    const inheritNote = apps > 0
      ? ` ${inherited} ${inherited === 1 ? 'agent that inherits' : 'agents that inherit'} the app default will also switch to ${to}.`
      : '';
    return `Move ${changes.join(' and ')} from ${from} to ${to}?${inheritNote}`;
  },
  moveSandboxSuccess: (agents: number, apps: number) => [
    agents > 0 && `Moved ${agents} ${agents === 1 ? 'agent' : 'agents'}`,
    apps > 0 && `changed the default sandbox in ${apps} ${apps === 1 ? 'app' : 'apps'}`,
  ].filter(Boolean).join(' and ') + '.',
  moveSandboxNote:
    'Agents inheriting the app default will follow the new default automatically.',
  deleteReview:
    'Review what uses this service below. You can move eligible agents to another service before deleting it.',
  deleteButton: 'Delete service...',
  deleting: 'Deleting...',
} as const;

export const MAX_DEPRECATION_NOTICE_LENGTH = 1000;
