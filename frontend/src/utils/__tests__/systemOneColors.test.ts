import { describe, expect, it } from 'vitest';
import { CATEGORY_PALETTE, categoryColor, scaleColor, yesNoColor } from '../systemOneColors';

describe('categoryColor', () => {
  it('gives each option a color from the palette, the same one every time', () => {
    expect(CATEGORY_PALETTE).toContain(categoryColor('billing'));
    expect(categoryColor('billing')).toBe(categoryColor('billing'));
  });
  it('does not depend on the position of the option', () => {
    expect(categoryColor('tech')).toBe(categoryColor('tech'));
  });
});

describe('scaleColor', () => {
  it('runs green to red when the scale starts green', () => {
    expect(scaleColor(0, 4, 'green')).toBe('rgb(16, 185, 129)');
    expect(scaleColor(3, 4, 'green')).toBe('rgb(239, 68, 68)');
  });
  it('runs red to green when the scale starts red', () => {
    expect(scaleColor(0, 4, 'red')).toBe('rgb(239, 68, 68)');
    expect(scaleColor(3, 4, 'red')).toBe('rgb(16, 185, 129)');
  });
  it('spreads the middle levels between the two ends', () => {
    expect(scaleColor(1, 3, 'green')).not.toBe(scaleColor(0, 3, 'green'));
    expect(scaleColor(1, 3, 'green')).not.toBe(scaleColor(2, 3, 'green'));
  });
  it('handles a single level and out-of-range indexes', () => {
    expect(scaleColor(0, 1, 'green')).toBe('rgb(16, 185, 129)');
    expect(scaleColor(9, 4, 'green')).toBe('rgb(239, 68, 68)');
  });
});

describe('yesNoColor', () => {
  it('is green for yes, red for no, neutral when undetermined', () => {
    expect(yesNoColor(true)).toBe('rgb(16, 185, 129)');
    expect(yesNoColor(false)).toBe('rgb(239, 68, 68)');
    expect(yesNoColor(null)).toBe('rgb(156, 163, 175)');
  });
});

import { toPayload } from '../systemOneQuestions';

describe('the color preference is saved with the score question', () => {
  it('keeps color_start on score questions and nothing else changes', () => {
    const [score] = toPayload([{ _id: 'c', key: 'anger', type: 'score', instructions: 'How angry?', criteria: ['Calm', 'Angry'], color_start: 'red' } as never]);
    expect(score).toMatchObject({ type: 'score', color_start: 'red', criteria: ['Calm', 'Angry'] });
  });
  it('defaults to green when it was never set', () => {
    const [score] = toPayload([{ _id: 'c', key: 'anger', type: 'score', instructions: 'How angry?', criteria: ['Calm', 'Angry'] } as never]);
    expect((score as { color_start?: string }).color_start).toBe('green');
  });
});
