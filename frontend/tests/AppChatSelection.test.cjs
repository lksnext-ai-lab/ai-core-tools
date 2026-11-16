const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function load() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'src/components/chat/chatSelection.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true },
  }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, { exports, require: () => assert.fail('no runtime dependencies expected') });
  return exports;
}

const m = load();

function makeOptions(overrides = {}) {
  return {
    ai_services: [
      { service_id: 1, name: 'A', is_system: false, lifecycle_status: 'active' },
      { service_id: 2, name: 'B', is_system: false, lifecycle_status: 'deprecated' },
      { service_id: 3, name: 'C', is_system: false, lifecycle_status: 'retired' },
    ],
    silos: [
      { silo_id: 10, name: 'S10', source_type: 'repository' },
      { silo_id: 11, name: 'S11', source_type: 'silo', disabled_reason: 'embedding_service_retired' },
    ],
    skills: [{ skill_id: 20, name: 'K20', is_system: false }],
    mcp_configs: [{ config_id: 30, name: 'M30' }],
    default_selection: { ai_service_id: 1, silo_id: 10, skill_ids: [20], mcp_config_ids: [] },
    default_warnings: [],
    has_usable_model: true,
    ...overrides,
  };
}

const sel = (over = {}) => ({ ai_service_id: 1, silo_id: null, skill_ids: [], mcp_config_ids: [], ...over });

test('reducer: each action changes only its field and a model pick bootstraps an empty selection', () => {
  const start = sel({ silo_id: 10, skill_ids: [20] });
  assert.deepEqual({ ...m.selectionReducer(start, { type: 'setModel', id: 2 }) }, { ...start, ai_service_id: 2 });
  assert.equal(m.selectionReducer(start, { type: 'setSilo', id: null }).silo_id, null);
  assert.deepEqual(JSON.parse(JSON.stringify(m.selectionReducer(start, { type: 'setSkills', ids: [1, 2] }).skill_ids)), [1, 2]);
  assert.deepEqual(JSON.parse(JSON.stringify(m.selectionReducer(start, { type: 'setMcpConfigs', ids: [5] }).mcp_config_ids)), [5]);
  assert.equal(m.selectionReducer(start, { type: 'replace', selection: null }), null);
  assert.equal(m.selectionReducer(null, { type: 'setSilo', id: 3 }), null);
  assert.equal(m.selectionReducer(null, { type: 'setModel', id: 4 }).ai_service_id, 4);
  assert.notEqual(m.selectionReducer(start, { type: 'setSkills', ids: start.skill_ids }).skill_ids, start.skill_ids);
});

test('new conversation starts from the user default (AC-10)', () => {
  const r = m.resolveInitialSelection(null, makeOptions());
  assert.deepEqual(JSON.parse(JSON.stringify(r.selection)), { ai_service_id: 1, silo_id: 10, skill_ids: [20], mcp_config_ids: [] });
  assert.equal(r.warnings.length, 0);
});

test('default whose silo was deleted keeps the model, drops the silo and warns (AC-10)', () => {
  const options = makeOptions({
    default_selection: sel({ silo_id: 99 }),
    default_warnings: [{ kind: 'silo', id: 99 }],
  });
  const r = m.resolveInitialSelection(null, options);
  assert.equal(r.selection.ai_service_id, 1);
  assert.equal(r.selection.silo_id, null);
  assert.deepEqual(JSON.parse(JSON.stringify(r.warnings)), [{ kind: 'silo', id: 99 }]);
});

test('an open conversation wins over the default (AC-11)', () => {
  const r = m.resolveInitialSelection(sel({ ai_service_id: 2 }), makeOptions());
  assert.equal(r.selection.ai_service_id, 2);
  assert.equal(r.selection.silo_id, null);
});

