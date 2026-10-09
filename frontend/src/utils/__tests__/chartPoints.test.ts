import { describe, expect, it } from 'vitest';
import { isolatedPointIndexes } from '../chartPoints';

describe('isolatedPointIndexes', () => {
  it('finds the points a line cannot draw because both neighbours are empty', () => {
    expect(isolatedPointIndexes([null, null, 5, null, null])).toEqual(new Set([2]));
    expect(isolatedPointIndexes([1, null, 2, null, 3])).toEqual(new Set([0, 2, 4]));
  });

  it('ignores points that belong to a line', () => {
    expect(isolatedPointIndexes([1, 2, 3])).toEqual(new Set());
    expect(isolatedPointIndexes([null, 1, 2, null])).toEqual(new Set());
  });

  it('treats the ends of the series and undefined values as empty neighbours', () => {
    expect(isolatedPointIndexes([4])).toEqual(new Set([0]));
    expect(isolatedPointIndexes([undefined, 7])).toEqual(new Set([1]));
    expect(isolatedPointIndexes([])).toEqual(new Set());
  });

  it('counts zero as a real value', () => {
    expect(isolatedPointIndexes([null, 0, null])).toEqual(new Set([1]));
  });
});
