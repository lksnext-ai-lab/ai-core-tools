import { describe, expect, it } from 'vitest';
import { checkConcurrency, questionLimits, textLengthHint } from '../systemOneLimits';
import { checkQuestions, type EditorQuestion } from '../systemOneQuestions';

const noul = (key: string): EditorQuestion => ({ _id: key, key, type: 'noul', instructions: 'Is it urgent?' }) as EditorQuestion;
const choice = (n: number): EditorQuestion =>
  ({ _id: 'c', key: 'area', type: 'choice', instructions: 'Which?', criteria: Array.from({ length: n }, (_, i) => ({ key: `o${i}`, description: '' })) }) as EditorQuestion;

describe('questionLimits', () => {
  it('reads what /v1/limits reports and ignores what is missing or not a positive number', () => {
    expect(questionLimits({ max_questions: 64, max_answers_per_question: 26 })).toEqual({ maxQuestions: 64, maxOptions: 26 });
    expect(questionLimits({ max_questions: 0 })).toEqual({});
    expect(questionLimits(null)).toEqual({});
  });
});

describe('questions are checked against the limits of the chosen service', () => {
  it('has no upper limit when the server did not report one', () => {
    const many = Array.from({ length: 200 }, (_, i) => noul(`q${i}`));
    expect(checkQuestions(many).general).toEqual([]);
    expect(checkQuestions([choice(40)]).byQuestion[0]).toEqual([]);
  });

  it('refuses more questions than the server accepts, naming the limit', () => {
    const many = Array.from({ length: 11 }, (_, i) => noul(`q${i}`));
    expect(checkQuestions(many, { maxQuestions: 10 }).general.some((p) => p.includes('at most 10'))).toBe(true);
    expect(checkQuestions(many.slice(0, 10), { maxQuestions: 10 }).general).toEqual([]);
  });

  it('refuses more options than the server accepts, but accepts more when the server does', () => {
    expect(checkQuestions([choice(27)], { maxOptions: 26 }).byQuestion[0].some((p) => p.includes('between 2 and 26'))).toBe(true);
    expect(checkQuestions([choice(40)], { maxOptions: 50 }).byQuestion[0]).toEqual([]);
  });
});

describe('checkConcurrency', () => {
  it('blocks a cap above what the server accepts at once: the cap is the whole server, shared by every process', () => {
    expect(checkConcurrency(5, 4).error).toMatch(/4/);
  });

  it('allows any cap up to the limit, with no warning', () => {
    expect(checkConcurrency(4, 4)).toEqual({});
    expect(checkConcurrency(1, 4)).toEqual({});
  });

  it('is silent when nothing is known', () => {
    expect(checkConcurrency(null, 4)).toEqual({});
    expect(checkConcurrency(500, null)).toEqual({});
    expect(checkConcurrency(500, undefined)).toEqual({});
  });
});

describe('textLengthHint', () => {
  it('is silent when the length fits what the server usually holds, or when nothing is known', () => {
    expect(textLengthHint(6000, 8192)).toBeNull();
    expect(textLengthHint(32768, 8192)).toBeNull();
    expect(textLengthHint(50000, undefined)).toBeNull();
    expect(textLengthHint(Number.NaN, 8192)).toBeNull();
  });
  it('says what the server accepts when the length goes beyond it', () => {
    expect(textLengthHint(40000, 8192)).toMatch(/8,192|8\.192|8192/);
  });
  it('reads max_prompt_tokens from the limits', () => {
    expect(questionLimits({ max_prompt_tokens: 8192 }).maxPromptTokens).toBe(8192);
  });
});
