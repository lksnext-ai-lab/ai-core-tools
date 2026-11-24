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

test('sandbox_output warnings carry a count: one per turn with the largest count, never a name', () => {
  const warnings = [{ kind: 'sandbox_output', id: 2 }, { kind: 'skill', id: 20 }, { kind: 'sandbox_output', id: 5 }, { kind: 'sandbox_output', id: 3 }];
  assert.deepEqual(JSON.parse(JSON.stringify(m.dedupeWarnings(warnings))), [
    { kind: 'sandbox_output', id: 5 },
    { kind: 'skill', id: 20 },
  ]);
  const out = m.describeWarnings(warnings, makeOptions());
  assert.deepEqual(JSON.parse(JSON.stringify(out[0])), { key: 'sandbox_output', values: { count: 5 } });
  assert.ok(m.WARNING_KINDS.includes('sandbox_output'));
});

test('describeWarnings ignores a kind from a newer backend instead of showing a raw key', () => {
  const out = m.describeWarnings([{ kind: 'brand_new', id: 1 }, { kind: 'silo', id: 1 }], null);
  assert.deepEqual(JSON.parse(JSON.stringify(out)), [{ key: 'silo', values: {} }]);
  assert.equal(m.describeWarnings([{ kind: 'brand_new', id: 1 }], null).length, 0);
});