test('retired model, disabled silo and unknown skill / mcp are dropped with warnings', () => {
  const candidate = sel({ ai_service_id: 3, silo_id: 11, skill_ids: [20, 21], mcp_config_ids: [30, 31] });
  const r = m.resolveInitialSelection(candidate, makeOptions(), [{ kind: 'skill', id: 21 }]);
  assert.equal(r.selection.ai_service_id, 1, 'falls back to the default model');
  assert.equal(r.selection.silo_id, null);
  assert.deepEqual(JSON.parse(JSON.stringify(r.selection.skill_ids)), [20]);
  assert.deepEqual(JSON.parse(JSON.stringify(r.selection.mcp_config_ids)), [30]);
  const keys = r.warnings.map((w) => `${w.kind}:${w.id}`).sort();
  assert.deepEqual(JSON.parse(JSON.stringify(keys)), ['ai_service:3', 'mcp_config:31', 'silo:11', 'skill:21']);
});

test('no selectable model gives a null selection', () => {
  const options = makeOptions({
    ai_services: [{ service_id: 3, name: 'C', is_system: false, lifecycle_status: 'retired' }],
    default_selection: null,
    has_usable_model: false,
  });
  assert.equal(m.resolveInitialSelection(null, options).selection, null);
  assert.equal(m.resolveInitialSelection(sel(), options).selection, null);
});

test('sendBlockReason covers loading, empty options and no selection', () => {
  assert.equal(m.sendBlockReason(null, null), 'loading');
  assert.equal(m.sendBlockReason(makeOptions({ has_usable_model: false }), null), 'noUsableModel');
  assert.equal(m.sendBlockReason(makeOptions({ ai_services: [] }), sel()), 'noUsableModel');
  assert.equal(m.sendBlockReason(makeOptions(), null), 'noSelection');
  assert.equal(m.sendBlockReason(makeOptions(), sel()), null);
});

test('sendBlockReason: a selection still being resolved is "loading", but an empty App stays "noUsableModel"', () => {
  assert.equal(m.sendBlockReason(makeOptions(), sel(), false), 'loading');
  assert.equal(m.sendBlockReason(makeOptions(), null, false), 'loading');
  assert.equal(m.sendBlockReason(makeOptions({ has_usable_model: false }), null, false), 'noUsableModel');
  assert.equal(m.sendBlockReason(makeOptions(), null, true), 'noSelection');
});

test('describeWarnings names known resources, dedupes and falls back to the generic message', () => {
  const out = m.describeWarnings(
    [{ kind: 'mcp_config', id: 30 }, { kind: 'mcp_config', id: 30 }, { kind: 'skill', id: 77 }],
    makeOptions(),
  );
  assert.equal(out.length, 2);
  assert.deepEqual(JSON.parse(JSON.stringify(out[0])), { key: 'mcp_configNamed', values: { name: 'M30' } });
  assert.deepEqual(JSON.parse(JSON.stringify(out[1])), { key: 'skill', values: {} });
  assert.equal(m.describeWarnings([{ kind: 'silo', id: 1 }], null)[0].key, 'silo');
});

const fallback = (id) => `Source #${id}`;

test('buildTurnMeta marks deleted resources from history and uses names from metadata while streaming', () => {
  const turn = {
    turn_index: 0, ai_service_id: null, ai_service_name: 'Old model', ai_service_deleted: true,
    silo_id: 5, silo_name: null, silo_deleted: false,
    skills: [{ id: 1, name: 'Sk', deleted: true }], mcp_configs: [{ id: 2, name: 'Mc', deleted: false }],
    created_at: '', warnings: [],
  };
  const fromTurn = m.buildTurnMeta(turn, null, fallback);
  assert.equal(fromTurn.model.label, 'Old model');
  assert.equal(fromTurn.model.deleted, true);
  assert.equal(fromTurn.source.label, 'Source #5');
  assert.equal(fromTurn.skills[0].deleted, true);

  const config = {
    ai_service: { id: 1, name: 'Live' }, silo: { id: 6, name: 'Docs' }, skills: [], mcp_configs: [], warnings: [],
  };
  const fromConfig = m.buildTurnMeta(null, config, fallback);
  assert.equal(fromConfig.model.label, 'Live');
  assert.equal(fromConfig.source.label, 'Docs');
  // The finished turn wins over the streaming summary.
  assert.equal(m.buildTurnMeta(turn, config, fallback).model.label, 'Old model');
  assert.equal(m.buildTurnMeta(null, null, fallback), null);
  assert.equal(m.buildTurnMeta({ ...turn, silo_id: null }, null, fallback).source, null);
});

