const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function compile(relativePath, modules, extraGlobals = {}) {
  const source = fs.readFileSync(path.join(__dirname, '..', relativePath), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(compiled.replaceAll('import.meta', '({ env: {} })'), {
    exports,
    require: (name) => {
      assert.ok(name in modules, `Unexpected dependency: ${name}`);
      return modules[name];
    },
    ...extraGlobals,
  });
  return exports;
}

/** `apiService` double that records every call as [method, ...args]. */
function recordingApi(overrides = {}) {
  const calls = [];
  const api = new Proxy({}, {
    get(_target, method) {
      return (...args) => {
        calls.push([method, ...args]);
        const impl = overrides[method];
        return impl ? impl(...args) : Promise.resolve(`${String(method)}-result`);
      };
    },
  });
  return { api, calls };
}

function loadTransport(overrides) {
  const { api, calls } = recordingApi(overrides);
  const mod = compile('src/components/playground/chatTransport.ts', {
    '../../services/api': { apiService: api },
  }, { console });
  return { mod, calls };
}

const selectionA = { ai_service_id: 1, silo_id: null, skill_ids: [], mcp_config_ids: [] };
const selectionB = { ai_service_id: 2, silo_id: 7, skill_ids: [3], mcp_config_ids: [4] };

// ---------------------------------------------------------------- agent playground

test('playground transport wraps exactly the api.ts calls ChatInterface made before', async () => {
  const { mod, calls } = loadTransport({
    getConversationWithHistory: async () => ({ messages: [{ role: 'user', content: 'hi' }], session_id: 's1', pending_approval: null }),
    getConversationHistory: async () => ({ messages: [] }),
    createConversation: async () => ({ conversation_id: 9, session_id: 's9' }),
    getFileDownloadUrl: async () => 'https://x/file',
  });
  const t = mod.createAgentPlaygroundTransport(3, 5);
  assert.deepEqual({ ...t.capabilities }, { agentMedia: true, exposedFilters: true, approvals: true });

  const opts = { conversationId: 11, searchParams: { a: 1 }, onEvent() {}, signal: undefined };
  await t.streamMessage('hello', opts);
  const resume = { approvalId: 'ap', decisions: [{ action_id: 'x', type: 'approve' }] };
  await t.streamMessage('', { ...opts, resume });
  const history = await t.loadHistory(11);
  await t.loadHistory(null);
  const created = await t.createConversation();
  await t.resetConversation(11);
  await t.resetConversation(null);
  await t.listFiles(11);
  await t.listFiles(null);
  const file = {};
  await t.uploadFile(11, file);
  await t.removeFile(11, 'f1');
  const url = await t.getFileDownloadUrl(11, 'f1');
  await t.media.list('s1');
  await t.media.remove('s1');
  t.media.streamUrl(8, 's1');
  await t.filters.list();
  await t.filters.searchValues('field', 'q', 50);

  require('node:assert').deepEqual(calls.map((c) => c.map((a) => (a === file ? '<file>' : a))), [
    ['chatWithAgentStream', 3, 5, 'hello', opts],
    ['decideApprovalStream', 'ap', resume.decisions, { onEvent: opts.onEvent, signal: undefined }],
    ['getConversationWithHistory', 11],
    ['getConversationHistory', 3, 5],
    ['createConversation', 5],
    ['resetAgentConversation', 3, 5, 11],
    ['resetAgentConversation', 3, 5, null],
    ['listAttachedFiles', 3, 5, 11],
    ['listAttachedFiles', 3, 5, null],
    ['uploadFileForChat', 3, 5, '<file>', 11],
    ['removeAttachedFile', 3, 5, 'f1', 11],
    ['getFileDownloadUrl', 3, 5, 'f1', 11],
    ['listPlaygroundMedia', 3, 5, 's1'],
    ['deletePlaygroundMedia', 3, 5, 's1'],
    ['getPlaygroundMediaStreamUrl', 3, 5, 8, 's1'],
    ['getAgentChatFilters', 3, 5],
    ['searchAgentChatFilterValues', 3, 5, 'field', 'q', 50],
  ]);
  assert.equal(history.sessionId, 's1');
  assert.equal(history.messages.length, 1);
  assert.deepEqual({ ...created }, { conversationId: 9, sessionId: 's9' });
  assert.equal(url, 'https://x/file');
});

test('ChatInterface only keeps one direct api.ts call (cancelling an approval, playground only)', () => {
  const source = fs.readFileSync(path.join(__dirname, '../src/components/playground/ChatInterface.tsx'), 'utf8');
  const used = [...source.matchAll(/apiService\.(\w+)/g)].map((m) => m[1]);
  assert.deepEqual(used, ['cancelApproval']);
});

// ---------------------------------------------------------------- app chat

test('chat transport reads the selection at send time, once per turn', async () => {
  let current = selectionA;
  const { mod, calls } = loadTransport({ streamAppChatMessage: async () => undefined });
  const t = mod.createAppChatTransport(4, () => current);
  assert.deepEqual({ ...t.capabilities }, { agentMedia: false, exposedFilters: false, approvals: false });
  assert.equal(t.media, undefined);
  assert.equal(t.filters, undefined);

  const onEvent = () => {};
  await t.streamMessage('first', { conversationId: null, onEvent });
  current = selectionB;
  await t.streamMessage('second', { conversationId: 12, searchParams: { filter: { k: 'v' } }, onEvent });

  assert.equal(calls.length, 2);
  assert.equal(calls[0][1], 4);
  assert.equal(calls[0][2].message, 'first');
  assert.equal(calls[0][2].selection, selectionA);
  assert.equal(calls[1][2].message, 'second');
  assert.equal(calls[1][2].selection, selectionB);
  assert.equal(calls[1][2].conversationId, 12);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[1][2].searchParams)), { filter: { k: 'v' } });
});

