import { useEffect, useState } from 'react';
import { apiService, type AIService } from '../../services/api';
import { ServiceOptionStatus, serviceStatusId } from '../ui/ServiceOptionStatus';
import type { MCPConfig, Middleware, MiddlewarePayload, MiddlewareType } from '../../core/types';
import { MIDDLEWARE_TYPES, MIDDLEWARE_TYPE_INFO, agentToolName } from '../../constants/middlewares';
import { selectableServiceOptions, serviceOptionLabel } from '../../utils/serviceLifecycle';
import FormActions from '../ui/FormActions';
import { ButtonCard } from '../ui/ButtonCard';
import { FormField, FormSelect, FormTextArea } from '../ui/FormField';
import CardApp from '../ui/CardApp';

// Limits mirror backend/schemas/middleware_schemas.py so errors show before saving.
const PII_TYPES = [
  { value: 'email', label: 'Email addresses' },
  { value: 'credit_card', label: 'Credit card numbers' },
  { value: 'ip', label: 'IP addresses' },
  { value: 'mac_address', label: 'MAC addresses' },
  { value: 'url', label: 'URLs' },
] as const;

const PII_STRATEGIES = [
  { value: 'redact', label: 'Redact', hint: 'Replace with [REDACTED_EMAIL]' },
  { value: 'mask', label: 'Mask', hint: 'Keep the last characters, e.g. ****-1234' },
  { value: 'hash', label: 'Hash', hint: 'Replace with a stable hash' },
  { value: 'block', label: 'Block', hint: 'Stop the run when personal data is found' },
] as const;

const GUARDRAIL_RULES = [
  { group: 'input', key: 'block_malicious_prompts', label: 'Refuse harmful or malicious requests' },
  { group: 'input', key: 'block_jailbreak', label: 'Resist jailbreak and prompt-injection attempts' },
  { group: 'output', key: 'prevent_pii_leakage', label: 'Do not reveal personal data' },
  { group: 'output', key: 'block_toxic_biased', label: 'No toxic or biased language' },
  { group: 'output', key: 'enforce_business_facts', label: 'Do not make up facts' },
] as const;

const DECISIONS = ['approve', 'edit', 'reject'] as const;
type Decision = typeof DECISIONS[number];

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
}

const labelClass = 'block text-sm font-medium text-gray-700 mb-1';
const inputClass =
  'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500';

const inRange = (v: unknown, min: number, max: number) => Number.isInteger(v) && (v as number) >= min && (v as number) <= max;
const inOptionalRange = (v: unknown, min: number, max: number) => v == null || inRange(v, min, max);

function validateCallLimit(config: Record<string, any>): string | null {
  return inRange(config.max_calls, 1, 10000) ? null : 'The limit must be a whole number between 1 and 10,000.';
}

function validateSummarization(config: Record<string, any>): string | null {
  if (!inOptionalRange(config.trigger_tokens, 500, 1000000)) {
    return 'Trigger must be between 500 and 1,000,000 tokens, or empty for automatic.';
  }
  if (!inRange(config.keep_messages, 1, 500)) return 'Messages to keep must be between 1 and 500.';
  if (!inOptionalRange(config.trim_tokens, 500, 1000000)) {
    return 'Tokens to summarize must be between 500 and 1,000,000, or empty for no limit.';
  }
  return null;
}

function validatePii(config: Record<string, any>): string | null {
  if (!config.pii_types?.length) return 'Select at least one type of personal data.';
  if (!config.apply_to_input && !config.apply_to_output && !config.apply_to_tool_results) {
    return 'Apply the protection to at least one of: user messages, tool results or answers.';
  }
  return null;
}

function validateHumanApproval(config: Record<string, any>): string | null {
  const tools = Object.entries(config.interrupt_on ?? {}) as Array<[string, { allowed_decisions: Decision[] }]>;
  if (tools.length === 0) return 'Select at least one tool that needs approval.';
  const empty = tools.find(([, rule]) => rule.allowed_decisions.length === 0);
  if (empty) return `Allow at least one decision for "${empty[0]}".`;
  return inRange(config.approval_timeout_seconds ?? 3600, 60, 604800)
    ? null
    : 'The approval time limit must be between 1 minute and 7 days.';
}

