import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { apiService, type AIService } from '../../services/api';
import { ServiceOptionStatus, serviceStatusId } from '../ui/ServiceOptionStatus';
import type { MCPConfig, Middleware, MiddlewarePayload, MiddlewareType } from '../../core/types';
import { MIDDLEWARE_TYPES, agentToolName } from '../../constants/middlewares';
import { selectableServiceOptions, serviceOptionLabel } from '../../utils/serviceLifecycle';
import FormActions from '../ui/FormActions';
import { ButtonCard } from '../ui/ButtonCard';
import { ButtonApp } from '../ui/ButtonApp';
import { FormField, FormSelect, FormTextArea } from '../ui/FormField';
import CardApp from '../ui/CardApp';
import Alert from '../ui/Alert';
import Table from '../ui/Table';

// Limits mirror backend/schemas/middleware_schemas.py so errors show before saving.
const PII_TYPES = ['email', 'credit_card', 'ip', 'mac_address', 'url'] as const;

const PII_STRATEGIES = [
  'redact',
  'mask',
  'hash',
  'block',
] as const;

const GUARDRAIL_RULES = [
  { group: 'input', key: 'block_malicious_prompts' },
  { group: 'input', key: 'block_jailbreak' },
  { group: 'output', key: 'prevent_pii_leakage' },
  { group: 'output', key: 'block_toxic_biased' },
  { group: 'output', key: 'enforce_business_facts' },
] as const;

const DECISIONS = ['approve', 'edit', 'reject'] as const;
type Decision = typeof DECISIONS[number];
type InterruptEntry = [string, { allowed_decisions: Decision[] }];

const DEFAULT_CONFIG: Record<MiddlewareType, Record<string, any>> = {
  guardrails: {
    input: { block_malicious_prompts: true, block_jailbreak: true },
    output: { prevent_pii_leakage: true, block_toxic_biased: true, enforce_business_facts: true },
    custom_prompt: '',
  },
  pii: {
    pii_types: ['email', 'credit_card'],
    strategy: 'redact',
    apply_to_input: true,
    apply_to_output: true,
    apply_to_tool_results: true,
    llm_detector: { enabled: false, ai_service: 'agent_llm', extra_entities: [] },
  },
  human_in_the_loop: {
    interrupt_on: {}, description_prefix: 'Tool execution requires approval', approval_timeout_seconds: 3600,
  },
  model_call_limit: { max_calls: 25 },
  tool_call_limit: { max_calls: 50 },
  summarization: { summarization_model: 'agent_llm', trigger_tokens: null, keep_messages: 20, trim_tokens: null },
};

interface ToolOption {
  name: string;
  label: string;
  source: string;
}

interface MiddlewareFormProps {
  middleware?: Middleware | null;
  appId: number;
  onSubmit: (data: MiddlewarePayload) => Promise<void>;
  onCancel: () => void;
  /** Reports whether the form differs from what it opened with (unsaved changes). */
  onDirtyChange?: (dirty: boolean) => void;
}

const labelClass = 'block text-sm font-medium text-fg dark:text-fg-dark mb-1';

const inRange = (v: unknown, min: number, max: number) => Number.isInteger(v) && (v as number) >= min && (v as number) <= max;
const inOptionalRange = (v: unknown, min: number, max: number) => v == null || inRange(v, min, max);

/** Each validation error belongs to one field (or group of fields) of the form. */
type FieldKey =
  | 'name' | 'max_calls'
  | 'trigger_tokens' | 'keep_messages' | 'trim_tokens'
  | 'pii_types' | 'pii_targets'
  | 'approval_timeout' | 'approval_tools' | 'approval_decisions'
  | 'custom_prompt';

/** Field -> message. Insertion order follows the visual order of the form. */
type FieldErrors = Partial<Record<FieldKey, string>>;
/** For approval decisions the message alone isn't enough to locate it: keep the tool too. */
interface ValidationResult {
  errors: FieldErrors;
  decisionTool?: string;
}

function validateCallLimit(config: Record<string, any>, t: TFunction<'common'>): ValidationResult {
  return inRange(config.max_calls, 1, 10000) ? { errors: {} } : { errors: { max_calls: t('middlewareForm.validation.callLimit') } };
}