test('chat transport fails before any request when no selection is available', async () => {
  const { mod, calls } = loadTransport({});
  const t = mod.createAppChatTransport(4, () => null);
  await assert.rejects(
    () => t.streamMessage('hi', { onEvent() {} }),
    (error) => error.name === 'ChatTransportError' && error.code === 'noSelection' && error.message === 'noSelection',
  );
  assert.equal(calls.length, 0);
});

test('chat transport creates the conversation with the current selection for an early file upload', async () => {
  let current = selectionA;
  const { mod, calls } = loadTransport({ createAppChatConversation: async () => ({ conversation_id: 31 }) });
  const t = mod.createAppChatTransport(4, () => current);
  current = selectionB;
  const created = await t.createConversation();
  assert.equal(created.conversationId, 31);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), ['createAppChatConversation', 4, { selection: selectionB }]);
});

test('chat transport makes no request without a conversation and never caches download links', async () => {
  let n = 0;
  const { mod, calls } = loadTransport({
    getAppChatFileDownload: async () => ({ download_url: `https://x/${++n}`, filename: 'a.pdf' }),
    listAppChatFiles: async () => ({ files: [{ file_id: 'f', filename: 'a.pdf', file_type: null }], total_size_bytes: 1, total_size_display: '1 B' }),
  });
  const t = mod.createAppChatTransport(4, () => selectionA);
  assert.deepEqual(JSON.parse(JSON.stringify(await t.loadHistory(null))), { messages: [] });
  assert.deepEqual(JSON.parse(JSON.stringify(await t.listFiles(null))), { files: [] });
  await t.resetConversation(null);
  await t.removeFile(null, 'f');
  assert.equal(calls.length, 0);

  assert.equal(await t.getFileDownloadUrl(6, 'f'), 'https://x/1');
  assert.equal(await t.getFileDownloadUrl(6, 'f'), 'https://x/2');
  const listed = await t.listFiles(6);
  assert.equal(listed.files[0].file_type, undefined);
});

