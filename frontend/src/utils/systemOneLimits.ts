import i18n from '../i18n';

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
  return {
    maxQuestions: positive(raw?.max_questions),
    maxOptions: positive(raw?.max_answers_per_question),
    maxPromptTokens: positive(raw?.max_prompt_tokens),
  };
}

/**
 * The cap is the whole server's limit: every backend process shares it through the global limiter, so a cap above
 * what the server accepts at once can never be used. Returns the message when it is not, null otherwise.
 */
export function checkConcurrency(value: number | null, serverLimit: number | null | undefined): string | null {
  if (value === null || !serverLimit || value <= serverLimit) return null;
  return i18n.t('systemOne.validation.concurrency', { limit: serverLimit, value });
}

/** Ordinary text is about 4 characters per token; dense text (codes, numbers) far fewer. A rough guide, never a limit. */
const CHARS_PER_TOKEN = 4;

/** A soft note when the chosen text length is beyond what the server's prompt budget usually holds; null otherwise. */
export function textLengthHint(maxStateChars: number, maxPromptTokens: number | undefined): string | null {
  if (!maxPromptTokens || !Number.isFinite(maxStateChars)) return null;
  const typical = maxPromptTokens * CHARS_PER_TOKEN;
  if (maxStateChars <= typical) return null;
  const locale = i18n.resolvedLanguage;
  return i18n.t('systemOne.validation.textLengthHint', { tokens: maxPromptTokens.toLocaleString(locale), chars: typical.toLocaleString(locale) });
}
