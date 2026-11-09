import type { LifecycleStatus } from '../types/services';
import i18n from '../i18n';

/**
 * End-of-service helpers and centralised strings (NFR-6: no hardcoded copy in components).
 * Lifecycle status is computed by the backend (D-9) — only dates are handled here.
 * Dates are calendar days stored as 00:00 UTC (D-1), so every conversion uses UTC.
 */

/** Date only, user locale, UTC so the picked calendar day never shifts. */
export function formatEndOfServiceDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(i18n.resolvedLanguage, { timeZone: 'UTC' });
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
  get optionRetired() { return i18n.t('serviceLifecycle.optionRetired'); },
  optionEnds: (date: string) => i18n.t('serviceLifecycle.optionEnds', { date }),
  optionStatusRetired: (date: string | null) => date
    ? i18n.t('serviceLifecycle.optionStatusRetiredWithDate', { date })
    : i18n.t('serviceLifecycle.optionStatusRetired'),
  optionStatusDeprecated: (date: string | null) => date
    ? i18n.t('serviceLifecycle.optionStatusDeprecatedWithDate', { date })
    : i18n.t('serviceLifecycle.optionStatusDeprecated'),
  get retired() { return i18n.t('serviceLifecycle.retired'); },
  retiredOn: (date: string) => i18n.t('serviceLifecycle.retiredOn', { date }),
  get deprecatedNoDate() { return i18n.t('serviceLifecycle.deprecatedNoDate'); },
  deprecated: (date: string) => i18n.t('serviceLifecycle.deprecated', { date }),
  get endOfServiceLabel() { return i18n.t('serviceLifecycle.endOfServiceLabel'); },
  get endOfServiceHelp() { return i18n.t('serviceLifecycle.endOfServiceHelp'); },
  get clearDate() { return i18n.t('serviceLifecycle.clearDate'); },
  get clearDateAria() { return i18n.t('serviceLifecycle.clearDateAria'); },
  get deprecationNoticeLabel() { return i18n.t('serviceLifecycle.deprecationNoticeLabel'); },
  get deprecationNoticeHelp() { return i18n.t('serviceLifecycle.deprecationNoticeHelp'); },
  noticeCounter: (used: number, max: number) => i18n.t('serviceLifecycle.noticeCounter', { used, max }),
  get retireImmediately() { return i18n.t('serviceLifecycle.retireImmediately'); },
  embeddingWarning: (date: string) => i18n.t('serviceLifecycle.embeddingWarning', { date }),
  aiWarning: (date: string) => i18n.t('serviceLifecycle.aiWarning', { date }),
} as const;

export const SERVICE_WARNING_STRINGS = {
  get titleRetired() { return i18n.t('serviceWarnings.titleRetired'); },
  get titleDeprecated() { return i18n.t('serviceWarnings.titleDeprecated'); },
  retiredStatus: (date: string) => i18n.t('serviceWarnings.retiredStatus', { date }),
  deprecatedStatus: (date: string) => i18n.t('serviceWarnings.deprecatedStatus', { date }),
  roles: {
    get llm() { return i18n.t('serviceWarnings.roles.llm'); },
    get ocr_vision() { return i18n.t('serviceWarnings.roles.ocr_vision'); },
    get transcription() { return i18n.t('serviceWarnings.roles.transcription'); },
    get video() { return i18n.t('serviceWarnings.roles.video'); },
    get media_embedding() { return i18n.t('serviceWarnings.roles.media_embedding'); },
    get embedding() { return i18n.t('serviceWarnings.roles.embedding'); },
    get sandbox() { return i18n.t('serviceWarnings.roles.sandbox'); },
    get sandbox_app_default() { return i18n.t('serviceWarnings.roles.sandbox_app_default'); },
  },
  silo_embedding: (via: string) => i18n.t('serviceWarnings.siloEmbedding', { via }),
  middleware: (via: string) => i18n.t('serviceWarnings.middleware', { via }),
  sandboxWarning: (date: string) => i18n.t('serviceWarnings.sandboxWarning', { date }),
  compactRetired: (count: number) => i18n.t('serviceWarnings.compactRetired', { count }),
  compactDeprecated: (count: number) => i18n.t('serviceWarnings.compactDeprecated', { count }),
  compactAria: (items: string) => i18n.t('serviceWarnings.compactAria', { items }),
} as const;

