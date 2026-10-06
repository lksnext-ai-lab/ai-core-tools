const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/components/output/outputChannelForm.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const helpers = {};
vm.runInNewContext(compiled, { exports: helpers, URL, atob });
const { initialChannelForm, validateChannelIdentity, validateChannelConfiguration, buildChannelPayload } = helpers;
const plain = (value) => JSON.parse(JSON.stringify(value));
const destination = {
  id: 7, name: 'Alerts', provider_key: 'webhook', has_credentials: true,
  content_mode: 'excerpt',
  public_config: { schema_version: '1', auth_mode: 'hmac_sha256', include_attachments: false, receiver_deduplicates: true },
};
const signingSecret = Buffer.alloc(32, 1).toString('base64');

test('editing attachment options preserves stored endpoint, credentials and other configuration', () => {
  const form = initialChannelForm(destination);
  form.includeAttachments = true;
  assert.equal(form.url, '');
  assert.equal(form.credential, '');
  assert.equal(validateChannelConfiguration(form, destination), null);
  const payload = plain(buildChannelPayload(form, destination));
  assert.equal('webhook_url' in payload, false);
  assert.equal('credentials' in payload, false);
  assert.equal('clear_credentials' in payload, false);
  assert.equal(payload.content_mode, 'excerpt');
  assert.deepEqual(payload.public_config, { ...destination.public_config, include_attachments: true });
});

test('switching to unauthenticated webhook explicitly clears stored credentials', () => {
  const form = { ...initialChannelForm(destination), authMode: 'none', credential: 'ignored' };
  assert.equal(validateChannelConfiguration(form, destination), null);
  const payload = buildChannelPayload(form, destination);
  assert.equal(payload.clear_credentials, true);
  assert.equal(payload.public_config.auth_mode, 'none');
  assert.equal('credentials' in payload, false);
});

test('changing authentication requires a new credential and sends only the selected credential type', () => {
  const form = { ...initialChannelForm(destination), authMode: 'bearer' };
  assert.ok(validateChannelConfiguration(form, destination));
  form.credential = 'new-token';
  assert.equal(validateChannelConfiguration(form, destination), null);
  assert.deepEqual(plain(buildChannelPayload(form, destination).credentials), { bearer_token: 'new-token' });
  const anonymous = { ...destination, has_credentials: false, public_config: { auth_mode: 'none' } };
  const secureForm = { ...initialChannelForm(anonymous), authMode: 'hmac_sha256' };
  assert.ok(validateChannelConfiguration(secureForm, anonymous));
  secureForm.credential = signingSecret;
  assert.equal(validateChannelConfiguration(secureForm, anonymous), null);
});

test('creation requires an HTTPS endpoint and credentials of the correct format', () => {
  const form = { ...initialChannelForm(null), provider: 'webhook' };
  assert.ok(validateChannelConfiguration(form, null));
  form.url = 'https://example.com/events';
  assert.ok(validateChannelConfiguration(form, null));
  form.credential = Buffer.alloc(31).toString('base64');
  assert.ok(validateChannelConfiguration(form, null));
  form.credential = signingSecret;
  assert.equal(validateChannelConfiguration(form, null), null);
  for (const url of ['http://example.com', 'https://example.com:8443', 'https://user:pass@example.com', 'https://example.com/#fragment']) {
    assert.ok(validateChannelConfiguration({ ...form, url }, null));
  }
  const payload = plain(buildChannelPayload(form, null));
  assert.equal(payload.webhook_url, form.url);
  assert.equal(payload.provider_key, 'webhook');
  assert.deepEqual(payload.credentials, { signing_secret: signingSecret });
});

test('Teams editing preserves the secret unless a replacement URL is supplied', () => {
  const teams = { ...destination, provider_key: 'teams_workflow', public_config: {} };
  const form = initialChannelForm(teams);
  assert.equal(validateChannelConfiguration(form, teams), null);
  assert.deepEqual(plain(buildChannelPayload(form, teams)), { name: 'Alerts', content_mode: 'excerpt' });
  form.url = 'https://example.com/workflow?secret=new';
  assert.equal(validateChannelConfiguration(form, teams), null);
  assert.equal(buildChannelPayload(form, teams).webhook_url, form.url);
  assert.equal('public_config' in buildChannelPayload(form, teams), false);
});

test('identity validation permits unchanged names while blocking duplicates and empty names', () => {
  const form = initialChannelForm(destination);
  assert.equal(validateChannelIdentity(form, [destination], destination), null);
  assert.ok(validateChannelIdentity(form, [destination], null));
  assert.ok(validateChannelIdentity({ ...form, name: '   ' }, [], null));
  assert.ok(validateChannelIdentity({ ...form, name: 'x'.repeat(256) }, [], null));
});

test('new channels default to result and edits persist the content mode for both providers', () => {
  assert.equal(initialChannelForm(null).contentMode, 'result');
  for (const provider_key of ['teams_workflow', 'webhook']) {
    const channel = { ...destination, provider_key };
    const form = { ...initialChannelForm(channel), contentMode: 'link_only' };
    assert.equal(validateChannelConfiguration(form, channel), null);
    assert.equal(buildChannelPayload(form, channel).content_mode, 'link_only');
  }
});
