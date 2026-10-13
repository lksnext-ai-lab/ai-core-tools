// What the chosen System One server accepts (GET /v1/limits), read instead of assumed: every server has its own.

export interface QuestionLimits {
  /** Questions per call; undefined = the server did not say. */
  maxQuestions?: number;
  /** Options (choice) or levels (score) per question. */
  maxOptions?: number;
  /** Tokens a prompt (the text plus one question) may have. */
  maxPromptTokens?: number;
}

const positive = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined;

export function questionLimits(raw: Record<string, number> | null | undefined): QuestionLimits {
  const limits: QuestionLimits = {};
  const maxQuestions = positive(raw?.max_questions);
  const maxOptions = positive(raw?.max_answers_per_question);
  if (maxQuestions !== undefined) limits.maxQuestions = maxQuestions;
  if (maxOptions !== undefined) limits.maxOptions = maxOptions;
  const maxPromptTokens = positive(raw?.max_prompt_tokens);
  if (maxPromptTokens !== undefined) limits.maxPromptTokens = maxPromptTokens;
  return limits;
}

export interface ConcurrencyCheck {
  /** Blocks saving. */
  error?: string;
  /** Allowed, but worth knowing. */
  warning?: string;
}

/**
 * The cap is per backend process and every process shares the server's limit: a cap above the whole limit can
 * never be right (error); one above limit ÷ processes can still overload it when the processes add up (warning).
 */
export function checkConcurrency(
  value: number | null,
  serverLimit: number | null | undefined,
  suggested: number | null | undefined,
): ConcurrencyCheck {
  if (value === null || !serverLimit) return {};
  if (value > serverLimit) {
    return { error: `The server accepts ${serverLimit} requests at once: a cap of ${value} can never be used` };
  }
  if (suggested && value > suggested) {
    return {
      warning: `Above ${suggested} (the server's ${serverLimit} shared among the backend processes) the server may answer "busy" under load`,
    };
  }
  return {};
}

/** Ordinary text is about 4 characters per token; dense text (codes, numbers) far fewer. A rough guide, never a limit. */
const CHARS_PER_TOKEN = 4;

/** A soft note when the chosen text length is beyond what the server's prompt budget usually holds; null otherwise. */
export function textLengthHint(maxStateChars: number, maxPromptTokens: number | undefined): string | null {
  if (!maxPromptTokens || !Number.isFinite(maxStateChars)) return null;
  const typical = maxPromptTokens * CHARS_PER_TOKEN;
  if (maxStateChars <= typical) return null;
  return `This server accepts ${maxPromptTokens.toLocaleString()} tokens per prompt, about ${typical.toLocaleString()} characters of ordinary text: a longer text may be shortened by the server's limit.`;
}
