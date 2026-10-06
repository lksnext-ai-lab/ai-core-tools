const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/pages/ScheduledTaskFormPage.tsx'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;

function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

const task = (id = 1) => ({
  id, app_id: 3, name: `Task ${id}`, agent_id: 11, input: {}, timezone: 'UTC',
  cron_expression: '0 8 * * *', conversation_mode: 'new_per_run', max_runs_retained: 10,
  marketplace_visibility: 'unpublished',
});
const configured = { bindings: [{ destination_id: 7, content_mode: 'excerpt' }] };
const flush = () => new Promise((resolve) => setImmediate(resolve));

// Exercise the actual page with a minimal hook harness; no browser or network
// dependency is needed to test delayed loads, errors and route changes.
function mount(overrides = {}) {
  const states = [];
  const effects = [];
  let stateIndex, effectIndex;
  let params = { appId: '3', taskId: '1' };
  const calls = { updates: [], outputs: [], creates: [] };
  const apiService = {
    getAgents: async () => [{ agent_id: 11, name: 'Agent' }],
    getOutputDestinations: async () => [{ id: 7, name: 'Teams', enabled: true }],
    getScheduledTask: async (_, id) => task(id),
    getScheduledTaskOutputs: async () => configured,
    updateScheduledTask: async (...args) => { calls.updates.push(args); return task(args[1]); },
    setScheduledTaskOutputs: async (...args) => { calls.outputs.push(args); },
    createScheduledTask: async (...args) => { calls.creates.push(args); return task(); },
    ...overrides,
  };
  const modules = {
    react: {
      useState(initial) {
        const index = stateIndex++;
        if (!(index in states)) states[index] = initial;
        return [states[index], (next) => { states[index] = typeof next === 'function' ? next(states[index]) : next; }];
      },
      useEffect(callback, deps) {
        const index = effectIndex++;
        const old = effects[index];
        if (!old || deps.some((dep, i) => !Object.is(dep, old.deps[i]))) {
          old?.cleanup?.();
          effects[index] = { deps, callback };
        }
      },
    },
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    'react-router-dom': { useNavigate: () => () => {}, useParams: () => params },
    sonner: { toast: { error() {}, success() {} } },
    'lucide-react': { Trash2: () => null },
    '../services/api': { apiService },
    '../components/ui/ConfirmationModal': () => null,
  };
  const exports = {};
  vm.runInNewContext(compiled, { exports, require: (name) => {
    assert.ok(name in modules, `Unexpected dependency: ${name}`);
    return modules[name];
  } });
  return {
    calls,
    setParams(next) { params = next; },
    render() {
      stateIndex = effectIndex = 0;
      const view = exports.default();
      for (const effect of effects) {
        if (effect.callback) {
          const callback = effect.callback;
          delete effect.callback;
          effect.cleanup = callback();
        }
      }
      return view;
    },
  };
}

function elements(node) {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!node || typeof node !== 'object') return [];
  return [node, ...elements(node.props?.children)];
}
const button = (view, label) => elements(view).find((node) => node.type === 'button' && node.props.children === label);
const save = (view) => button(view, 'Guardar y activar');

test('waits for channel bindings and preserves their content mode when saving', async () => {
  const outputs = deferred();
  const page = mount({ getScheduledTaskOutputs: () => outputs.promise });
  assert.equal(save(page.render()), undefined);
  await flush();
  assert.equal(save(page.render()), undefined);
  assert.equal(page.calls.updates.length, 0);
  outputs.resolve(configured);
  await flush();
  save(page.render()).props.onClick();
  await flush();
  assert.equal(page.calls.updates.length, 1);
  assert.equal(page.calls.outputs[0][2][0].destination_id, 7);
  assert.equal(page.calls.outputs[0][2][0].content_mode, 'excerpt');
});

test('failed channel load blocks saving and a successful retry restores the configured bindings', async () => {
  let loads = 0;
  const page = mount({ getScheduledTaskOutputs: async () => {
    if (++loads === 1) throw new Error('unavailable');
    return configured;
  } });
  page.render();
  await flush();
  const failed = page.render();
  assert.equal(save(failed), undefined);
  assert.equal(page.calls.outputs.length, 0);
  assert.ok(elements(failed).some((node) => node.props.role === 'alert'));
  button(failed, 'Reintentar carga').props.onClick();
  assert.equal(save(page.render()), undefined);
  await flush();
  save(page.render()).props.onClick();
  await flush();
  assert.equal(page.calls.outputs[0][2][0].destination_id, 7);
});

test('failed destination catalogue also blocks editing', async () => {
  const page = mount({ getOutputDestinations: async () => { throw new Error('unavailable'); } });
  page.render();
  await flush();
  assert.equal(save(page.render()), undefined);
  assert.equal(page.calls.updates.length, 0);
});

test('known empty bindings allow saving without treating them as a load failure', async () => {
  const page = mount({ getScheduledTaskOutputs: async () => ({ bindings: [] }) });
  page.render();
  await flush();
  save(page.render()).props.onClick();
  await flush();
  assert.equal(page.calls.outputs[0][2].length, 0);
});

test('a late response for a previous route cannot replace the current task channels', async () => {
  const old = deferred();
  const page = mount({ getScheduledTaskOutputs: (_, id) => id === 1 ? old.promise : Promise.resolve(configured) });
  page.render();
  page.setParams({ appId: '3', taskId: '2' });
  assert.equal(save(page.render()), undefined);
  await flush();
  old.resolve({ bindings: [] });
  await flush();
  save(page.render()).props.onClick();
  await flush();
  assert.equal(page.calls.updates[0][1], 2);
  assert.equal(page.calls.outputs[0][2][0].destination_id, 7);
});
