/**
 * Pure logic of the App Chat page (selection state, defaults merge, warning mapping, turn meta).
 * Kept free of React / i18n / api imports so it can be unit-tested with the `node --test` harness.
 */
import type {
  ChatOptions,
  ChatSelection,
  ChatSelectionWarning,
  ChatTurnConfig,
  ChatTurnInfo,
  ChatWarningKind,
} from '../../types/appChat';

// ---------------------------------------------------------------------------
// Selection state
// ---------------------------------------------------------------------------

export type ChatSelectionAction =
  | { readonly type: 'setModel'; readonly id: number }
  | { readonly type: 'setSilo'; readonly id: number | null }
  | { readonly type: 'setSkills'; readonly ids: readonly number[] }
  | { readonly type: 'setMcpConfigs'; readonly ids: readonly number[] }
  | { readonly type: 'replace'; readonly selection: ChatSelection | null };

/** `null` means "no model can be chosen yet" (options not loaded, or the App has no usable model). */
export function selectionReducer(state: ChatSelection | null, action: ChatSelectionAction): ChatSelection | null {
  switch (action.type) {
    case 'replace':
      return action.selection;
    case 'setModel':
      // Picking a model on an empty selection starts a selection with nothing else enabled.
      return state
        ? { ...state, ai_service_id: action.id }
        : { ai_service_id: action.id, silo_id: null, skill_ids: [], mcp_config_ids: [] };
    case 'setSilo':
      return state ? { ...state, silo_id: action.id } : state;
    case 'setSkills':
      return state ? { ...state, skill_ids: [...action.ids] } : state;
    case 'setMcpConfigs':
      return state ? { ...state, mcp_config_ids: [...action.ids] } : state;
  }
}

function isSelectableModel(options: ChatOptions, id: number): boolean {
  return options.ai_services.some((s) => s.service_id === id && s.lifecycle_status !== 'retired');
}

function isSelectableSilo(options: ChatOptions, id: number): boolean {
  return options.silos.some((s) => s.silo_id === id && !s.disabled_reason);
}

