import type { MiddlewareType } from '../core/types';

export interface MiddlewareTypeInfo {
  readonly label: string;
  /** What the user gets, in one sentence. */
  readonly description: string;
}

/** Display order of the types in pickers. */
export const MIDDLEWARE_TYPES: readonly MiddlewareType[] = [
  'guardrails',
  'pii',
  'human_in_the_loop',
  'model_call_limit',
  'tool_call_limit',
  'summarization',
];

export const MIDDLEWARE_TYPE_INFO: Record<MiddlewareType, MiddlewareTypeInfo> = {
  guardrails: {
    label: 'Guardrails',
    description: 'Adds safety rules to every model call: refuse jailbreaks and harmful requests, avoid leaking personal data, toxic language and made-up facts.',
  },
  pii: {
    label: 'PII protection',
    description: 'Redacts, masks or blocks personal data (emails, cards, IPs…) in user messages, tool results and answers.',
  },
  human_in_the_loop: {
    label: 'Human approval',
    description: 'Pauses before the selected tools run so a person can approve, edit or reject the call.',
  },
  model_call_limit: {
    label: 'Model call limit',
    description: 'Stops a run after a maximum number of LLM calls, to prevent loops and control cost.',
  },
  tool_call_limit: {
    label: 'Tool call limit',
    description: 'Caps the number of tool calls per run; extra calls are blocked and the agent is told why.',
  },
  summarization: {
    label: 'Summarization',
    description: 'Summarizes older messages when the conversation gets long, keeping the most recent ones.',
  },
};

export const middlewareTypeLabel = (type: string): string =>
  MIDDLEWARE_TYPE_INFO[type as MiddlewareType]?.label ?? type;

/**
 * Tool name an agent-as-tool gets at runtime. Mirrors backend
 * utils/schema_utils.sanitize_identifier so HITL rules match the real tool name.
 */
export const agentToolName = (agentName: string): string => {
  let name = agentName.replace(/[^a-zA-Z0-9_-]/gu, '_');
  if (!name) name = 'id';
  if (!/^[a-zA-Z_]/.test(name)) name = `id_${name}`;
  return name;
};