test('chat transport carries turn events and history turns', async () => {
  const turn = { turn_index: 1, ai_service_name: 'M', warnings: [{ kind: 'mcp_config', id: 4 }] };
  const turnConfig = { ai_service: { id: 1, name: 'M' }, silo: null, skills: [], mcp_configs: [], warnings: [{ kind: 'mcp_config', id: 9 }] };
  const seen = [];
  const forwarded = [];
  const { mod } = loadTransport({
    streamAppChatMessage: async (_app, _req, o) => {
      o.onEvent({ type: 'metadata', data: { conversation_id: 5, turn_config: turnConfig } });
      o.onEvent({ type: 'token', data: { content: 'x' } });
      o.onEvent({ type: 'done', data: { response: 'x', turn } });
    },
    getAppChatConversation: async () => ({ messages: [{ role: 'assistant', content: 'a', turn }] }),
  });
  const t = mod.createAppChatTransport(4, () => selectionA, { onTurnEvent: (e) => seen.push(e) });
  await t.streamMessage('hi', { onEvent: (e) => forwarded.push(e.type) });
  assert.deepEqual(forwarded, ['metadata', 'token', 'done']);
  assert.deepEqual(seen.map((e) => e.kind), ['metadata', 'done']);
  assert.equal(seen[0].conversationId, 5);
  assert.equal(seen[0].warnings[0].id, 9);
  assert.equal(seen[1].turn, turn);
  assert.equal(seen[1].warnings[0].id, 4);
  const history = await t.loadHistory(5);
  assert.equal(history.messages[0].turn, turn);
});

// ---------------------------------------------------------------- api.ts contract

function loadApi(fetchImpl) {
  const mod = compile(
    'src/services/api.ts',
    {
      '../core/ConfigService': { configService: { getApiBaseUrl: () => 'http://api' } },
      './auth': { authService: { getOIDCToken: () => null } },
      './cookies': { getCsrfToken: () => 'csrf' },
    },
    { fetch: fetchImpl, FormData, TextDecoder, console, URLSearchParams, encodeURIComponent },
  );
  return mod;
}

function sseResponse(events) {
  const encoder = new TextEncoder();
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
  return {
    ok: true,
    status: 200,
    body: { getReader: () => {
      let sent = false;
      return {
        read: async () => (sent ? { done: true } : ((sent = true), { done: false, value: encoder.encode(body) })),
        releaseLock() {},
      };
    } },
  };
}

test('streamAppChatMessage posts the multipart turn to /chat/stream and parses SSE events', async () => {
  let request;
  const mod = loadApi(async (url, init) => { request = { url, init }; return sseResponse([{ type: 'metadata', data: { conversation_id: 3 } }]); });
  const events = [];
  const file = new Blob(['x']);
  await mod.apiService.streamAppChatMessage(
    8,
    { message: 'hello', selection: selectionB, conversationId: 3, files: [file], fileReferences: ['f1'], searchParams: { k: 1 } },
    { onEvent: (e) => events.push(e) },
  );
  assert.equal(request.url, 'http://api/internal/apps/8/chat/stream');
  assert.equal(request.init.method, 'POST');
  assert.equal(request.init.credentials, 'include');
  const form = request.init.body;
  assert.equal(form.get('message'), 'hello');
  assert.deepEqual(JSON.parse(form.get('selection')), selectionB);
  assert.equal(form.get('conversation_id'), '3');
  assert.deepEqual(JSON.parse(form.get('file_references')), ['f1']);
  assert.deepEqual(JSON.parse(form.get('search_params')), { k: 1 });
  assert.equal(form.getAll('files').length, 1);
  assert.equal(events[0].data.conversation_id, 3);
});

test('a retired model is a real ApiError carrying status 409 and error_code before the stream starts', async () => {
  const mod = loadApi(async () => ({
    ok: false,
    status: 409,
    statusText: 'Conflict',
    json: async () => ({ detail: 'Service retired', error_code: 'SERVICE_RETIRED' }),
  }));
  await assert.rejects(
    () => mod.apiService.streamAppChatMessage(8, { message: 'x', selection: selectionA }, { onEvent() {} }),
    (error) => error.status === 409 && error.errorCode === 'SERVICE_RETIRED' && error.message === 'Service retired',
  );
});