test('route helpers', () => {
  assert.equal(m.parseConversationId('12'), 12);
  assert.equal(m.parseConversationId('0'), null);
  assert.equal(m.parseConversationId('x1'), null);
  assert.equal(m.parseConversationId(undefined), null);
  assert.equal(m.chatPath(3), '/apps/3/chat');
  assert.equal(m.chatPath(3, 9), '/apps/3/chat/9');
});

test('a retired or vanished selected model blocks sending until another is picked (M3)', () => {
  const options = makeOptions();
  assert.equal(m.sendBlockReason(options, sel({ ai_service_id: 3 })), 'modelRetired');
  assert.equal(m.sendBlockReason(options, sel({ ai_service_id: 999 })), 'modelRetired');
  assert.equal(m.sendBlockReason(options, sel({ ai_service_id: 2 })), null, 'deprecated is still allowed');
});

test('new conversation: defaults after an opened conversation, current selection otherwise (M4)', () => {
  const options = makeOptions();
  const current = sel({ ai_service_id: 2, silo_id: null, skill_ids: [] });
  const afterOpened = m.resolveNewConversationSelection(options, current, true);
  assert.deepEqual(JSON.parse(JSON.stringify(afterOpened.selection)), { ai_service_id: 1, silo_id: 10, skill_ids: [20], mcp_config_ids: [] });
  const untouched = m.resolveNewConversationSelection(options, current, false);
  assert.equal(untouched.selection, current);
  const first = m.resolveNewConversationSelection(options, null, false);
  assert.equal(first.selection.ai_service_id, 1);
});

test('defaults after "New" apply only while the request is current, on the new chat and untouched', () => {
  const d = (...args) => ({ ...m.decideNewChatDefaults(...args) });
  assert.deepEqual(d(3, 3, true, false), { resolve: true, applySelection: true });
  assert.deepEqual(d(3, 3, true, true), { resolve: true, applySelection: false }, 'user choice is kept but sending unblocks');
  assert.deepEqual(d(3, 4, true, false), { resolve: false, applySelection: false }, 'a newer request superseded it');
  assert.deepEqual(d(3, 3, false, false), { resolve: false, applySelection: false }, 'user moved to another conversation');
});

test('attachmentIndexingNotice: only an explicit enabled=false raises it; a missing field means enabled', () => {
  const withIndexing = (attachment_indexing) => makeOptions({ attachment_indexing });
  assert.equal(m.attachmentIndexingNotice(null), null);
  assert.equal(m.attachmentIndexingNotice(makeOptions()), null);
  assert.equal(m.attachmentIndexingNotice(withIndexing(null)), null);
  assert.equal(m.attachmentIndexingNotice(withIndexing({ enabled: true, reason: null })), null);
  assert.equal(m.attachmentIndexingNotice(withIndexing({ enabled: false, reason: 'no_default_embedding_service' })), 'noDefault');
  assert.equal(m.attachmentIndexingNotice(withIndexing({ enabled: false, reason: 'embedding_service_retired' })), 'retired');
  assert.equal(m.attachmentIndexingNotice(withIndexing({ enabled: false, reason: null })), 'unavailable');
  assert.equal(m.attachmentIndexingNotice(withIndexing({ enabled: false, reason: 'something_new' })), 'unavailable');
});
