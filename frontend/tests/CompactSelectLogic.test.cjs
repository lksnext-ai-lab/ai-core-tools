const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

const source = fs.readFileSync(
  path.join(__dirname, '../src/components/ui/compactSelectLogic.ts'),
  'utf8',
);
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true },
}).outputText;
const mod = { exports: {} };
new Function('module', 'exports', compiled)(mod, mod.exports);
const L = mod.exports;

const opts = [
  { value: 'a', label: 'Alpha', group: 'Source type' },
  { value: 'b', label: 'Beta', group: 'Other group' },
  { value: 'c', label: 'Alpine', group: 'Source type', disabled: true },
  { value: 'd', label: 'Delta' },
];

test('groups keep first-appearance order, numeric index and visual flat order', () => {
  const groups = L.buildGroups(opts);
  assert.deepEqual(groups.map((g) => g.index), [0, 1, 2]);
  assert.deepEqual(groups.map((g) => g.header), ['Source type', 'Other group', undefined]);
  assert.deepEqual(L.flattenGroups(groups).map((o) => o.value), ['a', 'c', 'b', 'd']);
  assert.deepEqual(groups[1].items.map((i) => i.index), [2]);
});

test('filter is case-insensitive and trims', () => {
  assert.deepEqual(L.filterOptions(opts, ' AL ').map((o) => o.value), ['a', 'c']);
  assert.equal(L.filterOptions(opts, '').length, 4);
});

test('navigation clamps and survives an empty list', () => {
  assert.equal(L.nextActiveIndex(0, 'ArrowDown', 0), 0);
  assert.equal(L.nextActiveIndex(5, 'End', 0), 0);
  assert.equal(L.nextActiveIndex(0, 'ArrowUp', 3), 0);
  assert.equal(L.nextActiveIndex(2, 'ArrowDown', 3), 2);
  assert.equal(L.nextActiveIndex(1, 'Home', 3), 0);
  assert.equal(L.nextActiveIndex(0, 'End', 3), 2);
  assert.equal(L.nextActiveIndex(0, 'PageDown', 25), 10);
  assert.equal(L.nextActiveIndex(3, 'PageUp', 25), 0);
  assert.equal(L.nextActiveIndex(99, 'ArrowDown', 3), 2);
});

test('activate does nothing on empty list or disabled option', () => {
  assert.deepEqual(L.activateResult([], 0, false, []), { kind: 'none' });
  const flat = L.flattenGroups(L.buildGroups(opts));
  assert.deepEqual(L.activateResult(flat, 1, false, []), { kind: 'none' });
  assert.deepEqual(L.activateResult(flat, 0, false, []), { kind: 'single', value: 'a' });
  // out-of-range index is clamped to the last option
  assert.deepEqual(L.activateResult(flat, 50, false, []), { kind: 'single', value: 'd' });
});

test('multiple toggles values on and off', () => {
  const flat = L.flattenGroups(L.buildGroups(opts));
  assert.deepEqual(L.activateResult(flat, 0, true, ['d']), { kind: 'multiple', selected: true, values: ['d', 'a'] });
  assert.deepEqual(L.activateResult(flat, 0, true, ['a', 'd']), { kind: 'multiple', selected: false, values: ['d'] });
  assert.deepEqual(L.activateResult(flat, 1, true, []), { kind: 'none' });
});

test('stale selected values use the fallback label or are dropped', () => {
  assert.deepEqual(L.selectedLabels(opts, ['a', 'gone']), ['Alpha']);
  assert.deepEqual(L.selectedLabels(opts, ['a', 'gone'], (v) => `${v}!`), ['Alpha', 'gone!']);
});

test('chip text: placeholder, join, summary', () => {
  assert.equal(L.chipValueText([], 'None'), 'None');
  assert.equal(L.chipValueText(['x', 'y'], 'None', () => 'many'), 'x, y');
  assert.equal(L.chipValueText(['x', 'y', 'z'], 'None', (l) => `${l.length} selected`), '3 selected');
  assert.equal(L.chipValueText(['x', 'y', 'z'], 'None'), 'x, y, z');
});

test('type-ahead jumps to the next matching label and wraps', () => {
  const flat = L.flattenGroups(L.buildGroups(opts)); // Alpha, Alpine, Beta, Delta
  assert.equal(L.typeAheadIndex(flat, 0, 'b'), 2);
  assert.equal(L.typeAheadIndex(flat, 0, 'a'), 1);
  assert.equal(L.typeAheadIndex(flat, 1, 'a'), 0);
  assert.equal(L.typeAheadIndex(flat, 0, 'alp'), 0);
  assert.equal(L.typeAheadIndex(flat, 0, 'zz'), -1);
  assert.equal(L.typeAheadIndex([], 0, 'a'), -1);
});
