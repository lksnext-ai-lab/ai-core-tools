import { describe, expect, it } from 'vitest';
import { endOfServiceForSave } from '../serviceLifecycle';

describe('endOfServiceForSave', () => {
  it('sends the picked day as midnight UTC when nothing was stored', () => {
    expect(endOfServiceForSave(null, '2026-12-31')).toBe('2026-12-31T00:00:00Z');
    expect(endOfServiceForSave(undefined, '2026-12-31')).toBe('2026-12-31T00:00:00Z');
  });

  it('keeps a stored non-midnight timestamp when the day was not changed', () => {
    const stored = '2026-12-31T15:30:00Z';
    expect(endOfServiceForSave(stored, '2026-12-31')).toBe(stored);
  });

  it('replaces the stored value when the day was changed', () => {
    expect(endOfServiceForSave('2026-12-31T15:30:00Z', '2027-01-15')).toBe('2027-01-15T00:00:00Z');
  });

  it('clears the date with an explicit null', () => {
    expect(endOfServiceForSave('2026-12-31T00:00:00Z', '')).toBeNull();
    expect(endOfServiceForSave(null, '')).toBeNull();
  });
});
