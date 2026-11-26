import { useEffect, useId, useMemo, useRef, useState, type CSSProperties, type FocusEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { Pencil } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { FormCheckbox, FormField, FormTextArea } from '../../ui/FormField';
import { KindIcon } from './KindIcon';
import { Badge } from '../../ui/Badge';
import { buttonAppSizeClasses, buttonAppVariantClasses } from '../../ui/ButtonApp';
import RagConfigSection, { type RagConfigValue, type RagFixedFilter } from '../../forms/RagConfigSection';
import type { SearchFilterMetadataField } from '../../playground/SearchFilters';
import { apiService, type Agent, type DataStructure, type Silo } from '../../../services/api';
import type { MCPConfig, Middleware } from '../../../core/types';
import { PIECE_VISUALS } from '../nodeKindConfig';
import { portsFor, type AgentType } from './agentPorts';
import type { CanvasSelection } from './AgentCanvas';
import type { CanvasPiece } from './useAgentCanvasData';

/** Saves `patch` on the edited agent through the canvas save queue; resolves true when it saved. */
export type SaveAgentFields = (patch: Record<string, unknown>) => Promise<boolean>;

export interface CanvasInspectorProps {
  readonly appId: number;
  readonly agent: Agent;
  readonly agentType: AgentType;
  /** Selection already resolved against the current agent and pieces; null shows the empty hint. */
  readonly selection: CanvasSelection | null;
  /** False for roles below EDITOR: every input is disabled. */
  readonly canEdit: boolean;
  /** True for ADMINISTRATOR and up: the AI service Edit button opens the editor in place. */
  readonly canCreateShared: boolean;
  /** Opens the AI service editor for the selected piece (the canvas refetches afterwards). */
  readonly onEditService: (piece: CanvasPiece) => void;
  /** Opens the overlay editor for the selected piece (skill, MCP, middleware, services, parser). */
  readonly onEditPiece: (piece: CanvasPiece) => void;
  /** Desktop width of the panel, driven by the canvas's resize divider. */
  readonly style?: CSSProperties;
  readonly onSaveFields: SaveAgentFields;
}

interface AgentFieldValues {
  name: string;
  description: string;
  system_prompt: string;
  vision_system_prompt: string;
  text_system_prompt: string;
  temperature: number;
  is_tool: boolean;
  has_memory: boolean;
  enable_code_interpreter: boolean;
  skill_router_enabled: boolean;
}

type TextField = 'name' | 'description' | 'system_prompt' | 'vision_system_prompt' | 'text_system_prompt';

/** Same range as the agent form's temperature slider. */
const TEMPERATURE_MIN = 0;
const TEMPERATURE_MAX = 2;

/** Keys of the RAG config that the threshold strategy depends on. */
const THRESHOLD_KEYS: ReadonlyArray<keyof RagConfigValue> = ['rag_search_type', 'rag_score_threshold'];

const LINK_CLASS =
  'rounded-sm text-sm font-medium text-fg underline underline-offset-2 hover:text-fg-secondary focus:outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent dark:text-fg-dark dark:hover:text-fg-secondary-dark dark:focus-visible:outline-accent-dark';

function savedAgentFields(agent: Agent): AgentFieldValues {
  return {
    name: agent.name,
    description: agent.description ?? '',
    system_prompt: agent.system_prompt ?? '',
    vision_system_prompt: agent.vision_system_prompt ?? '',
    text_system_prompt: agent.text_system_prompt ?? '',
    temperature: agent.temperature,
    is_tool: agent.is_tool,
    has_memory: agent.has_memory,
    enable_code_interpreter: agent.enable_code_interpreter,
    skill_router_enabled: agent.skill_router_enabled === true,
  };
}

/** The agent's saved RAG values, with the same fallbacks the agent form uses for missing fields. */
function savedRagValue(agent: Agent): RagConfigValue {
  return {
    rag_k: agent.rag_k ?? 10,
    rag_search_type: agent.rag_search_type ?? 'similarity',
    rag_score_threshold: agent.rag_score_threshold ?? null,
    // Null means unlimited retrieval calls, so it is kept as is (not coerced to a number).
    rag_max_retrieval_calls: agent.rag_max_retrieval_calls ?? null,
    rag_fixed_filters: agent.rag_fixed_filters ?? [],
  };
}

/** Drops incomplete rows and the editor-only `_key`, the same cleaning the agent form applies before saving. */
function cleanFilters(filters: readonly RagFixedFilter[]): Array<Omit<RagFixedFilter, '_key'>> {
  return filters
    .filter((filter) => filter.field && (Array.isArray(filter.value) ? filter.value.length > 0 : String(filter.value ?? '').trim() !== ''))
    .map(({ _key: _ignored, ...rest }) => rest);
}

/** Route of a piece's own editor page; null for the kinds edited in the overlay instead. */
function pieceEditPath(appId: number, piece: CanvasPiece): string | null {
  const base = `/apps/${appId}`;
  switch (piece.kind) {
    case 'agent':
      return `${base}/agents/${piece.id}?view=visual`;
    case 'silo':
      return `${base}/silos/${piece.id}`;
    default:
      return null;
  }
}

interface Drafts<T> {
  /** Unsaved edits, layered over the saved values. */
  readonly values: Partial<T>;
  /** Latest edits, readable synchronously (a blur right after a change must not see a stale render). */
  readonly read: () => Partial<T>;
  readonly set: <K extends keyof T>(key: K, value: T[K]) => void;
  readonly setAll: (patch: Partial<T>) => void;
  readonly clear: (key: keyof T) => void;
  /** Drops the draft only while it still holds `sent`: an edit made during the save keeps its draft. */
  readonly settle: (key: keyof T, sent: unknown) => void;
  /** Records a save as dispatched; until its refetch lands it is the value edits compare against. */
  readonly dispatch: (patch: Record<string, unknown>) => void;
  /** Forgets a dispatched value once its save resolved (the refetch has landed by then), if no newer save replaced it. */
  readonly landed: (key: keyof T, sent: unknown) => void;
  /** Last dispatched value for `key`, else `saved`. */
  readonly baseline: <K extends keyof T>(key: K, saved: T[K]) => T[K];
  /** True while a save for `key` is in flight or not yet refetched. */
  readonly isPending: (key: keyof T) => boolean;
}

/**
 * Unsaved field edits. Drafts show at once and are dropped when a save settles,
 * so a failed save reverts the field. Dispatched values bridge the gap until the
 * refetch lands, so an edit compares against what was last sent, not the stale fetch.
 */
function useDrafts<T extends object>(): Drafts<T> {
  const [values, setValues] = useState<Partial<T>>({});
  const latest = useRef<Partial<T>>({});
  const dispatched = useRef<Map<string, unknown>>(new Map());

  const replace = (next: Partial<T>) => {
    latest.current = next;
    setValues(next);
  };
  const clear = (key: keyof T) => {
    const next = { ...latest.current };
    delete next[key];
    replace(next);
  };

  return {
    values,
    read: () => latest.current,
    set: (key, value) => replace({ ...latest.current, [key]: value }),
    setAll: (patch) => replace({ ...latest.current, ...patch }),
    clear,
    settle: (key, sent) => {
      if (latest.current[key] === sent) clear(key);
    },
    dispatch: (patch) => {
      for (const [key, value] of Object.entries(patch)) dispatched.current.set(key, value);
    },
    landed: (key, sent) => {
      const name = String(key);
      if (dispatched.current.has(name) && dispatched.current.get(name) === sent) dispatched.current.delete(name);
    },
    baseline: (key, saved) =>
      dispatched.current.has(String(key)) ? (dispatched.current.get(String(key)) as typeof saved) : saved,
    isPending: (key) => dispatched.current.has(String(key)),
  };
}

interface AgentFieldsProps {
  readonly agent: Agent;
  readonly agentType: AgentType;
  readonly canEdit: boolean;
  readonly onSaveFields: SaveAgentFields;
}

/** Editable fields of the selected agent. Text saves on blur (when changed); toggles and the number save on change. */
function AgentFields({ agent, agentType, canEdit, onSaveFields }: AgentFieldsProps) {
  const { t } = useTranslation('common');
  const baseId = useId();
  const saved = useMemo(() => savedAgentFields(agent), [agent]);
  const drafts = useDrafts<AgentFieldValues>();
  const values = useMemo<AgentFieldValues>(() => ({ ...saved, ...drafts.values }), [saved, drafts.values]);
  const isOcr = agentType === 'ocr_agent';
  // Temperature text while the user types; null shows the value. Parsed and clamped on blur only.
  const [temperatureText, setTemperatureText] = useState<string | null>(null);

  /** Saves one field unless it matches the last dispatched (or saved) value; a failed save reverts through settle. */
  async function persist<K extends keyof AgentFieldValues>(field: K, value: AgentFieldValues[K]): Promise<void> {
    if (value === drafts.baseline(field, saved[field])) {
      if (!drafts.isPending(field)) drafts.clear(field);
      return;
    }
    drafts.set(field, value);
    drafts.dispatch({ [field]: value });
    await onSaveFields({ [field]: value });
    drafts.landed(field, value);
    drafts.settle(field, value);
  }

  function commitText(field: TextField, text: string): void {
    if (field === 'name' && text.trim() === '') {
      // A blank name is never saved: drop the draft so the field shows the saved name again.
      drafts.clear('name');
      toast.error(t('agentCanvas.inspector.nameRequired'));
      return;
    }
    void persist(field, text);
  }

  function commitTemperature(text: string): void {
    setTemperatureText(null);
    const parsed = Number.parseFloat(text);
    if (!Number.isFinite(parsed)) return;
    void persist('temperature', Math.min(TEMPERATURE_MAX, Math.max(TEMPERATURE_MIN, parsed)));
  }

  const textInput = (field: TextField, label: string) => (
    <FormField
      id={`${baseId}-${field}`}
      label={label}
      value={values[field]}
      disabled={!canEdit}
      onChange={(event) => drafts.set(field, event.currentTarget.value)}
      onBlur={(event) => commitText(field, event.currentTarget.value)}
    />
  );

  // FormTextArea has no onBlur prop; blur bubbles, so the wrapper commits the text on leaving it.
  const promptInput = (field: TextField, label: string) => (
    <div onBlur={(event) => {
        if (event.target instanceof HTMLTextAreaElement) commitText(field, event.target.value);
      }}>
      <FormTextArea
        id={`${baseId}-${field}`}
        label={label}
        rows={6}
        value={values[field]}
        disabled={!canEdit}
        onChange={(event) => drafts.set(field, event.currentTarget.value)}
        textareaClassName="resize-y"
      />
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display text-[17px] font-medium text-fg dark:text-fg-dark">{isOcr ? t('agentCanvas.kinds.ocrAgent') : t('agentCanvas.kinds.agent')}</h3>
        <Link to="?view=form" className={LINK_CLASS}>
          {t('agentCanvas.inspector.openFullEditor')}
        </Link>
      </div>

      {textInput('name', t('agentCanvas.inspector.fields.name'))}
      {textInput('description', t('agentCanvas.inspector.fields.description'))}
      {isOcr ? (
        <>
          {promptInput('vision_system_prompt', t('agentCanvas.inspector.fields.visionPrompt'))}
          {promptInput('text_system_prompt', t('agentCanvas.inspector.fields.textPrompt'))}
        </>
      ) : (
        promptInput('system_prompt', t('agentCanvas.inspector.fields.systemPrompt'))
      )}

      <FormField
        id={`${baseId}-temperature`}
        label={t('agentCanvas.inspector.fields.temperature')}
        type="number"
        min={TEMPERATURE_MIN}
        max={TEMPERATURE_MAX}
        step={0.1}
        value={temperatureText ?? String(values.temperature)}
        disabled={!canEdit}
        helpText={t('agentCanvas.inspector.fields.temperatureHelp')}
        onChange={(event) => setTemperatureText(event.currentTarget.value)}
        onBlur={(event) => commitTemperature(event.currentTarget.value)}
      />

      <div className="space-y-2">
        <FormCheckbox
          id={`${baseId}-is_tool`}
          label={t('agentCanvas.inspector.toggles.isTool.label')}
          helpText={t('agentCanvas.inspector.toggles.isTool.help')}
          checked={values.is_tool}
          disabled={!canEdit}
          onChange={(event) => void persist('is_tool', event.currentTarget.checked)}
        />
        <FormCheckbox
          id={`${baseId}-has_memory`}
          label={t('agentCanvas.inspector.toggles.hasMemory.label')}
          helpText={t('agentCanvas.inspector.toggles.hasMemory.help')}
          checked={values.has_memory}
          disabled={!canEdit}
          onChange={(event) => {
            const checked = event.currentTarget.checked;
            // Backend rule: conversational agents index chat uploads in a per-conversation
            // silo, which needs a media embedding service. Refuse without one (non-OCR only).
            if (checked && !isOcr && !agent.media_embedding_service_id) {
              toast.error(t('agentCanvas.inspector.memoryNeedsMediaEmbedding'));
              return;
            }
            void persist('has_memory', checked);
          }}
        />
        <FormCheckbox
          id={`${baseId}-enable_code_interpreter`}
          label={t('agentCanvas.inspector.toggles.codeInterpreter.label')}
          helpText={t('agentCanvas.inspector.toggles.codeInterpreter.help')}
          checked={values.enable_code_interpreter}
          disabled={!canEdit}
          onChange={(event) => void persist('enable_code_interpreter', event.currentTarget.checked)}
        />
        <FormCheckbox
          id={`${baseId}-skill_router_enabled`}
          label={t('agentCanvas.inspector.toggles.skillRouter.label')}
          helpText={t('agentCanvas.inspector.toggles.skillRouter.help')}
          checked={values.skill_router_enabled}
          disabled={!canEdit}
          onChange={(event) => void persist('skill_router_enabled', event.currentTarget.checked)}
        />
      </div>
    </div>
  );
}

interface KnowledgeSettingsProps {
  readonly agent: Agent;
  readonly canEdit: boolean;
  readonly onSaveFields: SaveAgentFields;
}

/** RAG retrieval settings for the agent's knowledge edge. Saves on leaving the section, or at once when a filter row is removed. */
function KnowledgeSettings({ agent, canEdit, onSaveFields }: KnowledgeSettingsProps) {
  const { t } = useTranslation('common');
  const saved = useMemo(() => savedRagValue(agent), [agent]);
  const drafts = useDrafts<RagConfigValue>();
  const value = useMemo<RagConfigValue>(() => ({ ...saved, ...drafts.values }), [saved, drafts.values]);
  const metadataFields = useMemo<SearchFilterMetadataField[]>(
    () =>
      (agent.silo?.metadata_definition?.fields ?? []).map((field) => ({
        name: field.name,
        type: field.type,
        description: field.description,
      })),
    [agent],
  );

  /**
   * Saves the drafts that differ from the saved agent. A threshold strategy
   * without a threshold is held back (the section asks for one); everything
   * else still saves.
   */
  function commit(): void {
    const pending = drafts.read();
    const effective = { ...saved, ...pending };
    const thresholdMissing =
      effective.rag_search_type === 'similarity_score_threshold' && effective.rag_score_threshold == null;

    const patch: Record<string, unknown> = {};
    const sent: Record<string, unknown> = {};
    for (const [key, draft] of Object.entries(pending) as Array<[keyof RagConfigValue, unknown]>) {
      if (draft === undefined) continue;
      if (thresholdMissing && THRESHOLD_KEYS.includes(key)) continue;
      const next = Array.isArray(draft) ? cleanFilters(draft) : draft;
      if (JSON.stringify(next) === JSON.stringify(drafts.baseline(key, saved[key]))) {
        if (!drafts.isPending(key)) drafts.clear(key);
        continue;
      }
      patch[key] = next;
      sent[key] = draft;
    }
    // Leaving the threshold strategy drops the saved threshold too (as the agent form does).
    if (
      patch.rag_search_type !== undefined &&
      effective.rag_search_type !== 'similarity_score_threshold' &&
      drafts.baseline('rag_score_threshold', saved.rag_score_threshold) !== null
    ) {
      patch.rag_score_threshold = null;
    }
    if (thresholdMissing && (pending.rag_search_type !== undefined || pending.rag_score_threshold !== undefined)) {
      toast.info(t('agentCanvas.inspector.thresholdRequired'));
    }
    if (Object.keys(patch).length === 0) return;

    drafts.dispatch(patch);
    void onSaveFields(patch).then(() => {
      for (const key of Object.keys(patch) as Array<keyof RagConfigValue>) drafts.landed(key, patch[key]);
      for (const key of Object.keys(sent) as Array<keyof RagConfigValue>) drafts.settle(key, sent[key]);
    });
  }

  function handleChange(patch: Partial<RagConfigValue>): void {
    const removesFilter =
      patch.rag_fixed_filters !== undefined && patch.rag_fixed_filters.length < value.rag_fixed_filters.length;
    drafts.setAll(patch);
    // A removed row's button leaves the DOM, so the section never blurs: save now.
    if (removesFilter) commit();
  }

  function handleBlur(event: FocusEvent<HTMLFieldSetElement>): void {
    // Focus moving between controls of the section is not a commit.
    if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
    commit();
  }

  // RagConfigSection has no disabled prop, so the fieldset disables its controls.
  return (
    <fieldset
      disabled={!canEdit}
      onBlur={handleBlur}
      className="m-0 min-w-0 border-0 p-0 [&_:disabled]:cursor-not-allowed [&_:disabled]:opacity-60"
    >
      <legend className="sr-only">{t('agentCanvas.inspector.retrievalSettings')}</legend>
      <RagConfigSection value={value} onChange={handleChange} metadataFields={metadataFields} loadingMetadata={false} />
    </fieldset>
  );
}

interface PieceInfoRow {
  /** Suffix under agentCanvas.inspector.info. */
  readonly labelKey: string;
  /** Literal value (names, numbers, dates). */
  readonly value?: string;
  /** Full i18n key of a translatable value; wins over `value`. */
  readonly valueKey?: string;
}

interface PieceInfo {
  readonly rows: readonly PieceInfoRow[];
  readonly description?: string;
}

const NO_PIECE_INFO: PieceInfo = { rows: [] };

/** `summarization` → "Summarization", `human_in_the_loop` → "Human in the loop". */
function prettyWords(value: string): string {
  return value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

/** The agent piece's read-only facts; they already ride along in the canvas payload. */
function agentPieceInfo(piece: CanvasPiece): PieceInfo {
  const info = piece.agentInfo;
  if (!info) return NO_PIECE_INFO;
  return {
    rows: [
      { labelKey: 'type', valueKey: info.type === 'ocr_agent' ? 'agentCanvas.kinds.ocrAgent' : 'agentCanvas.kinds.agent' },
      info.modelName ? { labelKey: 'model', value: info.modelName } : { labelKey: 'model', valueKey: 'agentCanvas.inspector.info.noModel' },
      { labelKey: 'toolAgent', valueKey: piece.isTool ? 'agentCanvas.inspector.info.yes' : 'agentCanvas.inspector.info.no' },
      { labelKey: 'tools', value: String(info.toolCount) },
      { labelKey: 'requests', value: String(info.requestCount) },
      info.lastUsedDate
        ? { labelKey: 'lastUsed', value: new Date(info.lastUsedDate).toLocaleString() }
        : { labelKey: 'lastUsed', valueKey: 'agentCanvas.inspector.info.never' },
    ],
    description: info.description,
  };
}

/**
 * The most relevant read-only facts per piece kind, fetched from the piece's
 * own detail endpoint (the agent piece carries its own). Refetches whenever
 * the canvas data reloads, so it never shows a stale name or status.
 */
function usePieceInfo(appId: number, piece: CanvasPiece): PieceInfo {
  const [info, setInfo] = useState<PieceInfo>(NO_PIECE_INFO);
  useEffect(() => {
    if (piece.kind === 'agent') {
      setInfo(agentPieceInfo(piece));
      return;
    }
    let cancelled = false;
    setInfo(NO_PIECE_INFO);
    (async () => {
      let next: PieceInfo;
      switch (piece.kind) {
        case 'ai_service': {
          const service = await apiService.getAIService(appId, piece.id);
          next = {
            rows: [
              { labelKey: 'model', value: service.model_name || '—' },
              { labelKey: 'provider', value: service.provider || '—' },
              { labelKey: 'video', valueKey: service.supports_video ? 'agentCanvas.inspector.info.supported' : 'agentCanvas.inspector.info.notSupported' },
            ],
          };
          break;
        }
        case 'embedding': {
          const service = await apiService.getEmbeddingService(appId, piece.id);
          next = {
            rows: [
              { labelKey: 'model', value: service.model_name || '—' },
              { labelKey: 'provider', value: service.provider || '—' },
            ],
          };
          break;
        }
        case 'sandbox': {
          const service = (await apiService.getSandboxService(appId, piece.id)) as { provider?: string };
          next = { rows: [{ labelKey: 'provider', value: service.provider || '—' }] };
          break;
        }
        case 'silo': {
          const silo: Silo = await apiService.getSilo(appId, piece.id);
          next = {
            rows: [
              { labelKey: 'vectorDb', value: silo.vector_db_type || '—' },
              { labelKey: 'documents', value: String(silo.docs_count) },
            ],
            description: silo.description,
          };
          break;
        }
        case 'skill': {
          const skill = await apiService.getSkill(appId, piece.id);
          next = { rows: [], description: skill.description };
          break;
        }
        case 'mcp': {
          const config: MCPConfig = await apiService.getMCPConfig(appId, piece.id);
          next = {
            rows: [{ labelKey: 'transport', value: config.transport_type || '—' }],
            description: config.description,
          };
          break;
        }
        case 'parser': {
          const parser: DataStructure = await apiService.getOutputParser(appId, piece.id);
          next = {
            rows: [{ labelKey: 'fields', value: String(parser.fields?.length ?? parser.field_count ?? 0) }],
            description: parser.description,
          };
          break;
        }
        case 'middleware': {
          const middleware: Middleware = await apiService.getMiddleware(appId, piece.id);
          next = {
            rows: [{ labelKey: 'type', value: middleware.middleware_type ? prettyWords(middleware.middleware_type) : '—' }],
            description: middleware.description,
          };
          break;
        }
        default:
          return;
      }
      if (cancelled) return;
      setInfo(next);
    })().catch(() => {
      // A failed detail fetch leaves the piece's name and type on their own.
    });
    return () => {
      cancelled = true;
    };
  }, [appId, piece]);
  return info;
}

const INFO_LABEL_CLASS = 'shrink-0 text-[11px] font-medium uppercase tracking-wide text-fg-tertiary dark:text-fg-tertiary-dark';
const INFO_VALUE_CLASS = 'min-w-0 truncate text-xs font-medium text-fg group-hover:whitespace-normal group-hover:break-words dark:text-fg-dark';
const EDIT_BLOB_CLASS = `inline-flex cursor-pointer items-center justify-center gap-2 font-display font-normal tracking-[-0.02em] transition-colors ${buttonAppSizeClasses.compact} rounded-md ${buttonAppVariantClasses.table} focus:outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent dark:focus-visible:outline-accent-dark disabled:cursor-not-allowed disabled:opacity-50`;

function EditBlob(props: { readonly disabled?: boolean; readonly onClick?: () => void; readonly to?: string; readonly state?: Record<string, string> }) {
  const { t } = useTranslation('common');
  const { disabled, onClick, to, state } = props;
  const label = t('agentCanvas.inspector.edit');
  if (to) {
    return (
      <Link to={to} state={state} className={EDIT_BLOB_CLASS}>
        <Pencil className="h-3 w-3" aria-hidden="true" />
        {label}
      </Link>
    );
  }
  return (
    <button
      type="button"
      disabled={disabled}
      title={disabled ? t('agentCanvas.inspector.adminRequired') : undefined}
      onClick={onClick}
      className={EDIT_BLOB_CLASS}
    >
      <Pencil className="h-3 w-3" aria-hidden="true" />
      {label}
    </button>
  );
}

interface PieceDetailsProps {
  readonly appId: number;
  readonly piece: CanvasPiece;
  /** Sentence describing the connection when an edge is selected. */
  readonly connection?: string;
  /** True for ADMINISTRATOR and up: the wizard kinds' Edit button opens the overlay editor. */
  readonly canEditShared: boolean;
  /** Opens the AI service editor for the selected piece (the canvas refetches afterwards). */
  readonly onEditService: (piece: CanvasPiece) => void;
  /** Opens the overlay editor for the selected piece (skill, MCP, middleware, services, parser). */
  readonly onEditPiece: (piece: CanvasPiece) => void;
}

function PieceDetails({ appId, piece, connection, canEditShared, onEditService, onEditPiece }: PieceDetailsProps) {
  const { t } = useTranslation('common');
  const visual = PIECE_VISUALS[piece.kind];
  const location = useLocation();
  const info = usePieceInfo(appId, piece);
  const path = pieceEditPath(appId, piece);
  const isSilo = piece.kind === 'silo';
  const isAgent = piece.kind === 'agent';
  // Wizard kinds are shared resources and need ADMINISTRATOR; silos and agents open their own page.
  const disabled = !isSilo && !isAgent && !canEditShared;
  // The kinds captions are keyed by the graph kind name; the AI service piece is "service".
  const captionKey = piece.kind === 'ai_service' ? 'service' : piece.kind;

  return (
    <div className="space-y-4">
      <div className="group flex items-center gap-3">
        <KindIcon icon={visual.icon} color={visual.accentHex} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className="text-xs font-medium text-fg-tertiary dark:text-fg-tertiary-dark">{t(`agentCanvas.kinds.${captionKey}`)}</p>
            {piece.isSystem && <Badge label={t('agentCanvas.inspector.badges.system')} variant="info" />}
            {piece.isTool && <Badge label={t('agentCanvas.inspector.badges.tool')} variant="success" />}
          </div>
          <h3 className="truncate font-display text-[17px] font-medium text-fg dark:text-fg-dark" title={piece.name}>
            {piece.name}
          </h3>
        </div>
      </div>
      {connection && <p className="text-xs italic text-fg-tertiary dark:text-fg-tertiary-dark">{connection}</p>}

      {(info.rows.length > 0 || info.description) && (
        <div className="space-y-2.5 rounded-md border border-line bg-surface-tint p-3 dark:border-btCard-border-dark dark:bg-surface-tint-dark">
          {info.rows.map((row) => {
            const value = row.valueKey ? t(row.valueKey) : (row.value ?? '');
            return (
              <div key={row.labelKey} className="group flex items-baseline justify-between gap-3">
                <span className={INFO_LABEL_CLASS}>{t(`agentCanvas.inspector.info.${row.labelKey}`)}</span>
                <span className={INFO_VALUE_CLASS} title={value}>
                  {value}
                </span>
              </div>
            );
          })}
          {info.description && (
            <div className="min-w-0">
              <p className={INFO_LABEL_CLASS}>{t('agentCanvas.inspector.info.description')}</p>
              <p className="mt-0.5 whitespace-pre-line text-xs leading-relaxed text-fg-secondary dark:text-fg-secondary-dark">
                {info.description}
              </p>
            </div>
          )}
        </div>
      )}

      {/* AI services edit in place through their editor; the wizard kinds open the overlay; silos and agents open their own page. */}
      {isAgent || isSilo ? (
        <EditBlob
          to={path ?? undefined}
          state={isSilo ? { returnTo: `${location.pathname}${location.search}` } : undefined}
        />
      ) : piece.kind === 'ai_service' ? (
        <EditBlob disabled={!canEditShared} onClick={() => onEditService(piece)} />
      ) : (
        <EditBlob disabled={disabled} onClick={() => onEditPiece(piece)} />
      )}
    </div>
  );
}

/**
 * Right-hand inspector of the per-agent canvas. Shows the editor for the
 * current selection: the agent's fields, a piece's read-only details with its
 * edit action (the AI service editor in place, the wizard overlay, or the
 * piece's own page), or the RAG settings / connection of an edge. Every save
 * goes through `onSaveFields` (the canvas save queue), so field saves never
 * race a connection.
 */
export function CanvasInspector({
  appId,
  agent,
  agentType,
  selection,
  canEdit,
  canCreateShared,
  onEditService,
  onEditPiece,
  style,
  onSaveFields,
}: CanvasInspectorProps) {
  const { t } = useTranslation('common');
  const edgePort = selection?.type === 'edge' ? portsFor(agentType).find((port) => port.id === selection.port) : undefined;
  const connection =
    selection?.type === 'edge'
      ? [
          t('agentCanvas.inspector.connectedTo', {
            port: edgePort
              ? t(`agentCanvas.ports.${edgePort.id}`)
              : t('agentCanvas.inspector.thisPort'),
          }),
          canEdit ? t('agentCanvas.inspector.disconnectHint') : '',
        ]
          .filter(Boolean)
          .join(' ')
      : undefined;

  return (
    <aside
      aria-label={t('agentCanvas.inspector.title')}
      style={style}
      className="flex max-h-96 w-full shrink-0 flex-col overflow-hidden rounded-md border border-line bg-surface md:self-start md:max-h-none md:w-[var(--inspector-w)] dark:border-btCard-border-dark dark:bg-surface-dark"
    >
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {selection === null && (
          <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{t('agentCanvas.inspector.emptyHint')}</p>
        )}

        {selection?.type === 'agent' && (
          <AgentFields
            key={agent.agent_id}
            agent={agent}
            agentType={agentType}
            canEdit={canEdit}
            onSaveFields={onSaveFields}
          />
        )}

        {selection?.type === 'piece' && (
          <PieceDetails
            appId={appId}
            piece={selection.piece}
            canEditShared={canCreateShared}
            onEditService={onEditService}
            onEditPiece={onEditPiece}
          />
        )}

        {selection?.type === 'edge' && selection.port === 'knowledge' && (
          <div className="space-y-4">
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
              {t('agentCanvas.inspector.knowledgeLabel')}: <span className="font-medium text-fg dark:text-fg-dark">{selection.piece.name}</span>
            </p>
            <KnowledgeSettings key={agent.agent_id} agent={agent} canEdit={canEdit} onSaveFields={onSaveFields} />
          </div>
        )}

        {selection?.type === 'edge' && selection.port !== 'knowledge' && (
          <PieceDetails
            appId={appId}
            piece={selection.piece}
            connection={connection}
            canEditShared={canCreateShared}
            onEditService={onEditService}
            onEditPiece={onEditPiece}
          />
        )}
      </div>
    </aside>
  );
}
