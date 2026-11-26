const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/components/visual-editor/agent-canvas/canvasLayout.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const helpers = {};
vm.runInNewContext(compiled, { exports: helpers });
const { layoutKey, loadLayout, saveLayout } = helpers;

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = v;
    },
  };
}

test('builds the per-agent storage key', () => {
  assert.equal(layoutKey(3, 7), 'mattin.agentCanvas.v1.3.7');
});

test('round-trips a saved layout', () => {
  const storage = fakeStorage();
  const layout = { positions: { 'silo:3': { x: 12.5, y: -40 } }, loose: ['ai_service:1'] };

  saveLayout(storage, 3, 7, layout);
  assert.deepEqual(JSON.parse(JSON.stringify(loadLayout(storage, 3, 7, new Set(['silo:3', 'ai_service:1'])))), layout);
});

test('drops entries whose node ids are not on the canvas', () => {
  const storage = fakeStorage({
    'mattin.agentCanvas.v1.3.7': JSON.stringify({
      positions: { 'silo:3': { x: 1, y: 2 }, 'mcp:9': { x: 5, y: 5 } },
      loose: ['ai_service:1', 'agent:2'],
    }),
  });

  assert.deepEqual(JSON.parse(JSON.stringify(loadLayout(storage, 3, 7, new Set(['silo:3', 'ai_service:1'])))), {
    positions: { 'silo:3': { x: 1, y: 2 } },
    loose: ['ai_service:1'],
  });
});

test('returns an empty layout when storage is null or the key is missing', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(loadLayout(null, 3, 7, new Set()))), { positions: {}, loose: [] });
  assert.deepEqual(JSON.parse(JSON.stringify(loadLayout(fakeStorage(), 3, 7, new Set()))), { positions: {}, loose: [] });
});

test('returns an empty layout on invalid JSON', () => {
  const storage = fakeStorage({ 'mattin.agentCanvas.v1.3.7': '{not json' });

  assert.deepEqual(JSON.parse(JSON.stringify(loadLayout(storage, 3, 7, new Set()))), { positions: {}, loose: [] });
});

test('drops stored values with the wrong shape instead of throwing', () => {
  const storage = fakeStorage({
    'mattin.agentCanvas.v1.3.7': JSON.stringify({
      positions: 'nope',
      loose: { not: 'an array' },
    }),
  });

  assert.deepEqual(JSON.parse(JSON.stringify(loadLayout(storage, 3, 7, new Set(['silo:3'])))), {
    positions: {},
    loose: [],
  });

  const storage2 = fakeStorage({
    'mattin.agentCanvas.v1.3.7': JSON.stringify({
      positions: { 'silo:3': { x: 'left', y: null }, 'silo:4': 7 },
      loose: [42, 'silo:3'],
    }),
  });

  assert.deepEqual(JSON.parse(JSON.stringify(loadLayout(storage2, 3, 7, new Set(['silo:3', 'silo:4'])))), {
    positions: {},
    loose: ['silo:3'],
  });
});

test('returns an empty layout when getItem throws', () => {
  const storage = {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {},
  };

  assert.deepEqual(JSON.parse(JSON.stringify(loadLayout(storage, 3, 7, new Set()))), { positions: {}, loose: [] });
});

test('saveLayout swallows storage failures', () => {
  const storage = { getItem: () => null, setItem: () => { throw new Error('quota exceeded'); } };

  assert.doesNotThrow(() => saveLayout(storage, 3, 7, { positions: { 'silo:3': { x: 1, y: 2 } }, loose: [] }));
});
