import type { ReactElement } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import { expect } from 'vitest';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes, useLocation, useNavigationType } from 'react-router-dom';

import i18n from '../../src/i18n';
import { ConfirmProvider } from '../../src/contexts/ConfirmContext';
import AppChatPage from '../../src/pages/AppChatPage';

export interface RecordedNavigation {
  readonly pathname: string;
  readonly type: string;
}

function LocationProbe({ log }: Readonly<{ log: RecordedNavigation[] }>) {
  const location = useLocation();
  const type = useNavigationType();
  const last = log[log.length - 1];
  if (!last || last.pathname !== location.pathname) log.push({ pathname: location.pathname, type });
  return <output data-testid="location">{location.pathname}</output>;
}

export interface RenderOptions {
  readonly path?: string;
}

/** Renders `ui` with the real i18n instance, a MemoryRouter and the providers the chat needs. */
export function renderWithProviders(ui: ReactElement, { path = '/' }: RenderOptions = {}) {
  const navigations: RecordedNavigation[] = [];
  const user = userEvent.setup();
  const view = render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[path]}>
        <ConfirmProvider>
          <LocationProbe log={navigations} />
          {ui}
        </ConfirmProvider>
      </MemoryRouter>
    </I18nextProvider>,
  );
  return { ...view, user, navigations };
}

/** The App Chat page under the same two sibling routes `ExtensibleBaseApp` declares. */
export function renderAppChat(path = '/apps/7/chat') {
  return renderWithProviders(
    <Routes>
      <Route path="/apps/:appId/chat" element={<AppChatPage />} />
      <Route path="/apps/:appId/chat/:conversationId" element={<AppChatPage />} />
    </Routes>,
    { path },
  );
}

/** Translate with the instance the components use (for text that is not the point of the test). */
export function tr(key: string, options?: Record<string, unknown>): string {
  return i18n.t(key, options) as string;
}

export interface Deferred<T> {
  readonly promise: Promise<T>;
  resolve(value: T): void;
  reject(reason: unknown): void;
}

export function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// ---------------------------------------------------------------------------
// Chat page locators
// ---------------------------------------------------------------------------

export function composer(): HTMLTextAreaElement {
  return screen.getByRole('textbox', {
    name: tr('agentPlayground.chat.messagePlaceholder', { agent: tr('appChat.page.assistantName') }),
  }) as HTMLTextAreaElement;
}

export function sendButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: tr('agentPlayground.chat.sendMessage') }) as HTMLButtonElement;
}

/** The chip of a selector ("Model", "Source", "Skills", "MCP"): its accessible name is "<label> <value>". */
export function chip(labelKey: 'model' | 'source' | 'skills' | 'mcps'): HTMLButtonElement {
  const label = tr(`appChat.selection.${labelKey}`);
  return screen.getByRole('button', { name: new RegExp(`^${label}\\b`) }) as HTMLButtonElement;
}

export async function pickOption(user: UserEvent, labelKey: 'model' | 'source', optionName: string | RegExp) {
  await user.click(chip(labelKey));
  await user.click(await screen.findByRole('option', { name: optionName }));
}

/** Waits until the chat has loaded its options and shows the composer. */
export async function waitForChat(): Promise<void> {
  await screen.findByRole('textbox', {
    name: tr('agentPlayground.chat.messagePlaceholder', { agent: tr('appChat.page.assistantName') }),
  });
}

/** Waits until the composer's blocked-reason region is empty (sending is possible once text is typed). */
export async function waitUntilSendable(user: UserEvent, text = 'probe') {
  await user.type(composer(), text);
  await waitFor(() => expect(sendButton()).toBeEnabled());
  await user.clear(composer());
}

export async function openConversationsPanel(user: UserEvent) {
  await user.click(screen.getByRole('button', { name: tr('appChat.page.conversations') }));
  return screen.findByRole('dialog', { name: tr('agentPlayground.conversations') });
}

export async function clickNewConversation(user: UserEvent) {
  const panel = await openConversationsPanel(user);
  await user.click(within(panel).getByRole('button', { name: tr('conversationSidebar.new') }));
}

/** The text of the element the composer's `aria-describedby` points to. */
export function composerDescription(): string {
  const id = composer().getAttribute('aria-describedby');
  if (!id) return '';
  return document.getElementById(id)?.textContent ?? '';
}

/** Name of the dismiss button of the indexing notice (stacked alerts carry their own name after "Dismiss"). */
export const dismissName = tr('alert.dismissNamed', { name: tr('appChat.attachmentIndexing.title') });

/** Pattern matching the translated text of ``key`` anywhere (e.g. a label followed by a required marker). */
export function trPattern(key: string): RegExp {
  return new RegExp(tr(key).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
}
