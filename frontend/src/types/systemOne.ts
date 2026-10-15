// System One: connections, question definitions and evaluation results.
// Text; images only for the models that take them (see `supports_images`).

export type SystemOneProvider = 'system_one' | 'openai_decisions';


export interface SystemOneService {
  service_id: number;
  name: string;
  endpoint: string;
  provider: SystemOneProvider;
  /** Whether the provider accepts images next to the text. */
  supports_images?: boolean;
  model: string;
  max_concurrency: number;
  /** Agents that would be left without a service if this one were deleted. */
  agent_count?: number;
  created_at?: string | null;
}

export interface SystemOneServiceDetail extends SystemOneService {
  /** Always masked ("****1234") or empty on read. */
  api_key: string;
}

export interface SystemOneServicePayload {
  name: string;
  endpoint: string;
  provider: SystemOneProvider;
  /** "" = no token; "****…" = keep the stored one. */
  api_key: string;
  model: string;
  max_concurrency: number | null;
}

export interface SystemOneConnectionResult {
  status: 'success' | 'error';
  message: string;
  models: string[];
  /** The models that also take images (by name: the servers' own lists do not say it). */
  image_models?: string[];
  /** When each model was created or released (Unix seconds), for the "New" badge; models without a date are absent. */
  created?: Record<string, number>;
  limits: Record<string, number> | null;
  /** The server's own limit (the cap is the total, shared by all backend processes); null when it did not report its limits. */
  suggested_max_concurrency?: number | null;
  /** True when the server cannot list models and the check was one real, tiny call with the chosen model. */
  checked_with_call?: boolean;
}

// ----------------------------------------------------------------- questions

export interface NoulQuestion {
  key: string;
  type: 'noul';
  instructions: string;
  /** Each meaning is independent and optional: the one left out keeps the server's default ("Yes" / "No"). */
  criteria?: { true?: string | null; false?: string | null } | null;
  threshold?: number;
}

export interface ChoiceOption {
  key: string;
  description?: string | null;
  /** Playground color (#rrggbb, never sent): empty = the automatic color of the name. */
  color?: string | null;
}

export interface ChoiceQuestion {
  key: string;
  type: 'choice';
  instructions: string;
  criteria: ChoiceOption[];
  min_probability?: number | null;
}

export interface ScoreQuestion {
  key: string;
  type: 'score';
  instructions: string;
  criteria: string[];
  min_probability?: number | null;
  /** Playground color only (never sent): which end of the scale is green. */
  color_start?: 'green' | 'red';
}

export type SystemOneQuestion = NoulQuestion | ChoiceQuestion | ScoreQuestion;
export type SystemOneQuestionType = SystemOneQuestion['type'];

// ------------------------------------------------------------------- results

export interface NoulAnswer {
  type: 'noul';
  decision: boolean;
  probability: number;
  threshold: number;
}

export interface ChoiceAnswer {
  type: 'choice';
  /** null = below the question's minimum probability. */
  decision: string | null;
  choice: string;
  probability: number;
  probabilities: Record<string, number>;
  confidence: number;
  min_probability?: number | null;
}

export interface ScoreAnswer {
  type: 'score';
  decision: string | null;
  level_index: number;
  probability: number;
  expected_score: number;
  legend: Record<string, string>;
  probabilities: Record<string, number>;
  confidence: number;
  min_probability?: number | null;
}

export type SystemOneAnswer = NoulAnswer | ChoiceAnswer | ScoreAnswer;

export interface SystemOneResult {
  answers: Record<string, SystemOneAnswer>;
  state_reduction: 'none' | 'summarized' | 'truncated';
  original_chars: number;
  state_chars: number;
  model: string;
  usage?: { input_tokens: number; output_tokens: number } | null;
  /** Milliseconds per phase; summarization_ms is null when no summarizing LLM ran. */
  timings?: { evaluation_ms: number; summarization_ms?: number | null } | null;
  /** The text the server evaluated, only when it was summarized or truncated. */
  evaluated_text?: string | null;
}