function validateSummarization(config: Record<string, any>, t: TFunction<'common'>): ValidationResult {
  const errors: FieldErrors = {};
  if (!inOptionalRange(config.trigger_tokens, 500, 1000000)) {
    errors.trigger_tokens = t('middlewareForm.validation.summarizationTrigger');
  }
  if (!inRange(config.keep_messages, 1, 500)) errors.keep_messages = t('middlewareForm.validation.keepMessages');
  if (!inOptionalRange(config.trim_tokens, 500, 1000000)) {
    errors.trim_tokens = t('middlewareForm.validation.trimTokens');
  }
  return { errors };
}

function validatePii(config: Record<string, any>, t: TFunction<'common'>): ValidationResult {
  const errors: FieldErrors = {};
  if (!config.pii_types?.length) errors.pii_types = t('middlewareForm.validation.selectPiiType');
  if (!config.apply_to_input && !config.apply_to_output && !config.apply_to_tool_results) {
    errors.pii_targets = t('middlewareForm.validation.selectPiiTarget');
  }
  return { errors };
}

function validateHumanApproval(config: Record<string, any>, t: TFunction<'common'>): ValidationResult {
  const errors: FieldErrors = {};
  let decisionTool: string | undefined;
  if (!inRange(config.approval_timeout_seconds ?? 3600, 60, 604800)) {
    errors.approval_timeout = t('middlewareForm.validation.approvalTimeout');
  }
  const tools = Object.entries(config.interrupt_on ?? {}) as Array<[string, { allowed_decisions: Decision[] }]>;
  if (tools.length === 0) {
    errors.approval_tools = t('middlewareForm.validation.selectApprovalTool');
  } else {
    const empty = tools.find(([, rule]) => rule.allowed_decisions.length === 0);
    if (empty) {
      decisionTool = empty[0];
      errors.approval_decisions = t('middlewareForm.validation.allowDecision', { tool: empty[0] });
    }
  }
  return { errors, decisionTool };
}

function validateGuardrails(config: Record<string, any>, t: TFunction<'common'>): ValidationResult {
  return (config.custom_prompt ?? '').length > 4000
    ? { errors: { custom_prompt: t('middlewareForm.validation.customRules') } }
    : { errors: {} };
}

const CONFIG_VALIDATORS: Record<MiddlewareType, (config: Record<string, any>, t: TFunction<'common'>) => ValidationResult> = {
  model_call_limit: validateCallLimit,
  tool_call_limit: validateCallLimit,
  summarization: validateSummarization,
  pii: validatePii,
  human_in_the_loop: validateHumanApproval,
  guardrails: validateGuardrails,
};

function validate(type: MiddlewareType, name: string, config: Record<string, any>, t: TFunction<'common'>): ValidationResult {
  const errors: FieldErrors = {};
  if (!name.trim()) errors.name = t('middlewareForm.validation.nameRequired');
  else if (name.trim().length > 100) errors.name = t('middlewareForm.validation.nameMaxLength');
  const configResult = CONFIG_VALIDATORS[type](config, t);
  return { errors: { ...errors, ...configResult.errors }, decisionTool: configResult.decisionTool };
}

/** Id of the control that receives focus for each field error. */
function focusTargetId(field: FieldKey, decisionTool?: string): string {
  switch (field) {
    case 'name': return 'mw-name';
    case 'max_calls': return 'mw-limit';
    case 'trigger_tokens': return 'mw-trigger';
    case 'keep_messages': return 'mw-keep';
    case 'trim_tokens': return 'mw-trim';
    case 'pii_types': return `mw-pii-type-${PII_TYPES[0]}`;
    case 'pii_targets': return 'mw-apply_to_input';
    case 'approval_timeout': return 'mw-approval-timeout';
    case 'approval_tools': return 'mw-custom-tool';
    case 'approval_decisions': return `mw-decision-${DECISIONS[0]}-${decisionTool ?? ''}`;
    case 'custom_prompt': return 'mw-custom-prompt';
  }
}

/** Id of the inline error message rendered under a group of checkboxes. */
const groupErrorId = (field: FieldKey) => `mw-${field}-error`;

/** `"ai_service:12"` -> 12; anything else (e.g. `agent_llm`) -> null. */
function savedServiceId(value: unknown): number | null {
  if (typeof value !== 'string' || !value.startsWith('ai_service:')) return null;
  const id = Number.parseInt(value.slice('ai_service:'.length), 10);
  return Number.isNaN(id) ? null : id;
}

