import { describe, expect, it } from 'vitest';
import {
  changeQuestionType,
  newQuestion,
  toEditorQuestions,
  toPayload,
  checkQuestions,
  questionSize,
  promptBudget,
  reorder,
  validateMaxStateChars,
  validateQuestions,
  type EditorQuestion,
} from '../systemOneQuestions';

const noul = (over: Partial<EditorQuestion> = {}): EditorQuestion =>
  ({ _id: 'a', key: 'is_urgent', type: 'noul', instructions: 'Is it urgent?', ...over }) as EditorQuestion;
const choice = (over: Partial<EditorQuestion> = {}): EditorQuestion =>
  ({
    _id: 'b', key: 'area', type: 'choice', instructions: 'Which area?',
    criteria: [{ key: 'billing', description: 'Invoices' }, { key: 'tech', description: '' }], ...over,
  }) as EditorQuestion;
const score = (over: Partial<EditorQuestion> = {}): EditorQuestion =>
  ({ _id: 'c', key: 'anger', type: 'score', instructions: 'How angry?', criteria: ['Calm', 'Angry'], ...over }) as EditorQuestion;

describe('validateQuestions', () => {
  it('accepts a valid mix of the three types', () => {
    expect(validateQuestions([noul(), choice(), score()])).toEqual([]);
  });

  it('needs at least one and at most 64 questions', () => {
    expect(validateQuestions([])).toEqual(['Add at least one question']);
    const many = Array.from({ length: 65 }, (_, i) => noul({ key: `q${i}` }));
    expect(validateQuestions(many, { maxQuestions: 64, maxOptions: 26 }).some((p) => p.includes('at most 64'))).toBe(true);
  });

  it.each(['Has Space', '', 'x'.repeat(41), 'Upper', 'a-b'])('rejects the key %j', (key) => {
    expect(validateQuestions([noul({ key })]).some((p) => p.includes('key must be'))).toBe(true);
  });

  it('rejects repeated keys', () => {
    const problems = validateQuestions([noul(), noul({ _id: 'z' })]);
    expect(problems.some((p) => p.includes('used by another question'))).toBe(true);
  });

  it('requires instructions', () => {
    expect(validateQuestions([noul({ instructions: '  ' })]).some((p) => p.includes('instructions'))).toBe(true);
  });

  it('checks the noul threshold', () => {
    expect(validateQuestions([noul({ threshold: 1.5 })]).some((p) => p.includes('threshold'))).toBe(true);
    expect(validateQuestions([noul({ threshold: 0 })])).toEqual([]);
    expect(validateQuestions([noul({ criteria: { true: 'Today', false: 'Later' } })])).toEqual([]);
  });

  it('checks the number and names of choice options', () => {
    expect(validateQuestions([choice({ criteria: [{ key: 'only' }] })], { maxQuestions: 64, maxOptions: 26 }).some((p) => p.includes('between 2 and 26'))).toBe(true);
    const tooMany = Array.from({ length: 27 }, (_, i) => ({ key: `o${i}` }));
    expect(validateQuestions([choice({ criteria: tooMany })], { maxQuestions: 64, maxOptions: 26 }).some((p) => p.includes('between 2 and 26'))).toBe(true);
    expect(validateQuestions([choice({ criteria: [{ key: 'Billing' }, { key: 'billing' }] })]).some((p) => p.includes('repeated'))).toBe(true);
    expect(validateQuestions([choice({ criteria: [{ key: ' ' }, { key: 'b' }] })]).some((p) => p.includes('needs a name'))).toBe(true);
  });

  it('accepts accents and spaces in option names', () => {
    expect(validateQuestions([choice({ criteria: [{ key: 'facturación' }, { key: 'soporte técnico' }] })])).toEqual([]);
  });

  it('checks score levels and the minimum probability', () => {
    expect(validateQuestions([score({ criteria: ['only'] })], { maxQuestions: 64, maxOptions: 26 }).some((p) => p.includes('between 2 and 26'))).toBe(true);
    expect(validateQuestions([score({ criteria: ['a', ' '] })]).some((p) => p.toLowerCase().includes('every level'))).toBe(true);
    expect(validateQuestions([score({ min_probability: 2 })]).some((p) => p.includes('minimum probability'))).toBe(true);
    expect(validateQuestions([choice({ min_probability: -0.1 })]).some((p) => p.includes('minimum probability'))).toBe(true);
  });

  it('names the question that has the problem', () => {
    const problems = validateQuestions([noul(), choice({ criteria: [{ key: 'only' }] })]);
    expect(problems[0]).toContain('Question 2 (area)');
  });
});

