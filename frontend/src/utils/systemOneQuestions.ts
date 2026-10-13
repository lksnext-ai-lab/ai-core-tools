// Pure helpers of the System One questions editor: defaults, validation (mirrors the backend rules in
// backend/schemas/system_one_schemas.py) and normalization of what is sent to the API.
import type { QuestionLimits } from './systemOneLimits';
import type {
  ChoiceOption,
  ChoiceQuestion,
  NoulQuestion,
  ScoreQuestion,
  SystemOneQuestion,
  SystemOneQuestionType,
} from '../types/systemOne';

export const MIN_OPTIONS = 2;
/** Mirrors backend question_overhead_chars / MIN_TEXT_ROOM_CHARS: what a question takes of each prompt's budget. */
const QUESTION_MARGIN_CHARS = 50;
const MIN_TEXT_ROOM_CHARS = 500;
export const MAX_KEY_LENGTH = 40;
export const MIN_STATE_CHARS = 500;
export const MAX_STATE_CHARS = 20000;
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

/** Message for an invalid "maximum text length", or null when it is fine. */
export function validateMaxStateChars(value: number): string | null {
  if (!Number.isInteger(value) || value < MIN_STATE_CHARS || value > MAX_STATE_CHARS) {
    return `The maximum text length must be a whole number between ${MIN_STATE_CHARS} and ${MAX_STATE_CHARS}`;
  }
  return null;
}

function label(question: EditorQuestion, index: number): string {
  return question.key.trim() ? `Question ${index + 1} (${question.key.trim()})` : `Question ${index + 1}`;
}

function rangeMessage(what: string, max: number | undefined): string {
  return max === undefined ? `it needs at least ${MIN_OPTIONS} ${what}` : `it needs between ${MIN_OPTIONS} and ${max} ${what}`;
}

/** Characters one question takes of every prompt: its instructions, options/levels and a margin (as the backend counts). */
export function questionSize(question: EditorQuestion): number {
  let total = question.instructions.trim().length;
  if (question.type === 'noul') {
    total += (question.criteria?.true?.trim().length ?? 0) + (question.criteria?.false?.trim().length ?? 0);
  } else if (question.type === 'choice') {
    total += question.criteria.reduce((sum, o) => sum + o.key.trim().length + (o.description?.trim().length ?? 0), 0);
  } else {
    total += question.criteria.reduce((sum, level) => sum + level.trim().length, 0);
  }
  return total + QUESTION_MARGIN_CHARS;
}

function validateNoul(question: NoulQuestion): string[] {
  const problems: string[] = [];
  if (question.threshold !== undefined && !isProbability(question.threshold)) {
    problems.push(`the threshold must be a number between 0 and 1`);
  }
  return problems;
}

function validateChoice(question: ChoiceQuestion, limits: QuestionLimits): string[] {
  const problems: string[] = [];
  const options = question.criteria;
  if (options.length < MIN_OPTIONS || (limits.maxOptions !== undefined && options.length > limits.maxOptions)) {
    problems.push(rangeMessage('options', limits.maxOptions));
  }
  const seen = new Set<string>();
  for (const option of options) {
    const key = option.key.trim();
    if (!key) {
      problems.push(`every option needs a name`);
      continue;
    }
    const folded = key.toLowerCase();
    if (seen.has(folded)) problems.push(`the option "${key}" is repeated (names are compared ignoring case)`);
    seen.add(folded);
  }
  if (question.min_probability != null && !isProbability(question.min_probability)) {
    problems.push(`the minimum probability must be a number between 0 and 1`);
  }
  return problems;
}

