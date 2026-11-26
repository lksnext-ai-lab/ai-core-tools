const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function load(relPath) {
  const source = fs.readFileSync(path.join(__dirname, relPath), 'utf8');
  return ts.transpileModule(source, {
    // The app builds with ES2022; without a target here transpileModule
    // downlevels iterator spreads into broken ES5 helper calls.
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
}

function runInVm(code, modules = {}) {
  const helpers = {};
  vm.runInNewContext(code, {
    exports: helpers,
    module: { exports: helpers },
    require: (specifier) => modules[specifier] ?? {},
  });
  return helpers;
}

// The component module with every import stubbed; only its module-level
// helpers are exercised (the real agentPorts supplies portsFor).
const ports = runInVm(load('../src/components/visual-editor/agent-canvas/agentPorts.ts'));
const canvas = runInVm(load('../src/components/visual-editor/agent-canvas/AgentCanvas.tsx'), {
  './agentPorts': ports,
});

const agent = { agent_id: 1, name: 'Assistant', type: 'agent' };
const pieces = [
  { kind: 'ai_service', id: 5, name: 'GPT' },
  { kind: 'silo', id: 9, name: 'Docs' },
];
const connected = [{ port: 'model', kind: 'ai_service', id: 5 }];

function buildNodes(canEdit, looseNodeIds) {
  return canvas.buildFlowNodes(agent, 'agent', connected, pieces, {}, canEdit, looseNodeIds, null, false);
}

test('connected piece cards are deletable to disconnect; loose cards stay deletable; the agent never is', () => {
  const byId = new Map(buildNodes(true, ['silo:9']).map((node) => [node.id, node]));
  assert.equal(byId.get('agent:1').deletable, false);
  assert.equal(byId.get('ai_service:5').deletable, true);
  assert.equal(byId.get('silo:9').deletable, true);
});

test('read-only viewers cannot delete any card', () => {
  const byId = new Map(buildNodes(false, ['silo:9']).map((node) => [node.id, node]));
  assert.equal(byId.get('agent:1').deletable, false);
  assert.equal(byId.get('ai_service:5').deletable, false);
  assert.equal(byId.get('silo:9').deletable, false);
});

const agentEdges = [
  { id: 'model:ai_service:5', source: 'ai_service:5', target: 'agent:1' },
  { id: 'transcription:ai_service:5', source: 'ai_service:5', target: 'agent:1' },
  { id: 'knowledge:silo:9', source: 'silo:9', target: 'agent:1' },
];
const connectedPiece = { id: 'ai_service:5', type: 'piece' };

test("a connected card's Delete collects every edge it has to the agent, even ones React Flow missed", () => {
  assert.equal(typeof canvas.deleteCandidateEdges, 'function');
  const candidates = canvas.deleteCandidateEdges([connectedPiece], [agentEdges[0]], agentEdges, 'agent:1', []);
  assert.deepEqual([...candidates.map((edge) => edge.id)].sort(), ['model:ai_service:5', 'transcription:ai_service:5']);
});

test('collected edges are deduped by id', () => {
  assert.equal(typeof canvas.deleteCandidateEdges, 'function');
  const candidates = canvas.deleteCandidateEdges(
    [connectedPiece],
    agentEdges.filter((edge) => edge.source === 'ai_service:5'),
    agentEdges,
    'agent:1',
    [],
  );
  const ids = candidates.map((edge) => edge.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.deepEqual([...ids].sort(), ['model:ai_service:5', 'transcription:ai_service:5']);
});

test('loose cards, the agent body and empty selections contribute no extra edges', () => {
  assert.equal(typeof canvas.deleteCandidateEdges, 'function');
  assert.deepEqual([...canvas.deleteCandidateEdges([{ id: 'silo:9', type: 'piece' }], [], agentEdges, 'agent:1', ['silo:9'])], []);
  assert.deepEqual([...canvas.deleteCandidateEdges([{ id: 'agent:1', type: 'agent' }], [], agentEdges, 'agent:1', [])], []);
  assert.deepEqual([...canvas.deleteCandidateEdges([], [], agentEdges, 'agent:1', [])], []);
});
