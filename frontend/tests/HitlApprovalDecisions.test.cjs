const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/components/playground/hitlApprovalDecisions.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const helpers = {};
vm.runInNewContext(compiled, { exports: helpers });
const { buildHitlDecisions } = helpers;

const actions = [
  {
    action_id: 'call-1',
    name: 'search',
    args: { query: 'status' },
    allowed_decisions: ['approve', 'reject'],
  },
  {
    action_id: 'call-2',
    name: 'send_email',
    args: { to: 'user@example.com' },
    allowed_decisions: ['approve', 'reject'],
  },
];

test('builds a separate decision for each tool in the same approval batch', () => {
  const result = buildHitlDecisions(actions, ['', ''], ['approve', 'reject']);

  assert.deepEqual(JSON.parse(JSON.stringify(result.decisions)), [
    { action_id: 'call-1', type: 'approve' },
    {
      action_id: 'call-2',
      type: 'reject',
      message: 'The user rejected the call to send_email. Do not call it again unless the user asks for it.',
    },
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(result.errors)), [null, null]);
});

test('does not submit until every tool has an individual decision', () => {
  const result = buildHitlDecisions(actions, ['', ''], ['approve', null]);

  assert.equal(result.decisions, null);
  assert.deepEqual(JSON.parse(JSON.stringify(result.errors)), [null, null]);
});

test('edited arguments produce an edit decision only for the selected tool', () => {
  const editableActions = [
    { ...actions[0], allowed_decisions: ['approve', 'edit', 'reject'] },
    actions[1],
  ];
  const result = buildHitlDecisions(
    editableActions,
    ['{"query":"new status"}', ''],
    ['approve', 'approve'],
  );

  assert.deepEqual(JSON.parse(JSON.stringify(result.decisions)), [
    { action_id: 'call-1', type: 'edit', args: { query: 'new status' } },
    { action_id: 'call-2', type: 'approve' },
  ]);
});