test('chat endpoints use the App-scoped chat routes', async () => {
  const urls = [];
  const mod = loadApi(async (url, init) => { urls.push(`${init.method ?? 'GET'} ${url}`); return { ok: true, status: 200, json: async () => ({}) }; });
  const a = mod.apiService;
  await a.getAppChatOptions(2);
  await a.getAppChatDefaults(2);
  await a.listAppChatConversations(2);
  await a.createAppChatConversation(2, { selection: selectionA });
  await a.getAppChatConversation(2, 5);
  await a.renameAppChatConversation(2, 5, 'T');
  await a.resetAppChatConversation(2, 5);
  await a.listAppChatFiles(2, 5);
  await a.removeAppChatFile(2, 5, 'f 1');
  await a.getAppChatFileDownload(2, 5, 'f1');
  assert.deepEqual(urls, [
    'GET http://api/internal/apps/2/chat/options',
    'GET http://api/internal/apps/2/chat/defaults',
    'GET http://api/internal/apps/2/chat/conversations?limit=50&offset=0',
    'POST http://api/internal/apps/2/chat/conversations',
    'GET http://api/internal/apps/2/chat/conversations/5',
    'PATCH http://api/internal/apps/2/chat/conversations/5',
    'POST http://api/internal/apps/2/chat/conversations/5/reset',
    'GET http://api/internal/apps/2/chat/conversations/5/files',
    'DELETE http://api/internal/apps/2/chat/conversations/5/files/f%201',
    'GET http://api/internal/apps/2/chat/conversations/5/files/f1/download',
  ]);
});

test('transport errors carry a code that maps to translated text in both locales', async () => {
  const { mod } = loadTransport({});
  const t = mod.createAppChatTransport(4, () => selectionA);
  await assert.rejects(
    () => t.getFileDownloadUrl(null, 'f'),
    (error) => error.name === 'ChatTransportError' && error.code === 'noConversation',
  );
  for (const language of ['en', 'es', 'eu']) {
    const keys = require(`../src/i18n/locales/${language}/common.json`).appChat.transportErrors;
    assert.equal(typeof keys.noSelection, 'string');
    assert.equal(typeof keys.noConversation, 'string');
    // Every code the transport can raise has a translated text.
    for (const code of ['noSelection', 'noConversation', 'forbidden', 'notFound', 'serviceRetired', 'conversationBusy', 'stepLimitReached', 'tooManyFiles']) {
      assert.equal(typeof keys[code], 'string', `${language}.${code}`);
    }
  }
  const en = require('../src/i18n/locales/en/common.json').appChat.transportErrors.stepLimitReached;
  const es = require('../src/i18n/locales/es/common.json').appChat.transportErrors.stepLimitReached;
  assert.match(en, /continue/);
  assert.match(es, /continúa/);
  assert.doesNotMatch(es, /fichero/);
  assert.match(require('../src/i18n/locales/en/common.json').appChat.transportErrors.tooManyFiles, /fewer files/);
  assert.match(require('../src/i18n/locales/es/common.json').appChat.transportErrors.tooManyFiles, /menos archivos/);
  const source = fs.readFileSync(path.join(__dirname, '../src/components/playground/chatTransport.ts'), 'utf8');
  assert.doesNotMatch(source, /new Error\(/, 'the transport throws coded errors, never display text');
});

test('a throwing onTurnEvent handler does not abort the stream', async () => {
  const forwarded = [];
  const { mod } = loadTransport({
    streamAppChatMessage: async (_app, _req, o) => {
      o.onEvent({ type: 'metadata', data: { conversation_id: 5 } });
      o.onEvent({ type: 'token', data: { content: 'x' } });
      o.onEvent({ type: 'done', data: { response: 'x', turn: null } });
    },
  });
  const t = mod.createAppChatTransport(4, () => selectionA, { onTurnEvent: () => { throw new Error('observer bug'); } });
  const original = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args);
  try {
    await t.streamMessage('hi', { onEvent: (e) => forwarded.push(e.type) });
  } finally {
    console.error = original;
  }
  assert.deepEqual(forwarded, ['metadata', 'token', 'done']);
  assert.equal(logged.length, 2);
});

// ---------------------------------------------------------------- turn errors (step 15)

function apiError(status, errorCode) {
  const error = new Error('boom');
  error.name = 'ApiError';
  error.status = status;
  error.errorCode = errorCode;
  return error;
}

