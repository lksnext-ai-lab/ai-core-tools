const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/components/visual-editor/agent-canvas/agentPorts.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const helpers = {};
vm.runInNewContext(compiled, { exports: helpers });
const { AGENT_PORTS, OCR_PORTS, portsFor, resolveDropPort, buildPortPatch, connectedPieces } = helpers;

test('exposes the agent and OCR port catalogs in canvas order', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(AGENT_PORTS.map((def) => def.id))), [
    'model',
    'knowledge',
    'skills',
    'tools',
    'output',
    'middlewares',
    'sandbox',
    'transcription',
    'video',
    'media_embedding',
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(OCR_PORTS.map((def) => def.id))), ['vision', 'text', 'output']);
  assert.deepEqual(JSON.parse(JSON.stringify(AGENT_PORTS.filter((def) => def.secondary).map((def) => def.id))), [
    'tools',
    'output',
    'middlewares',
    'sandbox',
    'media_embedding',
  ]);
});

test('resolves drop ports with per-type defaults', () => {
  assert.equal(resolveDropPort('agent', 'ai_service'), 'model');
  assert.equal(resolveDropPort('ocr_agent', 'ai_service'), 'ask');
  assert.equal(resolveDropPort('ocr_agent', 'skill'), null);
  assert.equal(resolveDropPort('agent', 'mcp'), 'tools');
});

test('adds tool agent ids idempotently on the tools port', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(buildPortPatch({ tool_ids: [1] }, 'tools', 'agent', 2, 'add'))), {
    tool_ids: [1, 2],
  });
  assert.deepEqual(JSON.parse(JSON.stringify(buildPortPatch({ tool_ids: [1, 2] }, 'tools', 'agent', 2, 'add'))), {
    tool_ids: [1, 2],
  });
});

test('picks the mcp field by piece kind on the tools port', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(buildPortPatch({}, 'tools', 'mcp', 4, 'add'))), { mcp_config_ids: [4] });
});

test('clears single-value ports to null on remove', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(buildPortPatch({ silo_id: 3 }, 'knowledge', 'silo', 3, 'remove'))), {
    silo_id: null,
  });
});

test('leaves a single-value port alone when the removed piece was already replaced', () => {
  // The port now holds B (silo 4); a stale remove of A (silo 3) must not wipe B.
  assert.deepEqual(JSON.parse(JSON.stringify(buildPortPatch({ silo_id: 4 }, 'knowledge', 'silo', 3, 'remove'))), {});
});

test('leaves a single-value port alone when it is already empty', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(buildPortPatch({ silo_id: null }, 'knowledge', 'silo', 3, 'remove'))), {});
});

test('appends middleware ids at the end', () => {
  assert.deepEqual(
    JSON.parse(JSON.stringify(buildPortPatch({ middleware_ids: [5, 6] }, 'middlewares', 'middleware', 7, 'add'))),
    { middleware_ids: [5, 6, 7] },
  );
});

test('routes OCR text drops to the shared service_id field', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(buildPortPatch({}, 'text', 'ai_service', 9, 'add'))), { service_id: 9 });
});

test('lists connected pieces per port, ignoring ports the agent type lacks', () => {
  const pieces = connectedPieces('ocr_agent', { service_id: 1, vision_service_id: 2, silo_id: 3 });
  assert.deepEqual(JSON.parse(JSON.stringify(pieces)), [
    { port: 'vision', kind: 'ai_service', id: 2 },
    { port: 'text', kind: 'ai_service', id: 1 },
  ]);
});
