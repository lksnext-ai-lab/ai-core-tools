import '@testing-library/jest-dom/vitest';
import * as axeMatchers from 'vitest-axe/matchers';
import { cleanup } from '@testing-library/react';
import { afterEach, expect, vi } from 'vitest';

// Every test file talks to the in-memory `apiService` of `./apiMock`, never to the network.
vi.mock('../../src/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/services/api')>();
  const { apiMock } = await import('./apiMock');
  return { ...actual, apiService: apiMock };
});

// jsdom does not implement these; the chat uses them to keep the newest message in view.
Element.prototype.scrollTo = () => {};
Element.prototype.scrollIntoView = () => {};

expect.extend(axeMatchers);

afterEach(() => {
  cleanup();
});

// Real i18n instance, English unless a test switches it.
import i18n from '../../src/i18n';
import { beforeEach } from 'vitest';
import { resetApiMock } from './apiMock';

beforeEach(async () => {
  resetApiMock();
  await i18n.changeLanguage('en');
});

// The app does not opt into React Router v7 behaviour, so these notices are noise here.
const originalWarn = console.warn.bind(console);
console.warn = (...args: unknown[]) => {
  if (typeof args[0] === 'string' && args[0].includes('React Router Future Flag Warning')) return;
  originalWarn(...args);
};