function validateScore(question: ScoreQuestion, limits: QuestionLimits): string[] {
  const problems: string[] = [];
  const levels = question.criteria;
  if (levels.length < MIN_OPTIONS || (limits.maxOptions !== undefined && levels.length > limits.maxOptions)) {
    problems.push(rangeMessage('levels', limits.maxOptions));
  }
  if (levels.some((level) => !level.trim())) problems.push(`every level needs a description`);
  if (question.min_probability != null && !isProbability(question.min_probability)) {
    problems.push(`the minimum probability must be a number between 0 and 1`);
  }
  return problems;
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export interface QuestionProblems {
  /** About the list as a whole (none, too many). */
  general: string[];
  /** One list per question, same order; each message reads on its own, shown right above that question. */
  byQuestion: string[][];
}

export interface QuestionContext extends QuestionLimits {
  /** The agent's per-prompt budget in characters: a question must leave room for the text inside it. */
  maxStateChars?: number;
}

export function checkQuestions(questions: EditorQuestion[], context: QuestionContext = {}): QuestionProblems {
  const general: string[] = [];
  if (questions.length === 0) general.push('Add at least one question');
  if (context.maxQuestions !== undefined && questions.length > context.maxQuestions) {
    general.push(`This server accepts at most ${context.maxQuestions} questions per call`);
  }

  const seenKeys = new Set<string>();
  const byQuestion = questions.map((question) => {
    const problems: string[] = [];
    const key = question.key.trim();
    if (!KEY_PATTERN.test(key)) {
      problems.push(`the key must be 1-${MAX_KEY_LENGTH} characters of lowercase letters, digits or underscores (e.g. is_urgent)`);
    } else if (seenKeys.has(key)) {
      problems.push(`the key "${key}" is used by another question`);
    }
    seenKeys.add(key);
    if (!question.instructions.trim()) problems.push('the instructions are required');
    const size = questionSize(question);
    if (context.maxStateChars !== undefined && Number.isFinite(context.maxStateChars) && context.maxStateChars - size < MIN_TEXT_ROOM_CHARS) {
      problems.push(
        `this question's definition (instructions plus options/levels) is about ${size} characters long. ` +
          `Each prompt has ${context.maxStateChars} characters in total, shared with the text to evaluate, and the text needs at least ${MIN_TEXT_ROOM_CHARS} ` +
          `("Maximum text length" in this form): shorten the question or raise that limit`,
      );
    }
    if (question.type === 'noul') problems.push(...validateNoul(question));
    else if (question.type === 'choice') problems.push(...validateChoice(question, context));
    else problems.push(...validateScore(question, context));
    return problems.map(capitalize);
  });
  return { general, byQuestion };
}

/** Human-readable problems, in question order, each naming its question. Empty array = valid. */
export function validateQuestions(questions: EditorQuestion[], context: QuestionContext = {}): string[] {
  const { general, byQuestion } = checkQuestions(questions, context);
  return [
    ...general,
    ...byQuestion.flatMap((problems, index) => problems.map((p) => `${label(questions[index], index)}: ${p}`)),
  ];
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
        ...(yes || no ? { criteria: { ...(yes ? { true: yes } : {}), ...(no ? { false: no } : {}) } } : {}),
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
    return { ...common, type: 'score', criteria: q.criteria.map((level) => level.trim()), color_start: q.color_start ?? 'green', ...extra };
  });
}

/** Questions from the API as editor questions (each gets a client-only id). */
export function toEditorQuestions(questions: SystemOneQuestion[] | null | undefined, makeId: () => string): EditorQuestion[] {
  return (questions ?? []).map((q) => ({ ...q, _id: makeId() }));
}

/** Moves the item at `from` to position `to` (what dropping a dragged question on another one does). */
export function reorder<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/** Characters of text that fit in a prompt next to the longest question (what the backend calls the state budget). */
export function promptBudget(questions: EditorQuestion[], maxStateChars: number): number {
  const longest = questions.reduce((max, q) => Math.max(max, questionSize(q)), 0);
  return Math.max(maxStateChars - longest, MIN_TEXT_ROOM_CHARS);
}

/** A decimal typed with a comma (Spanish keyboards) or a point. Empty = undefined; anything else not a number = NaN. */
export function parseDecimal(raw: string): number | undefined {
  const text = raw.trim();
  if (text === '') return undefined;
  return Number.parseFloat(text.replace(',', '.'));
}
