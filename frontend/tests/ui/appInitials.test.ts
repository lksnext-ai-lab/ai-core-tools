import { describe, expect, it } from 'vitest';

import { getAppInitials } from '../../src/utils/appInitials';

describe('getAppInitials', () => {
  it.each([
    ['Moyua', 'MO'],
    ['NEW APP', 'NA'],
    ['tarifas proveedor', 'TP'],
    ['MattinAI Demo App', 'MD'],
    ['IPCEI-AI', 'IP'],
    ['A', 'A'],
    ['  mi   proyecto  ', 'P'],
    ['  tarifas   proveedor  ', 'TP'],
    ['uno dos', 'UD'],
    ['Alfa Beta Gamma', 'AB'],
    ['', ''],
  ])('%j -> %j', (name, expected) => {
    expect(getAppInitials(name)).toBe(expected);
  });

  it('handles missing names', () => {
    expect(getAppInitials(undefined)).toBe('');
    expect(getAppInitials(null)).toBe('');
  });
});