function MiddlewareForm({ middleware, appId, onSubmit, onCancel, onDirtyChange }: Readonly<MiddlewareFormProps>) {
  const { t } = useTranslation('common');
  const isEditing = !!middleware;
  const [type, setType] = useState<MiddlewareType>(middleware?.middleware_type ?? 'guardrails');
  const [name, setName] = useState(middleware?.name ?? t('middlewaresPage.types.guardrails.label'));
  const [nameTouched, setNameTouched] = useState(isEditing);
  const [description, setDescription] = useState(middleware?.description ?? '');
  const [config, setConfig] = useState<Record<string, any>>(
    middleware ? { ...DEFAULT_CONFIG[middleware.middleware_type], ...middleware.config } : DEFAULT_CONFIG.guardrails,
  );
  /** Validation errors show only after the first save attempt; from then on they update live. */
  const [submitAttempted, setSubmitAttempted] = useState(false);
  /** Error returned by the server when saving — shown as a banner inside the panel. */
  const [serverError, setServerError] = useState<string | null>(null);
  const serverErrorRef = useRef<HTMLDivElement>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Bring the server error into view and move focus to it, so it can't go unnoticed.
  useEffect(() => {
    if (serverError) serverErrorRef.current?.focus();
  }, [serverError]);

  const [aiServices, setAiServices] = useState<AIService[]>([]);
  const [agentTools, setAgentTools] = useState<ToolOption[]>([]);
  const [mcpConfigs, setMcpConfigs] = useState<MCPConfig[]>([]);
  const [mcpTools, setMcpTools] = useState<Record<number, ToolOption[] | string>>({});
  const [loadingMcp, setLoadingMcp] = useState<number | null>(null);
  const [customTool, setCustomTool] = useState('');
  const [entitiesText, setEntitiesText] = useState<string>(
    (middleware?.config?.llm_detector?.extra_entities ?? []).join(', '),
  );

  useEffect(() => {
    if (!nameTouched) setName(t(`middlewaresPage.types.${type}.label`));
  }, [nameTouched, t, type]);

  // Unsaved changes = the editable values differ from the ones the form opened with.
  // Setting a value back to what it was no longer counts as a change.
  const snapshot = JSON.stringify({ type, name, description, config, entitiesText });
  const [initialSnapshot] = useState(snapshot);
  const isDirty = snapshot !== initialSnapshot;
  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const needsServices = type === 'summarization' || type === 'pii';
  useEffect(() => {
    if (!needsServices) return;
    // Only this app's services can be referenced (validated by the backend too).
    apiService.getAIServices(appId).then((list) => setAiServices(list.filter((s) => !s.is_system))).catch(() => setAiServices([]));
  }, [appId, needsServices]);

  useEffect(() => {
    if (type !== 'human_in_the_loop') return;
    apiService.getAgents(appId)
      .then((agents) => setAgentTools(agents.filter((a) => a.is_tool).map((a) => ({
        name: agentToolName(a.name), label: a.name, source: 'Agent used as a tool',
      }))))
      .catch(() => setAgentTools([]));
    apiService.getMCPConfigs(appId).then(setMcpConfigs).catch(() => setMcpConfigs([]));
  }, [appId, type]);

  const selectType = (next: MiddlewareType) => {
    setType(next);
    setConfig(DEFAULT_CONFIG[next]);
    setSubmitAttempted(false);
  };

  const patch = (changes: Record<string, any>) => setConfig((prev) => ({ ...prev, ...changes }));
  const patchGroup = (group: string, changes: Record<string, any>) =>
    setConfig((prev) => ({ ...prev, [group]: { ...prev[group], ...changes } }));
  const numberValue = (raw: string) => (raw === '' ? '' : Number(raw));
  const optionalNumberValue = (raw: string) => (raw === '' ? null : Number(raw));

  const loadMcpTools = async (cfg: MCPConfig) => {
    setLoadingMcp(cfg.config_id);
    try {
      const result = await apiService.testMCPConnection(appId, cfg.config_id);
      setMcpTools((prev) => ({
        ...prev,
        [cfg.config_id]: result.status === 'success'
          ? (result.tools ?? []).map((t) => ({ name: t.name, label: t.name, source: cfg.name }))
          : result.message || t('middlewareForm.mcp.connectionFailed'),
      }));
    } catch (err) {
      setMcpTools((prev) => ({
        ...prev,
        [cfg.config_id]: err instanceof Error ? err.message : t('middlewareForm.mcp.loadToolsFailed'),
      }));
    } finally {
      setLoadingMcp(null);
    }
  };

  const interruptOn: Record<string, { allowed_decisions: Decision[] }> = config.interrupt_on ?? {};
  const toggleTool = (toolName: string) => {
    const next = { ...interruptOn };
    if (next[toolName]) delete next[toolName];
    else next[toolName] = { allowed_decisions: ['approve', 'reject'] };
    patch({ interrupt_on: next });
  };
  const toggleDecision = (toolName: string, decision: Decision) => {
    const current = interruptOn[toolName].allowed_decisions;
    const allowed = current.includes(decision) ? current.filter((d) => d !== decision) : [...current, decision];
    patch({ interrupt_on: { ...interruptOn, [toolName]: { allowed_decisions: DECISIONS.filter((d) => allowed.includes(d)) } } });
  };
  const addCustomTool = () => {
    const toolName = customTool.trim();
    if (toolName && !interruptOn[toolName]) toggleTool(toolName);
    setCustomTool('');
  };

  const buildPayloadConfig = () => (type === 'pii'
    ? {
      ...config,
      llm_detector: {
        ...config.llm_detector,
        extra_entities: entitiesText.split(',').map((e) => e.trim()).filter(Boolean),
      },
    }
    : config);

  const validation = validate(type, name, buildPayloadConfig(), t);
  const fieldErrors: FieldErrors = submitAttempted ? validation.errors : {};
  const errorFields = Object.keys(fieldErrors) as FieldKey[];
  const focusField = (field: FieldKey) => {
    document.getElementById(focusTargetId(field, validation.decisionTool))?.focus();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payloadConfig = buildPayloadConfig();
    setSubmitAttempted(true);
    const firstInvalid = (Object.keys(validation.errors) as FieldKey[])[0];
    if (firstInvalid) {
      // Take the user to the first field to fix, even if it's out of view in the panel.
      focusField(firstInvalid);
      return;
    }
    setServerError(null);
    setIsSubmitting(true);
    try {
      await onSubmit({ name: name.trim(), description: description.trim(), middleware_type: type, config: payloadConfig });
    } catch (err) {
      setServerError(err instanceof Error && err.message ? err.message : t('middlewaresPage.saveFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const serviceSelect = (id: string, label: string, value: string, savedValue: unknown, onChange: (v: string) => void) => (
    <>
      <FormSelect
        id={id}
        label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        options={[
          { value: 'agent_llm', label: t('middlewareForm.agentModel') },
          ...selectableServiceOptions(aiServices, savedServiceId(savedValue)).map((service) => ({
            value: `ai_service:${service.service_id}`,
            label: serviceOptionLabel(service, `${service.name} (${service.provider} · ${service.model_name})`),
          })),
        ]}
        disabled={isSubmitting}
        ariaDescribedBy={serviceStatusId(aiServices, savedServiceId(value), id)}
      />
      <ServiceOptionStatus selectId={id} options={aiServices} selectedId={savedServiceId(value)} />
    </>
  );

  /** Inline error under a group of checkboxes (the group points to it with aria-describedby). */
  const groupError = (field: FieldKey) => (fieldErrors[field] ? (
    <p id={groupErrorId(field)} className="mt-2 text-xs text-error dark:text-error-dark">{fieldErrors[field]}</p>
  ) : null);
  const groupDescribedBy = (field: FieldKey) => (fieldErrors[field] ? groupErrorId(field) : undefined);

  const knownTools: ToolOption[] = [
    ...agentTools,
    ...Object.values(mcpTools).flatMap((v) => (Array.isArray(v) ? v : [])),
  ];
  const extraSelected = Object.keys(interruptOn).filter((t) => !knownTools.some((k) => k.name === t));

  return (
    <form onSubmit={handleSubmit} className="space-y-6 px-4 pt-3" noValidate>
      <h2 className="font-display text-[21px] font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">
        {t(isEditing ? 'middlewaresPage.editTitle' : 'middlewaresPage.createTitle')}
      </h2>

      {serverError && (
        <div ref={serverErrorRef} tabIndex={-1} className="scroll-mt-4 rounded-lg outline-none">
          <Alert type="error" title={t('middlewaresPage.saveFailed')} message={serverError} />
        </div>
      )}

      {/* Validation summary: only with 2+ errors; each item takes the user to its field */}
      {errorFields.length >= 2 && (
        <Alert
          type="error"
          title={t('middlewareForm.validation.summaryTitle', { count: errorFields.length })}
          message={(
            <ul className="list-disc space-y-1 pl-4">
              {errorFields.map((field) => (
                <li key={field}>
                  <button
                    type="button"
                    onClick={() => focusField(field)}
                    className="text-left underline underline-offset-2"
                  >
                    {fieldErrors[field]}
                  </button>
                </li>
              ))}
            </ul>
          )}
        />
      )}

      {/* Type */}
      {isEditing ? (
        <div>
          <p className={labelClass}>{t('middlewareForm.type')}</p>
          <CardApp variant="selected" className="gap-1">
            <p className="text-sm font-medium text-fg dark:text-fg-dark">
              {t(`middlewaresPage.types.${type}.label`)}
            </p>
            <p className="text-xs font-normal text-fg-secondary dark:text-fg-secondary-dark">
              {t(`middlewaresPage.types.${type}.description`)}
            </p>
          </CardApp>
        </div>
      ) : (
        <fieldset>
          <legend className={labelClass}>{t('middlewareForm.whatShouldItDo')}</legend>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {MIDDLEWARE_TYPES.map((value) => (
              <ButtonCard
                key={value}
                variant="selectable-radio"
                selected={type === value}
                radioName="middleware_type"
                radioValue={value}
                ariaLabel={t(`middlewaresPage.types.${value}.label`)}
                onClick={() => {
                  if (type !== value) selectType(value);
                }}
              >
                <span className="min-w-0 text-sm font-medium text-fg dark:text-fg-dark">
                  {t(`middlewaresPage.types.${value}.label`)}
                  <span className="block text-xs font-normal text-fg-secondary dark:text-fg-secondary-dark">
                    {t(`middlewaresPage.types.${value}.description`)}
                  </span>
                </span>
              </ButtonCard>
            ))}
          </div>
        </fieldset>
      )}

      {/* Name / description */}
      <div className="grid grid-cols-1 gap-4">
        <FormField
          id="mw-name"
          label={t('middlewareForm.name')}
          value={name}
          maxLength={100}
          onChange={(e) => { setName(e.target.value); setNameTouched(true); }}
          disabled={isSubmitting}
          required
          error={fieldErrors.name}
        />
        <FormField
          id="mw-description"
          label={t('middlewareForm.description')}
          value={description}
          maxLength={1000}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t('middlewareForm.descriptionPlaceholder')}
          disabled={isSubmitting}
        />
      </div>

      {/* Call limits */}
      {(type === 'model_call_limit' || type === 'tool_call_limit') && (
        <div>
          <FormField
            id="mw-limit"
            type="number"
            label={t(type === 'model_call_limit'
              ? 'middlewareForm.limits.modelCalls'
              : 'middlewareForm.limits.toolCalls')}
            min={1}
            max={10000}
            step={1}
            value={config.max_calls}
            onChange={(e) => patch({ max_calls: numberValue(e.target.value) })}
            disabled={isSubmitting}
            error={fieldErrors.max_calls}
          />
          <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {type === 'model_call_limit'
              ? t('middlewareForm.limits.modelCallsHelp')
              : t('middlewareForm.limits.toolCallsHelp')}
          </p>
        </div>
      )}

      {/* Summarization */}
      {type === 'summarization' && (
        <div className="space-y-4">
          <div>
            {serviceSelect('mw-sum-model', t('middlewareForm.summarization.model'), config.summarization_model, middleware?.config?.summarization_model, (v) => patch({ summarization_model: v }))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <FormField id="mw-trigger" type="number" label={t('middlewareForm.summarization.trigger')} min={500} step={500}
                value={config.trigger_tokens ?? ''} placeholder={t('middlewareForm.summarization.automatic')} ariaDescribedBy="mw-sum-help"
                onChange={(e) => patch({ trigger_tokens: optionalNumberValue(e.target.value) })} disabled={isSubmitting}
                error={fieldErrors.trigger_tokens} />
            </div>
            <div>
              <FormField id="mw-keep" type="number" label={t('middlewareForm.summarization.keepMessages')} min={1} max={500} value={config.keep_messages}
                onChange={(e) => patch({ keep_messages: numberValue(e.target.value) })} disabled={isSubmitting}
                error={fieldErrors.keep_messages} />
            </div>
            <div>
              <FormField id="mw-trim" type="number" label={t('middlewareForm.summarization.maxTokens')} min={500} step={500}
                value={config.trim_tokens ?? ''} placeholder={t('middlewareForm.summarization.noLimit')} ariaDescribedBy="mw-sum-help"
                onChange={(e) => patch({ trim_tokens: optionalNumberValue(e.target.value) })} disabled={isSubmitting}
                error={fieldErrors.trim_tokens} />
            </div>
          </div>
          <p id="mw-sum-help" className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {t('middlewareForm.summarization.help')}
          </p>
        </div>
      )}

      {/* PII */}
      {type === 'pii' && (
        <div className="space-y-4">
          <fieldset aria-describedby={groupDescribedBy('pii_types')}>
            <CardApp className="space-y-4">
            <legend className={labelClass}>{t('middlewareForm.pii.detect')}</legend>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {PII_TYPES.map((piiType) => (
                <FormField
                  key={piiType}
                  id={`mw-pii-type-${piiType}`}
                  type="checkbox"
                  label={t(`middlewareForm.pii.types.${piiType}`)}
                  checked={config.pii_types.includes(piiType)}
                  disabled={isSubmitting}
                  className="flex items-center gap-2"
                  onChange={() => patch({
                      pii_types: config.pii_types.includes(piiType)
                        ? config.pii_types.filter((v: string) => v !== piiType)
                        : [...config.pii_types, piiType],
                  })}
                />
              ))}
            </div>
            {groupError('pii_types')}
            </CardApp>
          </fieldset>
          <div>
            <label htmlFor="mw-strategy" className={labelClass}>{t('middlewareForm.pii.whenFound')}</label>
              <FormSelect
                id="mw-strategy"
                label={t('middlewareForm.pii.whenFound')}
                value={config.strategy}
                onChange={(e) => patch({ strategy: e.target.value })}
                options={PII_STRATEGIES.map((strategy) => ({
                  value: strategy,
                  label: t('middlewareForm.pii.strategies.' + strategy + '.label')
                    + ' — '
                    + t('middlewareForm.pii.strategies.' + strategy + '.hint'),
                }))}
                disabled={isSubmitting}
              />
          </div>
          <fieldset aria-describedby={groupDescribedBy('pii_targets')}>
            <CardApp className="space-y-4">
            <legend className={labelClass}>{t('middlewareForm.pii.applyTo')}</legend>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              {[
                ['apply_to_input', 'middlewareForm.pii.userMessages'],
                ['apply_to_tool_results', 'middlewareForm.pii.toolResults'],
                ['apply_to_output', 'middlewareForm.pii.agentAnswers'],
              ].map(([key, labelKey]) => (
                <FormField
                  key={key}
                  id={`mw-${key}`}
                  type="checkbox"
                  label={t(labelKey)}
                  checked={!!config[key]}
                  onChange={(e) => patch({ [key]: e.target.checked })}
                  disabled={isSubmitting}
                  className="flex items-center gap-2"
                />
              ))}
            </div>
            {config.apply_to_output && (
              <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
                {t('middlewareForm.pii.answersComplete')}
              </p>
            )}
            {groupError('pii_targets')}
            </CardApp>
          </fieldset>
          
          <div className="rounded-lg border border-line p-3 space-y-3 dark:border-line-dark">
            <FormField
              id="mw-pii-llm-detector"
              type="checkbox"
              label={t('middlewareForm.pii.llmDetector')}
              checked={!!config.llm_detector?.enabled}
              disabled={isSubmitting}
              onChange={(e) => patchGroup('llm_detector', { enabled: e.target.checked })}
              className="flex items-center gap-2"
            />
            {config.llm_detector?.enabled && (
              <>
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                  {t('middlewareForm.pii.extraModelCall')}
                </p>
                <div>
                  {serviceSelect('mw-pii-model', t('middlewareForm.pii.detectionModel'), config.llm_detector.ai_service, middleware?.config?.llm_detector?.ai_service, (v) => patchGroup('llm_detector', { ai_service: v }))}
                </div>
                <div>
                  <FormField id="mw-pii-entities" label={t('middlewareForm.pii.extraTypes')} disabled={isSubmitting}
                    placeholder={t('middlewareForm.pii.extraTypesPlaceholder')} value={entitiesText}
                    onChange={(e) => setEntitiesText(e.target.value)} />
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Human approval */}
      {type === 'human_in_the_loop' && (
        <div className="space-y-4">
          <Alert
            type="info"
            message={t('middlewareForm.approval.info')}
          />
          <div>
            <FormField
              id="mw-approval-timeout" type="number" min={1} max={10080} step={1}
              label={t('middlewareForm.approval.timeToAnswer')}
              value={
                typeof config.approval_timeout_seconds === 'number'
                  ? Math.round(config.approval_timeout_seconds / 60)
                  : 60
              }
              onChange={(e) => {
                const minutes = numberValue(e.target.value);
                patch({ approval_timeout_seconds: minutes === '' ? '' : minutes * 60 });
              }}
              disabled={isSubmitting} ariaDescribedBy="mw-approval-timeout-help"
              error={fieldErrors.approval_timeout}
            />
            <p id="mw-approval-timeout-help" className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
              {t('middlewareForm.approval.timeoutHelp')}
            </p>
          </div>
          <fieldset className="space-y-2">
            <legend className={labelClass}>{t('middlewareForm.approval.agentsAsTools')}</legend>
            {agentTools.length === 0 && (
              <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('middlewareForm.approval.noAgents')}</p>
            )}
            {agentTools.map((tool) => (
              <FormField
                key={tool.name}
                id={`mw-agent-tool-${tool.name}`}
                type="checkbox"
                label={<>{tool.label} <code className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{tool.name}</code></>}
                checked={!!interruptOn[tool.name]}
                onChange={() => toggleTool(tool.name)}
                disabled={isSubmitting}
                className="flex items-center gap-2"
              />
            ))}
          </fieldset>
          <fieldset className="space-y-2">
            <legend className={labelClass}>{t('middlewareForm.approval.mcpTools')}</legend>
            {mcpConfigs.length === 0 && (
              <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('middlewareForm.approval.noMcpServers')}</p>
            )}
            {mcpConfigs.map((cfg) => {
              const tools = mcpTools[cfg.config_id];
              return (
                <div key={cfg.config_id} className="rounded-lg border border-line p-3 dark:border-line-dark">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-fg truncate dark:text-fg-dark">{cfg.name}</span>
                    {!Array.isArray(tools) && (
                      <button type="button" onClick={() => void loadMcpTools(cfg)} disabled={loadingMcp !== null}
                        className="shrink-0 text-xs px-2 py-1 rounded border border-line-strong text-fg-secondary hover:bg-surface-hover disabled:opacity-50 dark:border-line-strong-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark">
                        {loadingMcp === cfg.config_id
                          ? t('middlewareForm.approval.loadingTools')
                          : t('middlewareForm.approval.showTools')}
                      </button>
                    )}
                  </div>
                  {typeof tools === 'string' && <p className="mt-1 text-xs text-error dark:text-error-dark">{tools}</p>}
                  {Array.isArray(tools) && tools.length === 0 && (
                    <p className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('middlewareForm.approval.noTools')}</p>
                  )}
                  {Array.isArray(tools) && tools.map((tool) => (
                    <FormField
                      key={tool.name}
                      id={`mw-mcp-tool-${cfg.config_id}-${tool.name}`}
                      type="checkbox"
                      label={<code className="text-xs">{tool.name}</code>}
                      checked={!!interruptOn[tool.name]}
                      onChange={() => toggleTool(tool.name)}
                      disabled={isSubmitting}
                      className="mt-1 flex items-center gap-2"
                    />
                  ))}
                </div>
              );
            })}
          </fieldset>
          <div>
            <div className="flex gap-2">
              <FormField id="mw-custom-tool" label={t('middlewareForm.approval.otherTool')} className="min-w-0 flex-1" value={customTool} onChange={(e) => setCustomTool(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomTool(); } }}
                placeholder={t('middlewareForm.approval.otherToolPlaceholder')} disabled={isSubmitting}
                ariaDescribedBy={groupDescribedBy('approval_tools')} />
              <ButtonApp
                type="button"
                label={t('middlewareForm.approval.addTool')}
                onClick={addCustomTool}
                disabled={!customTool.trim() || isSubmitting}
                variant="primary"
                size="control"
                className="shrink-0 self-end"
              />
            </div>
            <div className="mt-2 grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-3">
              {extraSelected.map((toolName) => (
                <FormField
                  key={toolName}
                  id={`mw-extra-tool-${toolName}`}
                  type="checkbox"
                  label={toolName}
                  checked
                  onChange={() => toggleTool(toolName)}
                  className="flex items-center gap-2"
                />
              ))}
            </div>
            {groupError('approval_tools')}
          </div>

          {Object.keys(interruptOn).length > 0 && (
            <div>
              <p className={labelClass}>{t('middlewareForm.approval.reviewerActions')}</p>
              <Table
                data={Object.entries(interruptOn)}
                keyExtractor={([toolName]) => toolName}
                columns={[
                  {
                    header: t('middlewareForm.approval.toolColumn'),
                    accessor: ([toolName]) => toolName,
                    className: 'px-2 py-1 text-left text-xs text-fg dark:text-fg-dark',
                  },
                  ...DECISIONS.map((decision) => ({
                    header: t(`middlewareForm.approval.decisions.${decision}`),
                    headerClassName: 'text-center',
                    className: 'px-2 py-1 text-center',
                    render: ([toolName, rule]: InterruptEntry) => (
                      <FormField
                        id={`mw-decision-${decision}-${toolName}`}
                        type="checkbox"
                        checked={rule.allowed_decisions.includes(decision)}
                        onChange={() => toggleDecision(toolName, decision)}
                        disabled={isSubmitting}
                        ariaLabel={t('middlewareForm.approval.decisionAria', {
                          decision: t(`middlewareForm.approval.decisions.${decision}`),
                          tool: toolName,
                        })}
                        className="flex justify-center"
                      />
                    ),
                  })),
                ]}
              />
              {groupError('approval_decisions')}
            </div>
          )}
        </div>
      )}

      {/* Guardrails */}
      {type === 'guardrails' && (
        <div className="space-y-4">
          <fieldset className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
            <legend className={labelClass}>{t('middlewareForm.guardrails.rulesTitle')}</legend>
            {GUARDRAIL_RULES.map((rule) => (
              <FormField
                key={rule.key}
                id={`mw-guardrail-${rule.key}`}
                type="checkbox"
                label={t(`middlewareForm.guardrails.rules.${rule.key}`)}
                checked={config[rule.group]?.[rule.key] !== false}
                disabled={isSubmitting}
                onChange={(e) => patchGroup(rule.group, { [rule.key]: e.target.checked })}
                className="flex items-center gap-2"
              />
            ))}
          </fieldset>
          <div>
            <FormTextArea
              id="mw-custom-prompt"
              label={t('middlewareForm.guardrails.additionalRules')}
              rows={4}
              maxLength={4000}
              value={config.custom_prompt ?? ''}
              onChange={(e) => patch({ custom_prompt: e.target.value })}
              disabled={isSubmitting}
              placeholder={t('middlewareForm.guardrails.additionalRulesPlaceholder')}
              error={fieldErrors.custom_prompt}
            />
          </div>
          <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {t('middlewareForm.guardrails.help')}
          </p>
        </div>
      )}

      {/* Fixed footer: sticks to the bottom of the side panel's scroll area while the body scrolls */}
      <div className="sticky -bottom-4 z-10 -mx-[1.625rem] -mb-4 border-t border-line bg-surface px-[1.625rem] py-4 dark:border-line-dark dark:bg-surface-dark">
        <FormActions
          onCancel={onCancel}
          isSubmitting={isSubmitting}
          isEditing={isEditing}
          submitDisabled={isEditing && !isDirty}
          containerClassName="!border-t-0 !pt-0"
        />
      </div>
    </form>
  );
}

export default MiddlewareForm;
