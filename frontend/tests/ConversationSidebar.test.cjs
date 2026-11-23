const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const locales = {
  en: require('../src/i18n/locales/en/common.json'),
  es: require('../src/i18n/locales/es/common.json'),
  eu: require('../src/i18n/locales/eu/common.json'),
};
const source = fs.readFileSync(path.join(__dirname, '../src/components/playground/ConversationSidebar.tsx'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;

const flush = () => new Promise((resolve) => setImmediate(resolve));

function lookup(language, key) {
  if (!(language in locales)) language = 'en'; // unknown tags (cimode) show the default texts
  return key.split('.').reduce((value, part) => value?.[part], locales[language]);
}

/** Minimal i18next `t`: nested keys, `_one` / `_other` plurals and `{{x}}` interpolation. */
function makeT(language) {
  return (key, options = {}) => {
    let value = options.count === undefined
      ? lookup(language, key)
      : lookup(language, `${key}_${options.count === 1 ? 'one' : 'other'}`);
    assert.equal(typeof value, 'string', `Missing ${language} translation: ${key}`);
    for (const [name, replacement] of Object.entries(options)) {
      value = value.replaceAll(`{{${name}}}`, String(replacement));
    }
    return value;
  };
}

function mount(language, props, api = {}, intl = Intl) {
  const states = [];
  const effects = [];
  let hookIndex = 0;
  const confirmCalls = [];
  const modules = {
    react: {
      useState(initial) {
        const index = hookIndex++;
        if (!(index in states)) states[index] = initial;
        return [states[index], (next) => { states[index] = typeof next === 'function' ? next(states[index]) : next; }];
      },
      useRef(initial) {
        const index = hookIndex++;
        if (!(index in states)) states[index] = { current: initial };
        return states[index];
      },
      useEffect(callback, deps) {
        const index = hookIndex++;
        const previous = effects[index];
        if (!previous || deps.some((dep, i) => !Object.is(dep, previous.deps[i]))) {
          effects[index] = { deps, callback, pending: true };
        }
      },
    },
    'react/jsx-runtime': { jsx: (type, p) => ({ type, props: p }), jsxs: (type, p) => ({ type, props: p }) },
    'react-i18next': { useTranslation: () => ({ t: makeT(language), i18n: { language } }) },
    'lucide-react': { Pencil: 'Pencil', Trash2: 'Trash2' },
    '../../services/api': { apiService: api },
    '../../contexts/ConfirmContext': { useConfirm: () => async (options) => { confirmCalls.push(options); return true; } },
    '../ui/Alert': { __esModule: true, default: 'Alert' },
    '../ui/LoadingState': { LoadingState: 'LoadingState' },
    '../ui/SidePanel': { SidePanel: 'SidePanel' },
  };
  const exports = {};
  vm.runInNewContext(compiled, {
    exports,
    require: (name) => {
      assert.ok(name in modules, `Unexpected dependency: ${name}`);
      return modules[name];
    },
    Intl: intl,
    Date,
    Error,
    console,
  });
  return {
    confirmCalls,
    render() {
      hookIndex = 0;
      const view = exports.default({
        open: true,
        onClose() {},
        onNewConversation() {},
        onConversationSelect() {},
        currentConversationId: 5,
        ...props,
      });
      for (const effect of effects) {
        if (effect?.pending) {
          effect.pending = false;
          effect.callback();
        }
      }
      return view;
    },
  };
}

function elements(node) {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!node || typeof node !== 'object') return [];
  const p = node.props ?? {};
  return [node, ...elements(p.children), ...elements(p.message), ...elements(p.headerActions), ...elements(p.footer)];
}

function text(node) {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(text).join(' ');
  if (!node || typeof node !== 'object') return '';
  const p = node.props ?? {};
  return [p.children, p.message, p.headerActions, p.footer].map(text).join(' ');
}

const old = new Date(Date.now() - 30 * 86400000).toISOString();
const chatConversation = {
  conversation_id: 5, title: null, created_at: old, updated_at: old, last_message: 'hi', message_count: 2,
};

async function renderLoaded(language, extraProps = {}, api = {}) {
  const sidebar = mount(language, {
    loadConversations: async () => ({ conversations: [chatConversation, { ...chatConversation, conversation_id: 6, title: 'Named', message_count: 1 }] }),
    ...extraProps,
  }, api);
  sidebar.render();
  await flush();
  return { sidebar, view: sidebar.render() };
}

for (const language of ['en', 'es', 'eu']) {
  test(`sidebar renders every label in ${language} and accepts Chat conversations (no agent_id / session_id)`, async () => {
    const { view } = await renderLoaded(language);
    const t = makeT(language);
    const panel = elements(view).find((n) => n.type === 'SidePanel');
    assert.equal(panel.props.title, t('agentPlayground.conversations'));
    assert.equal(panel.props.closeLabel, t('conversationSidebar.closeLabel'));
    const content = text(view);
    assert.ok(content.includes(t('conversationSidebar.new')));
    assert.ok(content.includes(t('conversationSidebar.refresh')));
    assert.ok(content.includes(t('conversationSidebar.untitled')), 'untitled conversation gets the translated placeholder');
    assert.ok(content.includes('Named'));
    assert.ok(content.includes(t('conversationSidebar.messageCount', { count: 2 })));
    assert.ok(content.includes(t('conversationSidebar.messageCount', { count: 1 })));
    const rename = elements(view).find((n) => n.props?.['data-action'] === 'rename');
    const del = elements(view).find((n) => n.props?.['data-action'] === 'delete');
    // Every row's actions name their conversation, so a screen reader can tell them apart.
    assert.equal(rename.props['aria-label'], t('conversationSidebar.renameNamed', { title: t('conversationSidebar.untitled') }));
    assert.equal(del.props['aria-label'], t('conversationSidebar.deleteNamed', { title: t('conversationSidebar.untitled') }));
    const labels = elements(view).filter((n) => n.props?.['data-action']).map((n) => n.props['aria-label']);
    assert.equal(new Set(labels).size, labels.length, 'accessible names are unique');
    // Old dates use the active locale, not a hardcoded es-ES.
    const expectedDate = new Intl.DateTimeFormat(language, { day: 'numeric', month: 'short' }).format(new Date(old));
    assert.ok(content.includes(expectedDate), `expected ${expectedDate} in ${content}`);
    assert.doesNotMatch(content, language === 'en' ? /mensajes|Hace|Nueva/ : /messages|ago/);
  });
}

test('relative dates are translated', async () => {
  for (const language of ['en', 'es', 'eu']) {
    const recent = new Date(Date.now() - 5 * 60000).toISOString();
    const sidebar = mount(language, {
      loadConversations: async () => ({ conversations: [{ ...chatConversation, updated_at: recent }] }),
    });
    sidebar.render();
    await flush();
    assert.ok(text(sidebar.render()).includes(makeT(language)('conversationSidebar.minutesAgo', { value: 5 })));
  }
});

test('load errors and the empty state are translated and use the injected loader', async () => {
  for (const language of ['en', 'es', 'eu']) {
    const t = makeT(language);
    const failing = mount(language, { loadConversations: async () => { throw new Error('boom'); } });
    failing.render();
    await flush();
    const failedText = text(failing.render());
    assert.ok(failedText.includes(t('conversationSidebar.loadError')));
    assert.ok(failedText.includes(t('serviceUsage.retry')));

    const empty = mount(language, { loadConversations: async () => ({ conversations: [] }) });
    empty.render();
    await flush();
    const emptyText = text(empty.render());
    assert.ok(emptyText.includes(t('conversationSidebar.empty')));
    assert.ok(emptyText.includes(t('conversationSidebar.emptyHint')));
  }
});

test('default behaviour is by agentId through the playground api calls; injected callbacks replace them', async () => {
  const calls = [];
  const api = {
    listConversations: async (agentId) => { calls.push(['listConversations', agentId]); return { conversations: [chatConversation] }; },
    updateConversation: async (...a) => { calls.push(['updateConversation', ...a]); },
    deleteConversation: async (...a) => { calls.push(['deleteConversation', ...a]); },
  };
  const defaults = mount('en', { agentId: 9 }, api);
  defaults.render();
  await flush();
  const view = defaults.render();
  assert.deepEqual(calls, [['listConversations', 9]]);
  const del = elements(view).find((n) => n.props?.['data-action'] === 'delete');
  await del.props.onClick({ stopPropagation() {} });
  assert.deepEqual(calls[1], ['deleteConversation', 5]);
  assert.equal(defaults.confirmCalls[0].confirmLabel, 'Delete');

  const injectedCalls = [];
  const { sidebar, view: injectedView } = await renderLoaded('es', {
    renameConversation: async (...a) => { injectedCalls.push(['rename', ...a]); },
    deleteConversation: async (...a) => { injectedCalls.push(['delete', ...a]); },
  }, api);
  const injectedDelete = elements(injectedView).find((n) => n.props?.['data-action'] === 'delete');
  await injectedDelete.props.onClick({ stopPropagation() {} });
  assert.deepEqual(injectedCalls, [['delete', 5]]);
  assert.equal(sidebar.confirmCalls[0].confirmLabel, 'Eliminar');
  assert.equal(sidebar.confirmCalls[0].message, locales.es.conversationSidebar.confirmDeleteMessage);
  assert.equal(calls.length, 2, 'the playground api is untouched when callbacks are injected');
});

test('both locales define the same conversationSidebar keys and the component uses no hardcoded Spanish', () => {
  assert.deepEqual(Object.keys(locales.en.conversationSidebar).sort(), Object.keys(locales.es.conversationSidebar).sort());
  const used = [...source.matchAll(/t\('(conversationSidebar\.[\w]+)'/g)].map((m) => m[1].split('.')[1]);
  for (const key of used) {
    const present = key in locales.en.conversationSidebar || `${key}_one` in locales.en.conversationSidebar;
    assert.ok(present, `missing key ${key}`);
  }
  assert.doesNotMatch(source, /es-ES/);
  assert.doesNotMatch(source, /Hace |Ahora|Renombrar|Eliminar|Actualizar|Reintentar|Cargando/);
});

test('an invalid language tag (cimode) falls back instead of throwing, and formatters are built once per language', async () => {
  let dateFormats = 0;
  const countingIntl = new Proxy(Intl, {
    get(target, prop) {
      if (prop === 'DateTimeFormat') {
        return new Proxy(target.DateTimeFormat, { construct(Ctor, args) { dateFormats += 1; return new Ctor(...args); } });
      }
      return target[prop];
    },
  });
  const many = Array.from({ length: 5 }, (_, i) => ({ ...chatConversation, conversation_id: 100 + i }));
  const sidebar = mount('cimode', { loadConversations: async () => ({ conversations: many }) }, {}, countingIntl);
  sidebar.render();
  await flush();
  assert.doesNotThrow(() => sidebar.render());
  // 1 probe (throws) + 1 formatter built for the language; the 5 rows reuse it.
  assert.ok(dateFormats <= 2, `expected the formatter to be shared, built ${dateFormats} times`);
});

test('time elements expose dateTime and an unabbreviated spoken form; the abbreviation is hidden from AT', async () => {
  for (const [language, pattern] of [['en', /5 minutes ago/], ['es', /hace 5 minutos/]]) {
    const recent = new Date(Date.now() - 5 * 60000).toISOString();
    const sidebar = mount(language, { loadConversations: async () => ({ conversations: [{ ...chatConversation, updated_at: recent }] }) });
    sidebar.render();
    await flush();
    const time = elements(sidebar.render()).find((n) => n.type === 'time');
    assert.equal(time.props.dateTime, recent);
    const [visible, spoken] = time.props.children;
    assert.equal(visible.props['aria-hidden'], 'true');
    assert.ok(visible.props.children.includes('5'));
    assert.equal(spoken.props.className, 'sr-only');
    assert.match(spoken.props.children, pattern);
  }
});

test('the rename input has an accessible name', async () => {
  const { sidebar, view } = await renderLoaded('es');
  const rename = elements(view).find((n) => n.props?.['data-action'] === 'rename');
  rename.props.onClick({ stopPropagation() {} });
  const input = elements(sidebar.render()).find((n) => n.type === 'input');
  assert.equal(input.props['aria-label'], locales.es.marketplaceHome.renameConversation);
});