test('mapTurnError explains 403, 404 and a retired model; everything else passes through', () => {
  const { mod } = loadTransport();
  assert.equal(mod.mapTurnError(apiError(409, 'SERVICE_RETIRED')).code, 'serviceRetired');
  assert.equal(mod.mapTurnError(apiError(409, 'CONVERSATION_BUSY')).code, 'conversationBusy');
  assert.notEqual(mod.mapTurnError(apiError(409, 'CONVERSATION_BUSY')).code, 'serviceRetired');
  const otherConflict = apiError(409, 'SOMETHING_ELSE');
  assert.equal(mod.mapTurnError(otherConflict), otherConflict);
  assert.equal(mod.mapTurnError(apiError(422, 'STEP_LIMIT_REACHED')).code, 'stepLimitReached');
  assert.equal(mod.mapTurnError(apiError(422, 'TOO_MANY_FILES')).code, 'tooManyFiles');
  // A plain 422 (invalid selection, too many files...) has no code the UI explains: it passes through.
  const plain422 = apiError(422);
  assert.equal(mod.mapTurnError(plain422), plain422);
  assert.equal(mod.mapTurnError(apiError(403)).code, 'forbidden');
  assert.equal(mod.mapTurnError(apiError(404)).code, 'notFound');
  const other = apiError(409, 'OTHER');
  assert.equal(mod.mapTurnError(other), other);
  const plain = new Error('x');
  assert.equal(mod.mapTurnError(plain), plain);
});

test('app chat transport reports a rejected turn through onTransportError and throws the coded error', async () => {
  const { mod } = loadTransport({
    streamAppChatMessage: async () => { throw apiError(409, 'SERVICE_RETIRED'); },
  });
  const seen = [];
  const t = mod.createAppChatTransport(3, () => selectionA, { onTransportError: (code) => seen.push(code) });
  await assert.rejects(
    t.streamMessage('hi', { onEvent() {} }),
    (error) => error.name === 'ChatTransportError' && error.code === 'serviceRetired',
  );
  assert.deepEqual(seen, ['serviceRetired']);
});

test('turn observers are skipped when the context token changed while the stream was running (M2)', async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const { mod } = loadTransport({
    streamAppChatMessage: async (_app, _req, opts) => {
      opts.onEvent({ type: 'metadata', data: { conversation_id: 1, turn_config: { warnings: [{ kind: 'skill', id: 1 }] } } });
      await gate;
      opts.onEvent({ type: 'metadata', data: { conversation_id: 1, turn_config: { warnings: [{ kind: 'skill', id: 2 }] } } });
      throw apiError(403);
    },
  });
  let token = 'view-1';
  const events = [];
  const errors = [];
  const t = mod.createAppChatTransport(3, () => selectionA, {
    onTurnEvent: (e) => events.push(e.warnings[0].id),
    onTransportError: (c) => errors.push(c),
    getContextToken: () => token,
  });
  const pending = t.streamMessage('hi', { onEvent() {} });
  token = 'view-2';
  release();
  await assert.rejects(pending);
  assert.deepEqual(JSON.parse(JSON.stringify(events)), [1].slice(0, 1));
  assert.equal(errors.length, 0);
});

test('SSE error events with a known code become the same coded errors as their HTTP twins', async () => {
  for (const [sseCode, expected] of [
    ['step_limit_reached', 'stepLimitReached'],
    ['conversation_busy', 'conversationBusy'],
    ['service_retired', 'serviceRetired'],
  ]) {
    const { mod } = loadTransport({
      streamAppChatMessage: async (_app, _req, opts) => {
        opts.onEvent({ type: 'metadata', data: { conversation_id: 9 } });
        opts.onEvent({ type: 'error', data: { message: 'fixed text', code: sseCode } });
      },
    });
    const seen = [];
    const forwarded = [];
    const t = mod.createAppChatTransport(3, () => selectionA, { onTransportError: (code) => seen.push(code) });
    await assert.rejects(
      t.streamMessage('hi', { onEvent: (e) => forwarded.push(e.type) }),
      (error) => error.name === 'ChatTransportError' && error.code === expected,
      sseCode,
    );
    assert.deepEqual(seen, [expected]);
    assert.deepEqual(forwarded, ['metadata', 'error'], 'the stream consumer still sees every event');
  }
});

test('an SSE error without a known code is left to the generic handling (no coded error)', async () => {
  const { mod } = loadTransport({
    streamAppChatMessage: async (_app, _req, opts) => {
      opts.onEvent({ type: 'error', data: { message: 'something else', code: 'unknown_thing' } });
      opts.onEvent({ type: 'error', data: { message: 'no code at all' } });
    },
  });
  const t = mod.createAppChatTransport(3, () => selectionA);
  await t.streamMessage('hi', { onEvent() {} }); // resolves: the stream consumer decides what the event means
});
