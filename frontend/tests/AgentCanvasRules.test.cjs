const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function load(relPath) {
  const source = fs.readFileSync(path.join(__dirname, relPath), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  const helpers = {};
  vm.runInNewContext(compiled, { exports: helpers });
  return helpers;
}

const ports = load('../src/components/visual-editor/agent-canvas/agentPorts.ts');
const rules = load('../src/components/visual-editor/agent-canvas/connectionRules.ts');
const { AGENT_PORTS, OCR_PORTS } = ports;
const { canConnect, canDisconnect, wouldCreateToolCycle } = rules;

const toolsPort = AGENT_PORTS.find((def) => def.id === 'tools');
const visionPort = OCR_PORTS.find((def) => def.id === 'vision');
const modelPort = AGENT_PORTS.find((def) => def.id === 'model');
const videoPort = AGENT_PORTS.find((def) => def.id === 'video');
const mediaPort = AGENT_PORTS.find((def) => def.id === 'media_embedding');

const base = {
  canEdit: true,
  agentId: 1,
  agentType: 'agent',
  hasMemory: false,
  port: toolsPort,
  kind: 'agent',
  pieceId: 2,
  toolEdges: {},
};

// Rule results come from the vm realm, so JSON round-trip them before deepEqual.
const plain = (value) => JSON.parse(JSON.stringify(value));

test('refuses connecting anything from a read-only viewer', () => {
  const result = canConnect({ ...base, canEdit: false });
  assert.deepEqual(plain(result), { ok: false, reason: { key: 'agentCanvas.rules.readOnly' } });
});

test('refuses a piece kind the port does not accept', () => {
  const result = canConnect({ ...base, port: visionPort, kind: 'skill' });
  assert.deepEqual(plain(result), { ok: false, reason: { key: 'agentCanvas.rules.wrongPort', params: { kind: 'skill', port: 'vision', portLabel: 'Vision' } } });
});

test('refuses an agent that would use itself as a tool', () => {
  const result = canConnect({ ...base, pieceId: 1 });
  assert.deepEqual(plain(result), { ok: false, reason: { key: 'agentCanvas.rules.selfTool' } });
});

test('refuses a direct and an indirect tool cycle', () => {
  const direct = canConnect({ ...base, toolEdges: { 2: [1] } });
  assert.deepEqual(plain(direct), {
    ok: false,
    reason: { key: 'agentCanvas.rules.toolLoop' },
  });
  const indirect = canConnect({ ...base, toolEdges: { 2: [3], 3: [1] } });
  assert.deepEqual(plain(indirect), {
    ok: false,
    reason: { key: 'agentCanvas.rules.toolLoop' },
  });
  assert.equal(wouldCreateToolCycle(1, 2, { 2: [1] }), true);
  assert.equal(wouldCreateToolCycle(1, 2, { 2: [3], 3: [1] }), true);
  assert.equal(wouldCreateToolCycle(1, 2, { 3: [1] }), false);
});

test('refuses connecting a retired service', () => {
  const result = canConnect({ ...base, port: modelPort, kind: 'ai_service', lifecycleStatus: 'retired' });
  assert.deepEqual(plain(result), { ok: false, reason: { key: 'agentCanvas.rules.retired' } });
});

test('connects a deprecated service with a warning', () => {
  const result = canConnect({ ...base, port: modelPort, kind: 'ai_service', lifecycleStatus: 'deprecated' });
  assert.deepEqual(plain(result), { ok: true, warning: { key: 'agentCanvas.rules.deprecated' } });
});

test('refuses an AI service without video support on the Video port', () => {
  const refused = canConnect({ ...base, port: videoPort, kind: 'ai_service', supportsVideo: false });
  assert.deepEqual(plain(refused), { ok: false, reason: { key: 'agentCanvas.rules.noVideo' } });
  // An option list without the flag must not unlock the port either.
  const unknown = canConnect({ ...base, port: videoPort, kind: 'ai_service' });
  assert.deepEqual(plain(unknown), { ok: false, reason: { key: 'agentCanvas.rules.noVideo' } });
});

test('connects an AI service with video support on the Video port', () => {
  const result = canConnect({ ...base, port: videoPort, kind: 'ai_service', supportsVideo: true });
  assert.deepEqual(plain(result), { ok: true });
});

test('refuses disconnecting the media embedding of a conversational agent', () => {
  const refused = canDisconnect({ canEdit: true, agentType: 'agent', hasMemory: true, port: mediaPort });
  assert.deepEqual(plain(refused), {
    ok: false,
    reason: { key: 'agentCanvas.rules.needsMediaEmbedding' },
  });
  assert.deepEqual(
    plain(canDisconnect({ canEdit: true, agentType: 'agent', hasMemory: false, port: mediaPort })),
    { ok: true },
  );
});

test('refuses disconnections from read-only viewers, allows retired services', () => {
  assert.deepEqual(
    plain(canDisconnect({ canEdit: false, agentType: 'agent', hasMemory: false, port: modelPort })),
    { ok: false, reason: { key: 'agentCanvas.rules.readOnly' } },
  );
  // Lifecycle never blocks a disconnect: the Pick carries no status at all.
  assert.deepEqual(
    plain(canDisconnect({ canEdit: true, agentType: 'agent', hasMemory: false, port: modelPort })),
    { ok: true },
  );
});
