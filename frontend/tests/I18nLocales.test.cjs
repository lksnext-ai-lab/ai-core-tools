const test = require('node:test');
const assert = require('node:assert/strict');

const locales = {
  en: require('../src/i18n/locales/en/common.json'),
  es: require('../src/i18n/locales/es/common.json'),
  eu: require('../src/i18n/locales/eu/common.json'),
};

function flatten(value, prefix = '', out = {}) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) flatten(child, prefix ? `${prefix}.${key}` : key, out);
  } else {
    out[prefix] = value;
  }
  return out;
}

const tokens = (text) => String(text).match(/\{\{[^}]+\}\}|<\/?[a-zA-Z0-9]+\/?>/g)?.sort().join('|') ?? '';

const reference = flatten(locales.en);

for (const language of ['es', 'eu']) {
  test(`${language} has exactly the same keys as en`, () => {
    const keys = flatten(locales[language]);
    assert.deepEqual(Object.keys(keys).sort(), Object.keys(reference).sort());
  });

  test(`${language} keeps the interpolation placeholders and tags of en`, () => {
    const keys = flatten(locales[language]);
    const mismatched = Object.keys(reference).filter((key) => {
      const source = reference[key];
      if (Array.isArray(source)) return !Array.isArray(keys[key]) || keys[key].length !== source.length;
      return tokens(source) !== tokens(keys[key]);
    });
    assert.deepEqual(mismatched, []);
  });
}
