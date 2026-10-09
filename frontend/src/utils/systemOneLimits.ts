// What the chosen System One server accepts (GET /v1/limits), read instead of assumed: every server has its own.

export interface QuestionLimits {
  /** Questions per call; undefined = the server did not say. */
  maxQuestions?: number;
  /** Options (choice) or levels (score) per question. */
  maxOptions?: number;
}

const positive = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined;

export function questionLimits(raw: Record<string, number> | null | undefined): QuestionLimits {
  const limits: QuestionLimits = {};
  const maxQuestions = positive(raw?.max_questions);
  const maxOptions = positive(raw?.max_answers_per_question);
  if (maxQuestions !== undefined) limits.maxQuestions = maxQuestions;
  if (maxOptions !== undefined) limits.maxOptions = maxOptions;
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
