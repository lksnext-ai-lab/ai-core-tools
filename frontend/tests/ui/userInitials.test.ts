import { describe, expect, it } from 'vitest';

import { getUserInitials } from '../../src/utils/userInitials';

describe('getUserInitials', () => {
  it.each([
    ['Aritz Galdos', 'a@x.com', 'AG'],
    ['  aritz   galdos otermin ', undefined, 'AG'],
    ['Aritz', 'a@x.com', 'A'],
    [undefined, 'zeta@x.com', 'Z'],
    ['', '', 'U'],
    [null, null, 'U'],
  ])('%j / %j -> %j', (name, email, expected) => {
    expect(getUserInitials(name, email)).toBe(expected);
  });
});
