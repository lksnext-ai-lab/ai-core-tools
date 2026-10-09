// Pure helpers of the System One questions editor: defaults, validation (mirrors the backend rules in
// backend/schemas/system_one_schemas.py) and normalization of what is sent to the API.
import type {
  ChoiceOption,
  ChoiceQuestion,
  NoulQuestion,
  ScoreQuestion,
  SystemOneQuestion,
  SystemOneQuestionType,
} from '../types/systemOne';

export const MAX_QUESTIONS = 64;
export const MIN_OPTIONS = 2;
export const MAX_OPTIONS = 26;
export const MAX_KEY_LENGTH = 40;
const KEY_PATTERN = /^[a-z0-9_]{1,40}$/;

/** A question as edited in the form: `_id` is a client-only React key, never sent. */
export type EditorQuestion = SystemOneQuestion & { _id?: string };

export function newQuestion(type: SystemOneQuestionType, id?: string): EditorQuestion {
  const base = { _id: id, key: '', instructions: '' };
  if (type === 'noul') return { ...base, type } satisfies EditorQuestion;
  if (type === 'choice') return { ...base, type, criteria: [{ key: '', description: '' }, { key: '', description: '' }] };
  return { ...base, type, criteria: ['', ''] };
}

/** Switch the type of a question keeping what is common (id, key, instructions). */
export function changeQuestionType(question: EditorQuestion, type: SystemOneQuestionType): EditorQuestion {
  if (question.type === type) return question;
  return { ...newQuestion(type, question._id), key: question.key, instructions: question.instructions };
}

function isProbability(value: unknown): boolean {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
}

function label(question: EditorQuestion, index: number): string {
  return question.key.trim() ? `Question ${index + 1} (${question.key.trim()})` : `Question ${index + 1}`;
}

function validateNoul(question: NoulQuestion, name: string): string[] {
  const problems: string[] = [];
  if (question.threshold !== undefined && !isProbability(question.threshold)) {
    problems.push(`${name}: the threshold must be a number between 0 and 1`);
  }
  const yes = question.criteria?.true?.trim() ?? '';
  const no = question.criteria?.false?.trim() ?? '';
  if ((yes === '') !== (no === '')) problems.push(`${name}: fill both meanings (yes and no) or leave both empty`);
  return problems;
}

function validateChoice(question: ChoiceQuestion, name: string): string[] {
  const problems: string[] = [];
  const options = question.criteria;
  if (options.length < MIN_OPTIONS || options.length > MAX_OPTIONS) {
    problems.push(`${name}: it needs between ${MIN_OPTIONS} and ${MAX_OPTIONS} options`);
  }
  const seen = new Set<string>();
  for (const option of options) {
    const key = option.key.trim();
    if (!key) {
      problems.push(`${name}: every option needs a name`);
      continue;
    }
    const folded = key.toLowerCase();
    if (seen.has(folded)) problems.push(`${name}: the option "${key}" is repeated (names are compared ignoring case)`);
    seen.add(folded);
  }
  if (question.min_probability != null && !isProbability(question.min_probability)) {
    problems.push(`${name}: the minimum probability must be a number between 0 and 1`);
  }
  return problems;
}

function validateScore(question: ScoreQuestion, name: string): string[] {
  const problems: string[] = [];
  const levels = question.criteria;
  if (levels.length < MIN_OPTIONS || levels.length > MAX_OPTIONS) {
    problems.push(`${name}: it needs between ${MIN_OPTIONS} and ${MAX_OPTIONS} levels`);
  }
  if (levels.some((level) => !level.trim())) problems.push(`${name}: every level needs a description`);
  if (question.min_probability != null && !isProbability(question.min_probability)) {
    problems.push(`${name}: the minimum probability must be a number between 0 and 1`);
  }
  return problems;
}

/** Human-readable problems, in question order. Empty array = valid. */
export function validateQuestions(questions: EditorQuestion[]): string[] {
  if (questions.length === 0) return ['Add at least one question'];
  const problems: string[] = [];
  if (questions.length > MAX_QUESTIONS) problems.push(`A System One agent supports at most ${MAX_QUESTIONS} questions`);

  const seenKeys = new Set<string>();
  questions.forEach((question, index) => {
    const name = label(question, index);
    const key = question.key.trim();
    if (!KEY_PATTERN.test(key)) {
      problems.push(`${name}: the key must be 1-${MAX_KEY_LENGTH} characters of lowercase letters, digits or underscores (e.g. is_urgent)`);
    } else if (seenKeys.has(key)) {
      problems.push(`${name}: the key "${key}" is used by another question`);
    }
    seenKeys.add(key);
    if (!question.instructions.trim()) problems.push(`${name}: the instructions are required`);

    if (question.type === 'noul') problems.push(...validateNoul(question, name));
    else if (question.type === 'choice') problems.push(...validateChoice(question, name));
    else problems.push(...validateScore(question, name));
  });
  return problems;
}

function optionalProbability(value: number | null | undefined): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/** What goes to the API: trimmed, without client-only fields and without empty optional values. */
export function toPayload(questions: EditorQuestion[]): SystemOneQuestion[] {
  return questions.map((q): SystemOneQuestion => {
    const common = { key: q.key.trim(), instructions: q.instructions.trim() };
    if (q.type === 'noul') {
      const yes = q.criteria?.true?.trim() ?? '';
      const no = q.criteria?.false?.trim() ?? '';
      const threshold = optionalProbability(q.threshold);
      return {
        ...common,
        type: 'noul',
        ...(yes && no ? { criteria: { true: yes, false: no } } : {}),
        ...(threshold !== undefined ? { threshold } : {}),
      };
    }
    const minProbability = optionalProbability(q.min_probability);
    const extra = minProbability !== undefined ? { min_probability: minProbability } : {};
    if (q.type === 'choice') {
      const criteria: ChoiceOption[] = q.criteria.map((o) => {
        const description = o.description?.trim() ?? '';
        return description ? { key: o.key.trim(), description } : { key: o.key.trim() };
      });
      return { ...common, type: 'choice', criteria, ...extra };
    }
    return { ...common, type: 'score', criteria: q.criteria.map((level) => level.trim()), ...extra };
  });
}

/** Questions from the API as editor questions (each gets a client-only id). */
export function toEditorQuestions(questions: SystemOneQuestion[] | null | undefined, makeId: () => string): EditorQuestion[] {
  return (questions ?? []).map((q) => ({ ...q, _id: makeId() }));
}