function validateGuardrails(config: Record<string, any>): string | null {
  return (config.custom_prompt ?? '').length > 4000 ? 'Additional rules must be at most 4,000 characters.' : null;
}

const CONFIG_VALIDATORS: Record<MiddlewareType, (config: Record<string, any>) => string | null> = {
  model_call_limit: validateCallLimit,
  tool_call_limit: validateCallLimit,
  summarization: validateSummarization,
  pii: validatePii,
  human_in_the_loop: validateHumanApproval,
  guardrails: validateGuardrails,
};

function validate(type: MiddlewareType, name: string, config: Record<string, any>): string | null {
  if (!name.trim()) return 'Name is required.';
  if (name.trim().length > 100) return 'Name must be at most 100 characters.';
  return CONFIG_VALIDATORS[type](config);
}

/** `"ai_service:12"` -> 12; anything else (e.g. `agent_llm`) -> null. */
function savedServiceId(value: unknown): number | null {
  if (typeof value !== 'string' || !value.startsWith('ai_service:')) return null;
  const id = Number.parseInt(value.slice('ai_service:'.length), 10);
  return Number.isNaN(id) ? null : id;
}

function MiddlewareForm({ middleware, appId, onSubmit, onCancel }: Readonly<MiddlewareFormProps>) {
  const isEditing = !!middleware;
  const [type, setType] = useState<MiddlewareType>(middleware?.middleware_type ?? 'guardrails');
  const [name, setName] = useState(middleware?.name ?? MIDDLEWARE_TYPE_INFO.guardrails.label);
  const [nameTouched, setNameTouched] = useState(isEditing);
  const [description, setDescription] = useState(middleware?.description ?? '');
  const [config, setConfig] = useState<Record<string, any>>(
    middleware ? { ...DEFAULT_CONFIG[middleware.middleware_type], ...middleware.config } : DEFAULT_CONFIG.guardrails,
  );
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [aiServices, setAiServices] = useState<AIService[]>([]);
  const [agentTools, setAgentTools] = useState<ToolOption[]>([]);
  const [mcpConfigs, setMcpConfigs] = useState<MCPConfig[]>([]);
  const [mcpTools, setMcpTools] = useState<Record<number, ToolOption[] | string>>({});
  const [loadingMcp, setLoadingMcp] = useState<number | null>(null);
  const [customTool, setCustomTool] = useState('');
  const [entitiesText, setEntitiesText] = useState<string>(
    (middleware?.config?.llm_detector?.extra_entities ?? []).join(', '),
  );

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
    if (!nameTouched) setName(MIDDLEWARE_TYPE_INFO[next].label);
    setError(null);
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
          : result.message || 'Could not connect to this MCP server.',
      }));
    } catch (err) {
      setMcpTools((prev) => ({ ...prev, [cfg.config_id]: err instanceof Error ? err.message : 'Could not load tools.' }));
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payloadConfig = type === 'pii'
      ? {
        ...config,
        llm_detector: {
          ...config.llm_detector,
          extra_entities: entitiesText.split(',').map((e) => e.trim()).filter(Boolean),
        },
      }
      : config;
    const message = validate(type, name, payloadConfig);
    if (message) {
      setError(message);
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await onSubmit({ name: name.trim(), description: description.trim(), middleware_type: type, config: payloadConfig });
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
          { value: 'agent_llm', label: "The agent's own model" },
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

  const knownTools: ToolOption[] = [
    ...agentTools,
    ...Object.values(mcpTools).flatMap((v) => (Array.isArray(v) ? v : [])),
  ];
  const extraSelected = Object.keys(interruptOn).filter((t) => !knownTools.some((k) => k.name === t));

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3" role="alert">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}

      {/* Type */}
      {isEditing ? (
        <div>
          <p className={labelClass}>Type</p>
          <p className="text-sm text-gray-900">{MIDDLEWARE_TYPE_INFO[type].label}</p>
          <p className="text-xs text-gray-500">{MIDDLEWARE_TYPE_INFO[type].description}</p>
        </div>
      ) : (
        <fieldset>
          <legend className={labelClass}>What should it do?</legend>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {MIDDLEWARE_TYPES.map((value) => (
              <ButtonCard
                key={value}
                variant="selectable-radio"
                selected={type === value}
                radioName="middleware_type"
                radioValue={value}
                ariaLabel={MIDDLEWARE_TYPE_INFO[value].label}
                onClick={() => {
                  if (type !== value) selectType(value);
                }}
              >
                <span className="min-w-0 text-sm font-medium text-fg dark:text-fg-dark">
                  {MIDDLEWARE_TYPE_INFO[value].label}
                  <span className="block text-xs font-normal text-fg-secondary   dark:text-fg-secondary-dark">{MIDDLEWARE_TYPE_INFO[value].description}</span>
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
          label="Name"
          value={name}
          maxLength={100}
          onChange={(e) => { setName(e.target.value); setNameTouched(true); }}
          disabled={isSubmitting}
          required
        />
        <FormField
          id="mw-description"
          label="Description"
          value={description}
          maxLength={1000}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Shown when choosing middlewares for an agent"
          disabled={isSubmitting}
        />
      </div>

      {/* Call limits */}
      {(type === 'model_call_limit' || type === 'tool_call_limit') && (
        <div>
          <FormField
            id="mw-limit"
            type="number"
            label={type === 'model_call_limit' ? 'Maximum LLM calls per run' : 'Maximum tool calls per run'}
            min={1}
            max={10000}
            step={1}
            value={config.max_calls}
            onChange={(e) => patch({ max_calls: numberValue(e.target.value) })}
            disabled={isSubmitting}
          />
          <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {type === 'model_call_limit'
              ? 'When reached, the run stops and the user gets the answer produced so far.'
              : 'Calls over the limit are not executed; the agent is told the limit was reached.'}
          </p>
        </div>
      )}

      {/* Summarization */}
      {type === 'summarization' && (
        <div className="space-y-4">
          <div>
            {serviceSelect('mw-sum-model', 'Model used to summarize', config.summarization_model, middleware?.config?.summarization_model, (v) => patch({ summarization_model: v }))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <FormField id="mw-trigger" type="number" label="Summarize after (tokens)" min={500} step={500}
                value={config.trigger_tokens ?? ''} placeholder="Automatic" ariaDescribedBy="mw-sum-help"
                onChange={(e) => patch({ trigger_tokens: optionalNumberValue(e.target.value) })} disabled={isSubmitting} />
            </div>
            <div>
              <FormField id="mw-keep" type="number" label="Recent messages to keep" min={1} max={500} value={config.keep_messages}
                onChange={(e) => patch({ keep_messages: numberValue(e.target.value) })} disabled={isSubmitting} />
            </div>
            <div>
              <FormField id="mw-trim" type="number" label="Max tokens to summarize" min={500} step={500}
                value={config.trim_tokens ?? ''} placeholder="No limit" ariaDescribedBy="mw-sum-help"
                onChange={(e) => patch({ trim_tokens: optionalNumberValue(e.target.value) })} disabled={isSubmitting} />
            </div>
          </div>
          <p id="mw-sum-help" className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
            Leave the trigger empty to summarize at 85% of the model's context window (at most 150,000 tokens),
            and the last field empty to summarize the whole older history. Agents with memory and no summarization
            middleware use these same defaults.
          </p>
        </div>
      )}

      {/* PII */}
      {type === 'pii' && (
        <div className="space-y-4">
          <fieldset>
            <CardApp className="space-y-4">
            <legend className={labelClass}>Personal data to detect</legend>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {PII_TYPES.map((t) => (
                <FormField
                  key={t.value}
                  id={`mw-pii-type-${t.value}`}
                  type="checkbox"
                  label={t.label}
                  checked={config.pii_types.includes(t.value)}
                  disabled={isSubmitting}
                  className="flex items-center gap-2"
                  onChange={() => patch({
                      pii_types: config.pii_types.includes(t.value)
                        ? config.pii_types.filter((v: string) => v !== t.value)
                        : [...config.pii_types, t.value],
                  })}
                />
              ))}
            </div>
            </CardApp>
          </fieldset>
          <div>
            <label htmlFor="mw-strategy" className={labelClass}>When found</label>
            <select id="mw-strategy" value={config.strategy} onChange={(e) => patch({ strategy: e.target.value })}
              className={inputClass} disabled={isSubmitting}>
              {PII_STRATEGIES.map((s) => <option key={s.value} value={s.value}>{s.label} — {s.hint}</option>)}
            </select>
          </div>
          <fieldset>
            <CardApp className="space-y-4">
            <legend className={labelClass}>Apply to</legend>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              {[
                ['apply_to_input', 'User messages'],
                ['apply_to_tool_results', 'Tool results'],
                ['apply_to_output', 'Agent answers'],
              ].map(([key, label]) => (
                <FormField
                  key={key}
                  id={`mw-${key}`}
                  type="checkbox"
                  label={label}
                  checked={!!config[key]}
                  onChange={(e) => patch({ [key]: e.target.checked })}
                  disabled={isSubmitting}
                  className="flex items-center gap-2"
                />
              ))}
            </div>
            {config.apply_to_output && (
              <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">Answers are shown once complete instead of word by word, so nothing is displayed before it is checked.</p>
            )}
            </CardApp>
          </fieldset>
          
          <div className="rounded-lg border border-gray-200 p-3 space-y-3">
            <FormField
              id="mw-pii-llm-detector"
              type="checkbox"
              label="Also detect names, addresses and other data with an LLM"
              checked={!!config.llm_detector?.enabled}
              disabled={isSubmitting}
              onChange={(e) => patchGroup('llm_detector', { enabled: e.target.checked })}
              className="flex items-center gap-2"
            />
            {config.llm_detector?.enabled && (
              <>
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">Adds one extra model call per message checked.</p>
                <div>
                  {serviceSelect('mw-pii-model', 'Detection model', config.llm_detector.ai_service, middleware?.config?.llm_detector?.ai_service, (v) => patchGroup('llm_detector', { ai_service: v }))}
                </div>
                <div>
                  <FormField id="mw-pii-entities" label="Extra data types (comma separated)" disabled={isSubmitting}
                    placeholder="person name, postal address, national ID" value={entitiesText}
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
          <p className="text-sm text-gray-700">
            Choose the tools that need a person's approval. Agents using this middleware keep conversation memory on.
            Approvals are given from the chat, or by the application calling the agent through the API.
          </p>
          <div>
            <FormField
              id="mw-approval-timeout" type="number" min={1} max={10080} step={1}
              label="Time to answer (minutes)"
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
            />
            <p id="mw-approval-timeout-help" className="mt-1 text-xs text-gray-500">
              Requests nobody answers in time are rejected: the tool is not executed and the agent answers without it.
            </p>
          </div>
          <fieldset className="space-y-2">
            <legend className={labelClass}>Agents used as tools</legend>
            {agentTools.length === 0 && <p className="text-xs text-gray-500">No agents in this app are marked as tools.</p>}
            {agentTools.map((tool) => (
              <FormField
                key={tool.name}
                id={`mw-agent-tool-${tool.name}`}
                type="checkbox"
                label={<>{tool.label} <code className="text-xs text-gray-500">{tool.name}</code></>}
                checked={!!interruptOn[tool.name]}
                onChange={() => toggleTool(tool.name)}
                disabled={isSubmitting}
                className="flex items-center gap-2"
              />
            ))}
          </fieldset>
          <fieldset className="space-y-2">
            <legend className={labelClass}>MCP server tools</legend>
            {mcpConfigs.length === 0 && <p className="text-xs text-gray-500">No MCP servers configured in this app.</p>}
            {mcpConfigs.map((cfg) => {
              const tools = mcpTools[cfg.config_id];
              return (
                <div key={cfg.config_id} className="rounded-lg border border-gray-200 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-gray-900 truncate">{cfg.name}</span>
                    {!Array.isArray(tools) && (
                      <button type="button" onClick={() => void loadMcpTools(cfg)} disabled={loadingMcp !== null}
                        className="shrink-0 text-xs px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                        {loadingMcp === cfg.config_id ? 'Loading…' : 'Show tools'}
                      </button>
                    )}
                  </div>
                  {typeof tools === 'string' && <p className="mt-1 text-xs text-red-600">{tools}</p>}
                  {Array.isArray(tools) && tools.length === 0 && <p className="mt-1 text-xs text-gray-500">This server exposes no tools.</p>}
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
              <FormField id="mw-custom-tool" label="Other tool (by exact name)" className="min-w-0 flex-1" value={customTool} onChange={(e) => setCustomTool(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomTool(); } }}
                placeholder="e.g. send_email" disabled={isSubmitting} />
              <button type="button" onClick={addCustomTool} disabled={!customTool.trim() || isSubmitting}
                className="shrink-0 px-3 py-2 text-sm rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                Add
              </button>
            </div>
            {extraSelected.map((toolName) => (
              <FormField
                key={toolName}
                id={`mw-extra-tool-${toolName}`}
                type="checkbox"
                label={<code className="text-xs">{toolName}</code>}
                checked
                onChange={() => toggleTool(toolName)}
                className="mt-2 flex items-center gap-2"
              />
            ))}
          </div>

          {Object.keys(interruptOn).length > 0 && (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <caption className="text-left text-sm font-medium text-gray-700 mb-1">What the reviewer can do</caption>
                <thead>
                  <tr className="text-xs text-gray-500">
                    <th className="text-left font-medium py-1 pr-4">Tool</th>
                    <th className="font-medium px-2">Approve</th>
                    <th className="font-medium px-2">Edit arguments</th>
                    <th className="font-medium px-2">Reject</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(interruptOn).map(([toolName, rule]) => (
                    <tr key={toolName} className="border-t border-gray-100">
                      <td className="py-1 pr-4"><code className="text-xs">{toolName}</code></td>
                      {DECISIONS.map((d) => (
                        <td key={d} className="text-center px-2">
                          <FormField
                            id={`mw-decision-${d}-${toolName}`}
                            type="checkbox"
                            checked={rule.allowed_decisions.includes(d)}
                            onChange={() => toggleDecision(toolName, d)}
                            disabled={isSubmitting}
                            ariaLabel={`${d} ${toolName}`}
                            className="flex justify-center"
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Guardrails */}
      {type === 'guardrails' && (
        <div className="space-y-4">
          <fieldset className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
            <legend className={labelClass}>Rules added to every model call</legend>
            {GUARDRAIL_RULES.map((rule) => (
              <FormField
                key={rule.key}
                id={`mw-guardrail-${rule.key}`}
                type="checkbox"
                label={rule.label}
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
              label="Additional rules"
              rows={4}
              maxLength={4000}
              value={config.custom_prompt ?? ''}
              onChange={(e) => patch({ custom_prompt: e.target.value })}
              disabled={isSubmitting}
              placeholder="e.g. Only answer questions about our products."
            />
          </div>
          <p className="text-xs text-gray-500">
            These are instructions to the model, not a hard block: combine them with PII protection or human approval
            where you need guarantees.
          </p>
        </div>
      )}

      <FormActions onCancel={onCancel} isSubmitting={isSubmitting} isEditing={isEditing} />
    </form>
  );
}

export default MiddlewareForm;