export const SERVICE_USAGE_STRINGS = {
  get action() { return i18n.t('serviceUsage.action'); },
  title: (name: string) => i18n.t('serviceUsage.title', { name }),
  get loading() { return i18n.t('serviceUsage.loading'); },
  get loadError() { return i18n.t('serviceUsage.loadError'); },
  get retry() { return i18n.t('serviceUsage.retry'); },
  get close() { return i18n.t('serviceUsage.close'); },
  get nothing() { return i18n.t('serviceUsage.nothing'); },
  get empty() { return i18n.t('serviceUsage.empty'); },
  sections: {
    get agents() { return i18n.t('serviceUsage.sections.agents'); },
    get appsDefault() { return i18n.t('serviceUsage.sections.appsDefault'); },
    get silos() { return i18n.t('serviceUsage.sections.silos'); },
    get repositories() { return i18n.t('serviceUsage.sections.repositories'); },
    get middlewares() { return i18n.t('serviceUsage.sections.middlewares'); },
    get scheduledTasks() { return i18n.t('serviceUsage.sections.scheduledTasks'); },
  },
  appLabel: (name: string) => i18n.t('serviceUsage.appLabel', { name }),
  agentRoles: {
    get llm() { return i18n.t('serviceUsage.agentRoles.llm'); },
    get ocr_vision() { return i18n.t('serviceUsage.agentRoles.ocr_vision'); },
    get transcription() { return i18n.t('serviceUsage.agentRoles.transcription'); },
    get video() { return i18n.t('serviceUsage.agentRoles.video'); },
    get media_embedding() { return i18n.t('serviceUsage.agentRoles.media_embedding'); },
    get silo_embedding() { return i18n.t('serviceUsage.agentRoles.silo_embedding'); },
    get sandbox() { return i18n.t('serviceUsage.agentRoles.sandbox'); },
    get sandbox_app_default() { return i18n.t('serviceUsage.agentRoles.sandbox_app_default'); },
  },
  siloRoles: {
    get embedding() { return i18n.t('serviceUsage.siloRoles.embedding'); },
    get transcription() { return i18n.t('serviceUsage.siloRoles.transcription'); },
    get video() { return i18n.t('serviceUsage.siloRoles.video'); },
  },
  get reindexWarning() { return i18n.t('serviceUsage.reindexWarning'); },
  get moveTitle() { return i18n.t('serviceUsage.moveTitle'); },
  moveCount: (count: number) => i18n.t('serviceUsage.moveCount', { count }),
  get moveNone() { return i18n.t('serviceUsage.moveNone'); },
  get moveTargetLabel() { return i18n.t('serviceUsage.moveTargetLabel'); },
  get moveTargetPlaceholder() { return i18n.t('serviceUsage.moveTargetPlaceholder'); },
  moveTargetEnds: (name: string, date: string) => i18n.t('serviceUsage.moveTargetEnds', { name, date }),
  get moveNoTargets() { return i18n.t('serviceUsage.moveNoTargets'); },
  get moveButton() { return i18n.t('serviceUsage.moveButton'); },
  moveConfirm: (count: number, from: string, to: string) => i18n.t('serviceUsage.moveConfirm', { count, from, to }),
  get moveConfirmButton() { return i18n.t('serviceUsage.moveConfirmButton'); },
  get moveConfirming() { return i18n.t('serviceUsage.moveConfirming'); },
  get moveCancel() { return i18n.t('serviceUsage.moveCancel'); },
  moveSuccess: (count: number) => i18n.t('serviceUsage.moveSuccess', { count }),
  moveCountChanged: (count: number) => i18n.t('serviceUsage.moveCountChanged', { count }),
  get moveNote() { return i18n.t('serviceUsage.moveNote'); },
  get moveError() { return i18n.t('serviceUsage.moveError'); },
  get moveSandboxTitle() { return i18n.t('serviceUsage.moveSandboxTitle'); },
  get targetsLoading() { return i18n.t('serviceUsage.targetsLoading'); },
  get targetsLoadError() { return i18n.t('serviceUsage.targetsLoadError'); },
  moveSandboxSummary: (agents: number, apps: number) => {
    if (agents === 0 && apps === 0) return i18n.t('serviceUsage.moveSandboxSummaryNone');
    const parts = [
      agents > 0 && i18n.t('serviceUsage.moveSandboxSummaryAgents', { count: agents }),
      apps > 0 && i18n.t('serviceUsage.moveSandboxSummaryApps', { count: apps }),
    ].filter(Boolean);
    return `${parts.join('; ')}.`;
  },
  get moveSandboxTargetLabel() { return i18n.t('serviceUsage.moveSandboxTargetLabel'); },
  get moveSandboxNoTargets() { return i18n.t('serviceUsage.moveSandboxNoTargets'); },
  get moveSandboxButton() { return i18n.t('serviceUsage.moveSandboxButton'); },
  moveSandboxConfirm: (
    agents: number,
    apps: number,
    inherited: number,
    from: string,
    to: string,
  ) => {
    let appDefaultText = i18n.t('serviceUsage.moveSandboxConfirmNoAppDefault');
    if (apps > 0) {
      appDefaultText = i18n.t('serviceUsage.moveSandboxConfirmAppDefault');
    }
    const changes = [
      i18n.t('serviceUsage.moveSandboxConfirmAgents', { count: agents }),
      appDefaultText,
    ];
    let inheritNote = '';
    if (apps > 0) {
      inheritNote = i18n.t('serviceUsage.moveSandboxConfirmInherited', { count: inherited, to });
    }
    return i18n.t('serviceUsage.moveSandboxConfirm', { changes: changes.join(` ${i18n.t('serviceUsage.conjunction')} `), from, to, inheritNote });
  },
  moveSandboxSuccess: (agents: number, apps: number) => {
    const parts = [
      agents > 0 && i18n.t('serviceUsage.moveSandboxSuccessAgents', { count: agents }),
      apps > 0 && i18n.t('serviceUsage.moveSandboxSuccessApps', { count: apps }),
    ].filter(Boolean);
    const conjunction = i18n.t('serviceUsage.conjunction');
    return parts.join(' ' + conjunction + ' ') + '.';
  },
  get moveSandboxNote() { return i18n.t('serviceUsage.moveSandboxNote'); },
  get deleteReview() { return i18n.t('serviceUsage.deleteReview'); },
  get deleteButton() { return i18n.t('serviceUsage.deleteButton'); },
  get deleting() { return i18n.t('serviceUsage.deleting'); },
} as const;

export const MAX_DEPRECATION_NOTICE_LENGTH = 1000;
