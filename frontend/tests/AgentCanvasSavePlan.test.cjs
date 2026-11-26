const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/components/visual-editor/agent-canvas/savePlan.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const helpers = {};
vm.runInNewContext(compiled, { exports: helpers });
const { planConnect, createSaveQueue } = helpers;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('plans the is_tool toggle first for a non-tool agent piece on tools', () => {
  const steps = planConnect({
    agentId: 1,
    port: 'tools',
    kind: 'agent',
    pieceId: 2,
    patch: { tool_ids: [2] },
    targetIsTool: false,
    pieceName: 'Helper',
  });
  assert.deepEqual(JSON.parse(JSON.stringify(steps)), [
    { agentId: 2, patch: { is_tool: true }, toast: { key: 'agentCanvas.save.nowTool', params: { name: 'Helper' } } },
    { agentId: 1, patch: { tool_ids: [2] }, toast: { key: 'agentCanvas.save.connected', params: { name: 'Helper' } } },
  ]);
});

test('keeps a single step when the piece is already a tool or not an agent', () => {
  assert.deepEqual(
    JSON.parse(
      JSON.stringify(
        planConnect({
          agentId: 1,
          port: 'tools',
          kind: 'agent',
          pieceId: 2,
          patch: { tool_ids: [2] },
          targetIsTool: true,
          pieceName: 'Helper',
        }),
      ),
    ),
    [{ agentId: 1, patch: { tool_ids: [2] }, toast: { key: 'agentCanvas.save.connected', params: { name: 'Helper' } } }],
  );
  assert.deepEqual(
    JSON.parse(
      JSON.stringify(planConnect({ agentId: 1, port: 'tools', kind: 'mcp', pieceId: 2, patch: { mcp_config_ids: [2] }, pieceName: 'MCP' })),
    ),
    [{ agentId: 1, patch: { mcp_config_ids: [2] }, toast: { key: 'agentCanvas.save.connected', params: { name: 'MCP' } } }],
  );
});

test('turns on the code interpreter together with the sandbox patch without mutating it', () => {
  const patch = { sandbox_service_id: 4 };
  const steps = planConnect({
    agentId: 1,
    port: 'sandbox',
    kind: 'sandbox',
    pieceId: 4,
    patch,
    codeInterpreterOn: false,
    pieceName: 'Python Box',
  });
  assert.deepEqual(JSON.parse(JSON.stringify(steps)), [
    {
      agentId: 1,
      patch: { sandbox_service_id: 4, enable_code_interpreter: true },
      toast: { key: 'agentCanvas.save.codeInterpreterOn', params: { name: 'Python Box' } },
    },
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(patch)), { sandbox_service_id: 4 });
});

test('announces a replacement on single-valued ports', () => {
  const steps = planConnect({
    agentId: 1,
    port: 'model',
    kind: 'ai_service',
    pieceId: 4,
    patch: { service_id: 4 },
    replacedName: 'GPT-4o',
    pieceName: 'Claude',
  });
  assert.deepEqual(JSON.parse(JSON.stringify(steps)), [
    { agentId: 1, patch: { service_id: 4 }, toast: { key: 'agentCanvas.save.replaced', params: { replaced: 'GPT-4o', name: 'Claude' } } },
  ]);
});

test('keeps the code-interpreter toast over the replace toast', () => {
  const steps = planConnect({
    agentId: 1,
    port: 'sandbox',
    kind: 'sandbox',
    pieceId: 4,
    patch: { sandbox_service_id: 4 },
    codeInterpreterOn: false,
    replacedName: 'Old Box',
    pieceName: 'Python Box',
  });
  assert.deepEqual(JSON.parse(JSON.stringify(steps)), [
    {
      agentId: 1,
      patch: { sandbox_service_id: 4, enable_code_interpreter: true },
      toast: { key: 'agentCanvas.save.codeInterpreterOn', params: { name: 'Python Box' } },
    },
  ]);
});

test('runs same-key tasks one at a time, in order', async () => {
  const queue = createSaveQueue();
  const order = [];
  const a = queue.run(1, async () => {
    order.push('a-start');
    await sleep(20);
    order.push('a-end');
    return 'a';
  });
  const b = queue.run(1, async () => {
    order.push('b-start');
    order.push('b-end');
    return 'b';
  });
  assert.deepEqual(await Promise.all([a, b]), ['a', 'b']);
  assert.deepEqual(order, ['a-start', 'a-end', 'b-start', 'b-end']);
});

test('lets the next task run after a failed one and rejects with its own error', async () => {
  const queue = createSaveQueue();
  const order = [];
  const a = queue.run(1, async () => {
    order.push('a');
    throw new Error('first failed');
  });
  const b = queue.run(1, async () => {
    order.push('b');
    return 'b-value';
  });
  await assert.rejects(a, { message: 'first failed' });
  assert.equal(await b, 'b-value');
  assert.deepEqual(order, ['a', 'b']);
});

test('runs different keys independently', async () => {
  const queue = createSaveQueue();
  const order = [];
  const a = queue.run(1, async () => {
    order.push('a-start');
    await sleep(20);
    order.push('a-end');
  });
  const b = queue.run(2, async () => {
    order.push('b-start');
    order.push('b-end');
  });
  await Promise.all([a, b]);
  assert.deepEqual(order, ['a-start', 'b-start', 'b-end', 'a-end']);
});
