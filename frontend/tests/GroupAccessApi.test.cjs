const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const apiPath = path.join(__dirname, '../src/services/api.ts');
const source = fs.readFileSync(apiPath, 'utf8')
  // The browser-only Vite expression is not available in node:test's VM.
  .replace(/import\.meta\.env\.VITE_OIDC_ENABLED/g, "'false'");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;

const dependencyStubs = {
  '../core/ConfigService': { configService: { getApiBaseUrl: () => '' } },
  './auth': { authService: {} },
  './cookies': { getCsrfToken: () => null },
  '../constants/appList': { MAX_APP_LIST_PAGE_SIZE: 100 },
};
const apiModule = { exports: {} };
vm.runInNewContext(compiled, {
  exports: apiModule.exports,
  URLSearchParams,
  require: (specifier) => {
    if (!(specifier in dependencyStubs)) {
      throw new Error(`Unexpected API module dependency: ${specifier}`);
    }
    return dependencyStubs[specifier];
  },
});
const { apiService } = apiModule.exports;

test('My Groups API forwards the requested pagination and keeps contribution/effective roles', async () => {
  const expected = {
    items: [
      {
        group_id: 17,
        display_name: 'Engineering',
      },
    ],
    total: 14,
    offset: 10,
    limit: 5,
  };
  const requests = [];
  apiService.request = async (endpoint) => {
    requests.push(endpoint);
    return expected;
  };

  const groupPage = await apiService.getMyGroups(10, 5);
  assert.equal(requests[0], '/internal/my-groups?offset=10&limit=5');
  assert.deepEqual(JSON.parse(JSON.stringify(groupPage)), expected);

  const appsPage = {
    group_id: 17,
    display_name: 'Engineering',
    items: [
      {
        app_id: 23,
        app_name: 'Workspace',
        contribution: 'VIEWER',
        effective_role: 'editor',
      },
    ],
    total: 8,
    offset: 4,
    limit: 2,
  };
  apiService.request = async (endpoint) => {
    requests.push(endpoint);
    return appsPage;
  };

  const appResult = await apiService.getMyGroupApps(17, 4, 2);
  assert.equal(requests[1], '/internal/my-groups/17/apps?offset=4&limit=2');
  assert.deepEqual(JSON.parse(JSON.stringify(appResult)), appsPage);
  assert.equal(appResult.items[0].contribution, 'VIEWER');
  assert.equal(appResult.items[0].effective_role, 'editor');
});

test('group-policy API forwards paginated rule results without changing app roles', async () => {
  const rules = [
    {
      id: 5,
      group_id: 17,
      app_id: 23,
      role: 'editor',
      created_by_user_id: 9,
      is_active: true,
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-02T00:00:00',
      group_display_name: 'Engineering',
      connection_id: 4,
    },
  ];
  let request;
  apiService.request = async (endpoint) => {
    request = endpoint;
    return rules;
  };

  const result = await apiService.getGroupAppRules(23, 100, 25);

  assert.equal(request, '/internal/apps/23/scim-group-rules?offset=100&limit=25');
  assert.deepEqual(JSON.parse(JSON.stringify(result)), rules);
  assert.equal(result[0].role, 'editor');
});

test('group-policy mutations send backend enum values in lowercase', async () => {
  const requests = [];
  apiService.request = async (endpoint, options) => {
    requests.push({ endpoint, options });
    return {};
  };

  await apiService.createGroupAppRule(23, 17, 'viewer');
  await apiService.updateGroupAppRule(23, 5, 'editor');

  assert.equal(requests[0].endpoint, '/internal/apps/23/scim-group-rules');
  assert.equal(requests[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    group_id: 17,
    role: 'viewer',
  });
  assert.equal(requests[1].endpoint, '/internal/apps/23/scim-group-rules/5');
  assert.equal(requests[1].options.method, 'PATCH');
  assert.deepEqual(JSON.parse(requests[1].options.body), { role: 'editor' });
});

