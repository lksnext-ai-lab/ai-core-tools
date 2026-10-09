import { describe, expect, it } from 'vitest';
import {
  changeQuestionType,
  newQuestion,
  toEditorQuestions,
  toPayload,
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
    expect(validateQuestions(many).some((p) => p.includes('at most 64'))).toBe(true);
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

  it('checks the noul threshold and the two meanings together', () => {
    expect(validateQuestions([noul({ threshold: 1.5 })]).some((p) => p.includes('threshold'))).toBe(true);
    expect(validateQuestions([noul({ threshold: 0 })])).toEqual([]);
    expect(validateQuestions([noul({ criteria: { true: 'Today', false: '' } })]).some((p) => p.includes('both meanings'))).toBe(true);
    expect(validateQuestions([noul({ criteria: { true: 'Today', false: 'Later' } })])).toEqual([]);
  });

  it('checks the number and names of choice options', () => {
    expect(validateQuestions([choice({ criteria: [{ key: 'only' }] })]).some((p) => p.includes('between 2 and 26'))).toBe(true);
    const tooMany = Array.from({ length: 27 }, (_, i) => ({ key: `o${i}` }));
    expect(validateQuestions([choice({ criteria: tooMany })]).some((p) => p.includes('between 2 and 26'))).toBe(true);
    expect(validateQuestions([choice({ criteria: [{ key: 'Billing' }, { key: 'billing' }] })]).some((p) => p.includes('repeated'))).toBe(true);
    expect(validateQuestions([choice({ criteria: [{ key: ' ' }, { key: 'b' }] })]).some((p) => p.includes('needs a name'))).toBe(true);
  });

  it('accepts accents and spaces in option names', () => {
    expect(validateQuestions([choice({ criteria: [{ key: 'facturación' }, { key: 'soporte técnico' }] })])).toEqual([]);
  });

  it('checks score levels and the minimum probability', () => {
    expect(validateQuestions([score({ criteria: ['only'] })]).some((p) => p.includes('between 2 and 26'))).toBe(true);
    expect(validateQuestions([score({ criteria: ['a', ' '] })]).some((p) => p.includes('every level'))).toBe(true);
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
    expect(payload[2]).toEqual({ key: 'anger', type: 'score', instructions: 'How angry?', criteria: ['Calm', 'Angry'] });
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

describe('text length limits (mirror the backend)', () => {
  it('rejects instructions over 4000 characters, accepts exactly 4000', () => {
    expect(validateQuestions([noul({ instructions: 'x'.repeat(4000) })])).toEqual([]);
    expect(validateQuestions([noul({ instructions: 'x'.repeat(4001) })]).some((p) => p.includes('4000'))).toBe(true);
  });

  it('rejects criteria text over 500 characters', () => {
    const long = 'x'.repeat(501);
    expect(validateQuestions([score({ criteria: [long, 'High'] } as Partial<EditorQuestion>)]).some((p) => p.includes('500'))).toBe(true);
    expect(validateQuestions([noul({ criteria: { true: long, false: 'no' } } as Partial<EditorQuestion>)]).some((p) => p.includes('500'))).toBe(true);
    expect(validateQuestions([choice({ criteria: [{ key: 'a', description: long }, { key: 'b', description: '' }] } as Partial<EditorQuestion>)]).some((p) => p.includes('500'))).toBe(true);
  });

  it('rejects an option name over 100 characters', () => {
    const q = choice({ criteria: [{ key: 'a'.repeat(101), description: '' }, { key: 'b', description: '' }] } as Partial<EditorQuestion>);
    expect(validateQuestions([q]).some((p) => p.includes('100'))).toBe(true);
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