export function dedupeWarnings(warnings: readonly ChatSelectionWarning[]): ChatSelectionWarning[] {
  const seen = new Set<string>();
  const result: ChatSelectionWarning[] = [];
  for (const warning of warnings) {
    if (warning.kind === 'sandbox_output') {
      // `id` is a count: one warning per turn, with the largest count.
      const index = result.findIndex((w) => w.kind === 'sandbox_output');
      if (index === -1) result.push(warning);
      else if (warning.id > result[index].id) result[index] = warning;
      continue;
    }
    const key = `${warning.kind}:${warning.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(warning);
  }
  return result;
}

export interface ResolvedSelection {
  /** Null when no model can be selected (the send button stays disabled). */
  readonly selection: ChatSelection | null;
  readonly warnings: readonly ChatSelectionWarning[];
}

/**
 * Selection to show when entering the Chat.
 * - `candidate` (the stored selection of an open conversation) wins; without it the user's default applies
 *   (`options.default_selection`, whose own dropped ids come in `options.default_warnings`).
 * - Every id that is not selectable according to `options` is dropped with a warning (FR-10), and a dropped
 *   model falls back to the default model, then to the first selectable one.
 */
export function resolveInitialSelection(
  candidate: ChatSelection | null | undefined,
  options: ChatOptions,
  candidateWarnings: readonly ChatSelectionWarning[] = [],
): ResolvedSelection {
  const warnings: ChatSelectionWarning[] = candidate
    ? [...candidateWarnings]
    : [...options.default_warnings];
  const source = candidate ?? options.default_selection ?? null;

  let modelId: number | null = null;
  if (source && isSelectableModel(options, source.ai_service_id)) {
    modelId = source.ai_service_id;
  } else {
    if (source) warnings.push({ kind: 'ai_service', id: source.ai_service_id });
    const fallbackDefault = options.default_selection?.ai_service_id;
    if (fallbackDefault !== undefined && isSelectableModel(options, fallbackDefault)) {
      modelId = fallbackDefault;
    } else {
      modelId = options.ai_services.find((s) => s.lifecycle_status !== 'retired')?.service_id ?? null;
    }
  }
  if (modelId === null) return { selection: null, warnings: dedupeWarnings(warnings) };

  let siloId: number | null = null;
  if (source?.silo_id != null) {
    if (isSelectableSilo(options, source.silo_id)) siloId = source.silo_id;
    else warnings.push({ kind: 'silo', id: source.silo_id });
  }
  const skillIds: number[] = [];
  for (const id of source?.skill_ids ?? []) {
    if (options.skills.some((s) => s.skill_id === id)) skillIds.push(id);
    else warnings.push({ kind: 'skill', id });
  }
  const mcpIds: number[] = [];
  for (const id of source?.mcp_config_ids ?? []) {
    if (options.mcp_configs.some((c) => c.config_id === id)) mcpIds.push(id);
    else warnings.push({ kind: 'mcp_config', id });
  }
  return {
    selection: { ai_service_id: modelId, silo_id: siloId, skill_ids: skillIds, mcp_config_ids: mcpIds },
    warnings: dedupeWarnings(warnings),
  };
}

export interface NewChatDefaultsDecision {
  /** The refetch still belongs to the open new chat: unblock sending. */
  readonly resolve: boolean;
  /** ...and the user has not touched the selection meanwhile, so the defaults may replace it. */
  readonly applySelection: boolean;
}

/**
 * What to do when the options refetch that follows "New conversation" settles. A stale request (the user
 * started another "New", or moved to another conversation) does nothing; a selection the user changed in
 * the meantime is never overwritten.
 */
export function decideNewChatDefaults(
  requestToken: number,
  currentToken: number,
  routeIsNewChat: boolean,
  selectionTouched: boolean,
): NewChatDefaultsDecision {
  const resolve = requestToken === currentToken && routeIsNewChat;
  return { resolve, applySelection: resolve && !selectionTouched };
}

export type SendBlockReason = 'noUsableModel' | 'noSelection' | 'modelRetired' | 'loading';

/**
 * Why the composer cannot send, or null when it can. `selectionReady` is false while the selection is still being
 * resolved (conversation switch, deep link, defaults refetch after "New"): the selectors are locked then, so the
 * reason is "loading", not "select a model".
 */
export function sendBlockReason(
  options: ChatOptions | null,
  selection: ChatSelection | null,
  selectionReady = true,
): SendBlockReason | null {
  if (!options) return 'loading';
  if (!options.has_usable_model || options.ai_services.length === 0) return 'noUsableModel';
  if (!selectionReady) return 'loading';
  if (!selection) return 'noSelection';
  // E.g. after a 409 SERVICE_RETIRED: the model stays selected until the user picks another one.
  if (!isSelectableModel(options, selection.ai_service_id)) return 'modelRetired';
  return null;
}

/**
 * Selection for a conversation that is not stored anywhere yet.
 * - Starting a new conversation after having opened one: the user's defaults (`options` must be fresh, the
 *   backend updates the default on every completed turn).
 * - First entry, or a new chat the user already adjusted without sending: what is on screen stays.
 */
export function resolveNewConversationSelection(
  options: ChatOptions,
  current: ChatSelection | null,
  afterOpenedConversation: boolean,
): ResolvedSelection {
  if (current && !afterOpenedConversation) return { selection: current, warnings: [] };
  return resolveInitialSelection(null, options);
}

// ---------------------------------------------------------------------------
// Attachment indexing notice
// ---------------------------------------------------------------------------

/** Suffix of `appChat.attachmentIndexing.<kind>`; null when indexing works (or the backend does not report it). */
export function attachmentIndexingNotice(options: ChatOptions | null): 'noDefault' | 'retired' | 'unavailable' | null {
  const indexing = options?.attachment_indexing;
  if (!indexing || indexing.enabled !== false) return null;
  if (indexing.reason === 'embedding_service_retired') return 'retired';
  if (indexing.reason === 'no_default_embedding_service') return 'noDefault';
  // Unknown reason: do not claim a cause that may be false.
  return 'unavailable';
}

// ---------------------------------------------------------------------------
// Code interpreter notice
// ---------------------------------------------------------------------------

export type CodeInterpreterNoticeKind = 'disabled' | 'retired' | 'providerUnavailable' | 'unavailable';

/**
 * Suffix of `appChat.codeInterpreter.<kind>`; null when nothing should be said.
 * "Not set up" (switch off) matters only once the selection has a skill, since only skills carry scripts. Reasons where an administrator had it working (retired, provider) and unknown
 * ones always show. A missing block (older backend) shows nothing.
 */
export function codeInterpreterNotice(
  options: ChatOptions | null,
  selection: ChatSelection | null,
): CodeInterpreterNoticeKind | null {
  const interpreter = options?.code_interpreter;
  if (!interpreter || interpreter.enabled !== false) return null;
  const hasSkills = (selection?.skill_ids.length ?? 0) > 0;
  switch (interpreter.reason) {
    case 'disabled_in_app_settings':
      return hasSkills ? 'disabled' : null;
    case 'sandbox_service_retired':
      return 'retired';
    case 'sandbox_provider_unavailable':
      return 'providerUnavailable';
    default:
      // Unknown reason: do not claim a cause that may be false.
      return 'unavailable';
  }
}

// ---------------------------------------------------------------------------
// Warnings
// ---------------------------------------------------------------------------

export interface WarningMessage {
  /** Suffix of the i18n key `appChat.warnings.<key>`. */
  readonly key: string;
  readonly values: { readonly name?: string; readonly count?: number };
}

function lookupName(options: ChatOptions | null, warning: ChatSelectionWarning): string | undefined {
  if (!options) return undefined;
  switch (warning.kind) {
    case 'ai_service':
      return options.ai_services.find((s) => s.service_id === warning.id)?.name;
    case 'silo':
      return options.silos.find((s) => s.silo_id === warning.id)?.name ?? undefined;
    case 'skill':
      return options.skills.find((s) => s.skill_id === warning.id)?.name;
    case 'mcp_config':
      return options.mcp_configs.find((c) => c.config_id === warning.id)?.name;
    case 'sandbox_output':
      return undefined;
  }
}

/** Maps warnings to translation keys; `<kind>Named` when the resource name is known from the options. */
export function describeWarnings(
  warnings: readonly ChatSelectionWarning[],
  options: ChatOptions | null,
): WarningMessage[] {
  return dedupeWarnings(warnings)
    // A kind from a newer backend has no translation: say nothing rather than show a raw key.
    .filter((warning) => WARNING_KINDS.includes(warning.kind))
    .map((warning) => {
    if (warning.kind === 'sandbox_output') return { key: 'sandbox_output', values: { count: warning.id } };
    const name = lookupName(options, warning);
    return name ? { key: `${warning.kind}Named`, values: { name } } : { key: warning.kind, values: {} };
  });
}

export const WARNING_KINDS: readonly ChatWarningKind[] = ['ai_service', 'silo', 'skill', 'mcp_config', 'sandbox_output'];

// ---------------------------------------------------------------------------
// Per-message meta
// ---------------------------------------------------------------------------

export interface MetaItem {
  readonly id: number;
  readonly label: string;
  readonly deleted: boolean;
}

export interface TurnMeta {
  readonly model: MetaItem;
  readonly source: MetaItem | null;
  readonly skills: readonly MetaItem[];
  readonly mcps: readonly MetaItem[];
}

/**
 * Model / source / skills / MCPs of a message. History and the `done` event give `turn` (with the
 * "deleted" flags); while a turn is only known by its `metadata` event (`turnConfig`) nothing is deleted.
 * Returns null when the message carries neither.
 */
export function buildTurnMeta(
  turn: ChatTurnInfo | null | undefined,
  turnConfig: ChatTurnConfig | null | undefined,
  siloFallbackName: (id: number) => string,
): TurnMeta | null {
  if (turn) {
    return {
      model: { id: turn.ai_service_id ?? 0, label: turn.ai_service_name, deleted: turn.ai_service_deleted },
      source:
        turn.silo_id == null
          ? null
          : {
              id: turn.silo_id,
              label: turn.silo_name || siloFallbackName(turn.silo_id),
              deleted: turn.silo_deleted,
            },
      skills: turn.skills.map((s) => ({ id: s.id, label: s.name, deleted: s.deleted })),
      mcps: turn.mcp_configs.map((c) => ({ id: c.id, label: c.name, deleted: c.deleted })),
    };
  }
  if (turnConfig) {
    return {
      model: { id: turnConfig.ai_service.id, label: turnConfig.ai_service.name, deleted: false },
      source: turnConfig.silo
        ? {
            id: turnConfig.silo.id,
            label: turnConfig.silo.name || siloFallbackName(turnConfig.silo.id),
            deleted: false,
          }
        : null,
      skills: turnConfig.skills.map((s) => ({ id: s.id, label: s.name, deleted: false })),
      mcps: turnConfig.mcp_configs.map((c) => ({ id: c.id, label: c.name, deleted: false })),
    };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Route
// ---------------------------------------------------------------------------

/** `:conversationId` of the route; null when absent or not a positive integer. */
export function parseConversationId(value: string | undefined): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const id = Number.parseInt(value, 10);
  return id > 0 ? id : null;
}

export function chatPath(appId: number | string, conversationId?: number | null): string {
  return conversationId ? `/apps/${appId}/chat/${conversationId}` : `/apps/${appId}/chat`;
}