describe('toPayload', () => {
  it('drops client-only fields, trims and omits empty optional values', () => {
    const payload = toPayload([
      noul({ key: ' is_urgent ', instructions: ' Is it urgent? ', threshold: Number.NaN, criteria: { true: '', false: '' } }),
      choice({ min_probability: undefined }),
      score(),
    ]);
    expect(payload[0]).toEqual({ key: 'is_urgent', type: 'noul', instructions: 'Is it urgent?' });
    expect(payload[1]).toEqual({
      key: 'area', type: 'choice', instructions: 'Which area?',
      criteria: [{ key: 'billing', description: 'Invoices' }, { key: 'tech' }],
    });
    expect(payload[2]).toEqual({ key: 'anger', type: 'score', instructions: 'How angry?', criteria: ['Calm', 'Angry'], color_start: 'green' });
    expect(JSON.stringify(payload)).not.toContain('_id');
  });

  it('keeps the values the user did set', () => {
    const payload = toPayload([
      noul({ threshold: 0.8, criteria: { true: ' Today ', false: ' Later ' } }),
      choice({ min_probability: 0.6 }),
      score({ min_probability: 0.4 }),
    ]);
    expect(payload[0]).toMatchObject({ threshold: 0.8, criteria: { true: 'Today', false: 'Later' } });
    expect(payload[1]).toMatchObject({ min_probability: 0.6 });
    expect(payload[2]).toMatchObject({ min_probability: 0.4 });
  });

  it('a threshold of 0 is a real value, not "empty"', () => {
    expect(toPayload([noul({ threshold: 0 })])[0]).toMatchObject({ threshold: 0 });
  });
});

describe('changeQuestionType / newQuestion / toEditorQuestions', () => {
  it('new questions start with the minimum shape of their type', () => {
    expect(newQuestion('noul', 'x')).toMatchObject({ type: 'noul', key: '', instructions: '' });
    expect((newQuestion('choice') as { criteria: unknown[] }).criteria).toHaveLength(2);
    expect((newQuestion('score') as { criteria: unknown[] }).criteria).toEqual(['', '']);
  });

  it('switching type keeps id, key and instructions and resets the criteria', () => {
    const changed = changeQuestionType(choice(), 'score');
    expect(changed).toMatchObject({ _id: 'b', key: 'area', instructions: 'Which area?', type: 'score', criteria: ['', ''] });
    expect(changeQuestionType(noul(), 'noul')).toEqual(noul());
  });

  it('API questions get a client id each', () => {
    let n = 0;
    const editor = toEditorQuestions([{ key: 'a', type: 'noul', instructions: 'q' }], () => `id${++n}`);
    expect(editor[0]._id).toBe('id1');
    expect(toEditorQuestions(null, () => 'x')).toEqual([]);
  });
});

describe('a question must leave room for the text in the prompt budget (mirrors the backend)', () => {
  it('accepts a long question when the budget is big enough and refuses it when it is not', () => {
    const long = noul({ instructions: 'x'.repeat(5600) });
    expect(checkQuestions([long], { maxStateChars: 12000 }).byQuestion[0]).toEqual([]);
    expect(checkQuestions([long], { maxStateChars: 6000 }).byQuestion[0].some((p) => p.includes('needs at least 500') && p.includes('definition'))).toBe(true);
  });

  it('counts options and levels, not only the instructions', () => {
    const q = score({ criteria: ['y'.repeat(3000), 'z'.repeat(3000)] } as Partial<EditorQuestion>);
    expect(checkQuestions([q], { maxStateChars: 6000 }).byQuestion[0].length).toBeGreaterThan(0);
  });

  it('does not judge the size when the budget is unknown or being retyped', () => {
    const long = noul({ instructions: 'x'.repeat(50000) });
    expect(checkQuestions([long]).byQuestion[0]).toEqual([]);
    expect(checkQuestions([long], { maxStateChars: Number.NaN }).byQuestion[0]).toEqual([]);
  });
});

describe('reorder', () => {
  it('moves an item to the position it is dropped on, either direction', () => {
    expect(reorder(['a', 'b', 'c', 'd'], 0, 2)).toEqual(['b', 'c', 'a', 'd']);
    expect(reorder(['a', 'b', 'c', 'd'], 3, 1)).toEqual(['a', 'd', 'b', 'c']);
  });

  it('returns the list untouched for a no-op or an invalid position', () => {
    const list = ['a', 'b'];
    expect(reorder(list, 1, 1)).toBe(list);
    expect(reorder(list, 0, 5)).toBe(list);
    expect(reorder(list, -1, 0)).toBe(list);
  });
});

