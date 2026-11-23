import { waitFor } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { describe, expect, it } from 'vitest';

import { chip, composer, openConversationsPanel, renderAppChat, waitForChat } from './testUtils';
import { makeDetail, setupChatApi } from './apiMock';

/**
 * Structural WCAG checks with axe-core on the rendered Chat page. jsdom has no layout or stylesheets
 * (`css: false`), so colour contrast cannot be computed here and its rule is switched off; contrast
 * is checked from the design tokens instead (see the accessibility notes of the Chat).
 */
const RULES = { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } };

async function ready(path = '/apps/7/chat/5') {
  const view = renderAppChat(path);
  await waitForChat();
  await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Alpha|Alfa/));
  await waitFor(() => expect(composer()).toBeEnabled());
  return view;
}

describe.each(['light', 'dark'])('Chat page structure (%s theme)', (theme) => {
  const setTheme = () => document.documentElement.classList.toggle('dark', theme === 'dark');

  it('has no axe violations with the conversation panel closed', async () => {
    setTheme();
    setupChatApi({ conversations: { 5: makeDetail(5, { title: 'Quarterly plan', message_count: 2 }) } });
    const { container } = await ready();
    expect(await axe(container, RULES)).toHaveNoViolations();
  });

  it('has no axe violations with the conversation panel open', async () => {
    setTheme();
    setupChatApi({ conversations: { 5: makeDetail(5, { title: 'Quarterly plan', message_count: 2 }) } });
    const { user } = await ready();
    await openConversationsPanel(user);
    expect(await axe(document.body, RULES)).toHaveNoViolations();
  });
});