test('sandbox_output has plural forms in en and es', () => {
  for (const language of ['en', 'es', 'eu']) {
    const w = require(`../src/i18n/locales/${language}/common.json`).appChat.warnings;
    assert.match(w.sandbox_output_one, /\{\{count\}\}/);
    assert.match(w.sandbox_output_other, /\{\{count\}\}/);
    assert.notEqual(w.sandbox_output_one, w.sandbox_output_other);
  }
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

test('codeInterpreterNotice: not-set-up reasons need a selected skill; retired, provider and unknown always show', () => {
  const withBlock = (code_interpreter) => makeOptions({ code_interpreter });
  const none = { ai_service_id: 1, silo_id: null, skill_ids: [], mcp_config_ids: [] };
  const some = { ...none, skill_ids: [20] };
  const reason = (r) => withBlock({ enabled: false, reason: r });

  // Nothing to say: no options, no block, enabled.
  for (const sel of [null, none, some]) {
    assert.equal(m.codeInterpreterNotice(null, sel), null);
    assert.equal(m.codeInterpreterNotice(makeOptions(), sel), null);
    assert.equal(m.codeInterpreterNotice(withBlock(null), sel), null);
    assert.equal(m.codeInterpreterNotice(withBlock({ enabled: true, reason: null }), sel), null);
  }
  // Not set up: only with a skill selected.
  for (const [r, kind] of [['disabled_in_app_settings', 'disabled']]) {
    assert.equal(m.codeInterpreterNotice(reason(r), none), null, r);
    assert.equal(m.codeInterpreterNotice(reason(r), null), null, r);
    assert.equal(m.codeInterpreterNotice(reason(r), some), kind, r);
  }
  // Was working, stopped: always.
  for (const [r, kind] of [
    ['sandbox_service_retired', 'retired'],
    ['sandbox_provider_unavailable', 'providerUnavailable'],
    [null, 'unavailable'],
    ['something_new', 'unavailable'],
    ['no_default_sandbox_service', 'unavailable'], // retired reason from an older backend
  ]) {
    assert.equal(m.codeInterpreterNotice(reason(r), none), kind, String(r));
    assert.equal(m.codeInterpreterNotice(reason(r), some), kind, String(r));
  }
});

test('codeInterpreter notice and settings keys exist in en and es, and reused keys are not duplicated', () => {
  const kinds = ['title', 'disabled', 'retired', 'providerUnavailable', 'unavailable'];
  const texts = {};
  for (const language of ['en', 'es', 'eu']) {
    const common = require(`../src/i18n/locales/${language}/common.json`);
    const appChat = common.appChat;
    for (const kind of kinds) assert.equal(typeof appChat.codeInterpreter[kind], 'string', `${language}.${kind}`);
    assert.deepEqual(Object.keys(appChat.codeInterpreter).sort(), [...kinds].sort());
    assert.equal(typeof appChat.attachmentIndexing.configureLink, 'string');
    assert.equal(typeof appChat.attachmentIndexing.askAdmin, 'string');
    for (const key of ['chatCodeInterpreter', 'chatCodeInterpreterHelp']) {
      assert.equal(typeof common.appSettingsPage[key], 'string', `${language}.${key}`);
    }
    texts[language] = appChat.codeInterpreter;
  }
  for (const kind of kinds) assert.notEqual(texts.en[kind], texts.es[kind], kind);
});

test('accessibility texts exist in en and es with the same placeholders, and the Spanish Chat wording is consistent', () => {
  const keys = [
    ['agentPlayground', 'chat', 'generatingFor'], ['agentPlayground', 'chat', 'statusAnswering'],
    ['agentPlayground', 'chat', 'statusReady'], ['agentPlayground', 'chat', 'statusFailed'],
    ['agentPlayground', 'chat', 'statusReset'], ['agentPlayground', 'chat', 'speakerYou'],
    ['agentPlayground', 'chat', 'speakerAssistant'], ['agentPlayground', 'chat', 'messagesRegion'],
    ['agentPlayground', 'chat', 'resetConfirmTitle'], ['agentPlayground', 'chat', 'resetConfirmMessage'],
    ['agentPlayground', 'chat', 'resetFailed'], ['conversationSidebar', 'renameNamed'],
    ['conversationSidebar', 'deleteNamed'], ['appSettingsPage', 'systemServiceOption'], ['confirm'],
  ];
  const locales = {
    en: require('../src/i18n/locales/en/common.json'),
    es: require('../src/i18n/locales/es/common.json'),
  };
  const placeholders = (text) => (text.match(/\{\{\w+\}\}/g) ?? []).sort().join();
  for (const path of keys) {
    const [en, es] = ['en', 'es'].map((l) => path.reduce((v, part) => v?.[part], locales[l]));
    assert.equal(typeof en, 'string', `en.${path.join('.')}`);
    assert.equal(typeof es, 'string', `es.${path.join('.')}`);
    assert.equal(placeholders(en), placeholders(es), path.join('.'));
  }
  // One word for files across the Chat texts, and counts that do not depend on grammatical gender.
  const chatEs = JSON.stringify(locales.es.appChat);
  assert.doesNotMatch(chatEs, /fichero/i);
  assert.doesNotMatch(JSON.stringify(locales.es.appChat.selection), /seleccionadas?\b|quitada\b/);
});

test('leaving an App and removing a collaborator warn that the member Chat data is deleted (en and es)', () => {
  const en = require('../src/i18n/locales/en/common.json');
  const es = require('../src/i18n/locales/es/common.json');
  assert.match(en.appsPage.confirmLeaveMessage, /Your Chat conversations and files in this app will be deleted\.$/);
  assert.match(en.collaborationPage.remove.namedMessage, /Their Chat conversations and files in this app will be deleted\.$/);
  assert.match(en.collaborationPage.remove.message, /Their Chat conversations and files in this app will be deleted\.$/);
  assert.match(es.appsPage.confirmLeaveMessage, /Se eliminarán tus conversaciones y archivos del Chat en esta aplicación\.$/);
  assert.match(es.collaborationPage.remove.namedMessage, /Se eliminarán sus conversaciones y archivos del Chat en esta aplicación\.$/);
  assert.match(es.collaborationPage.remove.message, /Se eliminarán sus conversaciones y archivos del Chat en esta aplicación\.$/);
  // The named texts keep their interpolation.
  assert.match(en.appsPage.confirmLeaveMessage, /\{\{name\}\}/);
  assert.match(es.collaborationPage.remove.namedMessage, /\{\{name\}\}/);
});