describe('validateMaxStateChars', () => {
  it('accepts 500 to 20000 whole numbers', () => {
    expect([500, 6000, 20000].map(validateMaxStateChars)).toEqual([null, null, null]);
  });

  it('rejects empty/zero, fractions and out-of-range values with a readable message', () => {
    for (const bad of [Number.NaN, 0, 499, 20001, 600.5]) {
      expect(validateMaxStateChars(bad)).toMatch(/500.*20000/);
    }
  });
});

describe('checkQuestions (problems grouped by the question they belong to)', () => {
  it('puts each problem under its own question and nothing in the general list', () => {
    const result = checkQuestions([noul(), noul({ key: 'Bad Key', _id: 'z' }), choice({ criteria: [{ key: '', description: '' }, { key: 'b', description: '' }] } as Partial<EditorQuestion>)]);
    expect(result.general).toEqual([]);
    expect(result.byQuestion[0]).toEqual([]);
    expect(result.byQuestion[1].some((p) => p.includes('key'))).toBe(true);
    expect(result.byQuestion[2].some((p) => p.toLowerCase().includes('option'))).toBe(true);
  });

  it('keeps list-wide problems out of the questions', () => {
    expect(checkQuestions([]).general).toEqual(['Add at least one question']);
    const many = Array.from({ length: 65 }, (_, i) => noul({ key: `q${i}` }));
    expect(checkQuestions(many, { maxQuestions: 64, maxOptions: 26 }).general.some((p) => p.includes('at most 64'))).toBe(true);
  });

  it('starts each message with a capital so it reads on its own above the question', () => {
    const [first] = checkQuestions([noul({ instructions: '' })]).byQuestion[0];
    expect(first[0]).toBe(first[0].toUpperCase());
    expect(first).not.toMatch(/^Question \d/);
  });

  it('flags a repeated key on the second question only', () => {
    const { byQuestion } = checkQuestions([noul(), noul({ _id: 'x' })]);
    expect(byQuestion[0]).toEqual([]);
    expect(byQuestion[1].some((p) => p.includes('used by another question'))).toBe(true);
  });
});

describe('yes / no meanings are independent and optional', () => {
  it('accepts only one of them, or none', () => {
    expect(checkQuestions([noul({ criteria: { true: 'Needs an answer today', false: '' } } as Partial<EditorQuestion>)]).byQuestion[0]).toEqual([]);
    expect(checkQuestions([noul({ criteria: { true: '', false: 'Can wait' } } as Partial<EditorQuestion>)]).byQuestion[0]).toEqual([]);
    expect(checkQuestions([noul()]).byQuestion[0]).toEqual([]);
  });

  it('sends only the meanings that were filled', () => {
    const [only] = toPayload([noul({ criteria: { true: ' Today ', false: '' } } as Partial<EditorQuestion>)]);
    expect(only).toMatchObject({ criteria: { true: 'Today' } });
    expect((only as { criteria: Record<string, string> }).criteria.false).toBeUndefined();
    const [none] = toPayload([noul({ criteria: { true: '', false: '' } } as Partial<EditorQuestion>)]);
    expect((none as { criteria?: unknown }).criteria).toBeUndefined();
  });
});

describe('promptBudget', () => {
  it('is what is left of the per-prompt budget after the longest question', () => {
    const q = noul({ instructions: 'x'.repeat(100) });
    expect(promptBudget([q, noul({ instructions: 'short' })], 6000)).toBe(6000 - questionSize(q));
  });

  it('never goes below the room a question must leave', () => {
    expect(promptBudget([noul({ instructions: 'x'.repeat(9000) })], 6000)).toBe(500);
  });
});

describe('decimal input accepts a comma or a point', () => {
  it('reads 0,5 and 0.5 as the same number', async () => {
    const { parseDecimal } = await import('../systemOneQuestions');
    expect(parseDecimal('0,5')).toBe(0.5);
    expect(parseDecimal('0.5')).toBe(0.5);
    expect(parseDecimal(' 0,75 ')).toBe(0.75);
    expect(parseDecimal('')).toBeUndefined();
    expect(parseDecimal('abc')).toBeNaN();
  });
});
