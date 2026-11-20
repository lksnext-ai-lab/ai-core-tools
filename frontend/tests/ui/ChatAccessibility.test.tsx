import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import i18n from '../../src/i18n';
import { SidePanel } from '../../src/components/ui/SidePanel';
import { apiMock, makeDetail, setupChatApi } from './apiMock';
import {
  chip,
  composer,
  openConversationsPanel,
  renderAppChat,
  renderWithProviders,
  sendButton,
  tr,
  waitForChat,
} from './testUtils';

const agent = () => tr('appChat.page.assistantName');
const stopButton = () => screen.getByRole('button', { name: tr('agentPlayground.chat.stopGenerating') });

async function ready(path?: string) {
  const view = renderAppChat(path);
  await waitForChat();
  await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Alpha|Alfa/));
  await waitFor(() => expect(composer()).toBeEnabled());
  return view;
}

async function startTurn(user: ReturnType<typeof renderAppChat>['user']) {
  await user.type(composer(), 'hello');
  await user.click(sendButton());
}

describe('Chat: stopping a turn from the keyboard (H1)', () => {
  it('moves focus to Stop when the turn starts, and Esc aborts it', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await user.type(composer(), 'hello');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(stream.turns).toHaveLength(1));

    await waitFor(() => expect(stopButton()).toHaveFocus());
    await user.keyboard('{Escape}');
    expect(stream.turns[0].signal?.aborted).toBe(true);
  });

  it('Esc does not abort when the key was already used by an inner layer (defaultPrevented)', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await startTurn(user);
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    event.preventDefault();
    stopButton().dispatchEvent(event);
    expect(stream.turns[0].signal?.aborted).toBe(false);
  });

  it('returns focus to the composer when the turn ends and focus was on Stop', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await startTurn(user);
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    await waitFor(() => expect(stopButton()).toHaveFocus());
    stream.turns[0].metadata(41);
    stream.turns[0].done(41, 'Answer');
    await waitFor(() => expect(composer()).toHaveFocus());
  });

  it('does not steal focus from a selector the user moved to while the turn ran', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await startTurn(user);
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    chip('model').focus();
    expect(chip('model')).toHaveFocus();
    stream.turns[0].metadata(41);
    stream.turns[0].done(41, 'Answer');
    await screen.findByText('Answer');
    expect(chip('model')).toHaveFocus();
  });

  it('does not send while an IME composition is confirmed with Enter', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await user.type(composer(), 'ni');
    fireEvent.keyDown(composer(), { key: 'Enter', isComposing: true });
    expect(stream.turns).toHaveLength(0);
  });
});

describe('Chat: one status announcement per turn (H2)', () => {

  it('says once that the assistant is answering and once that the answer is ready, never the tokens', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await startTurn(user);
    await waitFor(() => expect(stream.turns).toHaveLength(1));

    const answering = tr('agentPlayground.chat.statusAnswering', { agent: agent() });
    await waitFor(() => expect(screen.getAllByRole('status').filter((n) => n.textContent === answering)).toHaveLength(1));

    stream.turns[0].metadata(41);
    stream.turns[0].token('Partial text');
    await screen.findByText(/Partial text/);
    // Streamed text is not inside any live region.
    for (const region of screen.getAllByRole('status')) expect(region.textContent).not.toMatch(/Partial text/);
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(0);

    stream.turns[0].done(41, 'Final answer');
    const ready_ = tr('agentPlayground.chat.statusReady', { agent: agent() });
    await waitFor(() => expect(screen.getAllByRole('status').filter((n) => n.textContent === ready_)).toHaveLength(1));
  });

  it('reports a failed turn', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const stream = setupChatApi();
    const { user } = await ready();
    await startTurn(user);
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    stream.turns[0].fail(new Error('boom'));
    const failed = tr('agentPlayground.chat.statusFailed');
    await waitFor(() => expect(screen.getAllByRole('status').filter((n) => n.textContent === failed)).toHaveLength(1));
  });

  it('shows the elapsed-time counter as translated text that is hidden from assistive technology', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await startTurn(user);
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    const counter = await screen.findByText(/^Generating for /);
    expect(counter.parentElement).toHaveAttribute('aria-hidden', 'true');
    expect(counter.closest('[aria-live]')).toBeNull();
  });

  it('prefixes each message with its speaker for screen readers, and hides the avatars', async () => {
    setupChatApi({
      conversations: {
        5: makeDetail(5, {
          messages: [
            { role: 'user', content: 'Question', created_at: '2026-01-01T10:00:00Z' },
            { role: 'assistant', content: 'Reply', created_at: '2026-01-01T10:00:05Z' },
          ],
        } as never),
      },
    });
    await ready('/apps/7/chat/5');
    const region = await screen.findByRole('region', { name: tr('agentPlayground.chat.messagesRegion') });
    expect(region).toHaveAttribute('tabindex', '0');
    expect(await within(region).findByText(tr('agentPlayground.chat.speakerYou'))).toBeInTheDocument();
    expect(within(region).getByText(tr('agentPlayground.chat.speakerAssistant', { agent: agent() }))).toBeInTheDocument();
    expect(within(region).getByText('U').closest('[aria-hidden="true"]')).not.toBeNull();
  });
});

describe('Chat: conversation panel is a real dialog (H3, M5)', () => {
  const conversations = {
    5: makeDetail(5, { title: 'Quarterly plan', message_count: 2 }),
    6: makeDetail(6, { title: 'Another', message_count: 1 }),
  };

  it('moves focus in, inerts the page, points the trigger at it, wraps Tab, and restores focus on Esc', async () => {
    setupChatApi({ conversations });
    const { user } = await ready('/apps/7/chat/5');
    const trigger = screen.getByRole('button', { name: tr('appChat.page.conversations') });
    trigger.focus();
    await user.click(trigger);

    const panel = await screen.findByRole('dialog', { name: tr('agentPlayground.conversations') });
    await waitFor(() => expect(panel).toHaveFocus());
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(trigger).toHaveAttribute('aria-controls', panel.id);
    // The page behind it cannot be reached.
    expect(composer().closest('[inert]')).not.toBeNull();

    // Tab wraps from the last control to the first, and Shift+Tab the other way round.
    const buttons = within(panel).getAllByRole('button');
    buttons[buttons.length - 1].focus();
    await user.tab();
    expect(panel.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).toBe(within(panel).getAllByRole('button')[0]);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(buttons[buttons.length - 1]);

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: tr('agentPlayground.conversations') })).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
    expect(composer().closest('[inert]')).toBeNull();
  });

  it('Esc closes only the delete confirmation, not the panel behind it', async () => {
    setupChatApi({ conversations });
    const { user } = await ready('/apps/7/chat/5');
    const panel = await openConversationsPanel(user);
    await user.click(await within(panel).findByRole('button', { name: tr('conversationSidebar.deleteNamed', { title: 'Another' }) }));
    const confirmDialog = await screen.findByRole('dialog', { name: tr('marketplaceHome.deleteConversation') });
    // The cancel button is a translated label, not an English fallback.
    expect(within(confirmDialog).getByRole('button', { name: tr('cancel') })).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: tr('marketplaceHome.deleteConversation') })).not.toBeInTheDocument());
    expect(screen.getByRole('dialog', { name: tr('agentPlayground.conversations') })).toBeInTheDocument();
    expect(apiMock.deleteAppChatConversation).not.toHaveBeenCalled();
  });

  it('gives every row its own action names and moves focus to a neighbouring row after a delete', async () => {
    setupChatApi({ conversations });
    apiMock.deleteAppChatConversation.mockResolvedValue(undefined as never);
    const { user } = await ready('/apps/7/chat/5');
    const panel = await openConversationsPanel(user);
    const list = await within(panel).findByRole('list');
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(panel).getByRole('button', { name: tr('conversationSidebar.renameNamed', { title: 'Quarterly plan' }) })).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: tr('conversationSidebar.renameNamed', { title: 'Another' }) })).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: /^Quarterly plan/ })).toHaveAttribute('aria-current', 'true');

    await user.click(within(panel).getByRole('button', { name: tr('conversationSidebar.deleteNamed', { title: 'Another' }) }));
    await user.click(await screen.findByRole('button', { name: tr('delete') }));
    await waitFor(() => expect(apiMock.deleteAppChatConversation).toHaveBeenCalledWith(7, 6));
    // No next row: focus goes to the previous one.
    await waitFor(() => expect(within(panel).getByRole('button', { name: /^Quarterly plan/ })).toHaveFocus());
  });

  it('Esc in the rename field cancels without saving and returns focus to the rename button', async () => {
    setupChatApi({ conversations });
    apiMock.renameAppChatConversation.mockResolvedValue(undefined as never);
    const { user } = await ready('/apps/7/chat/5');
    const panel = await openConversationsPanel(user);
    await user.click(await within(panel).findByRole('button', { name: tr('conversationSidebar.renameNamed', { title: 'Another' }) }));
    const input = within(panel).getByRole('textbox', { name: tr('marketplaceHome.renameConversation') });
    await user.clear(input);
    await user.type(input, 'Changed');
    await user.keyboard('{Escape}');
    expect(within(panel).queryByRole('textbox')).not.toBeInTheDocument();
    expect(apiMock.renameAppChatConversation).not.toHaveBeenCalled();
    // The panel stays open: Esc was consumed by the field.
    expect(screen.getByRole('dialog', { name: tr('agentPlayground.conversations') })).toBeInTheDocument();
    await waitFor(() => expect(within(panel).getByRole('button', { name: tr('conversationSidebar.renameNamed', { title: 'Another' }) })).toHaveFocus());
  });

  it('shows a delete failure as an alert in the panel instead of a browser alert', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const nativeAlert = vi.spyOn(window, 'alert').mockImplementation(() => {});
    setupChatApi({ conversations });
    apiMock.deleteAppChatConversation.mockRejectedValue(new Error('nope'));
    const { user } = await ready('/apps/7/chat/5');
    const panel = await openConversationsPanel(user);
    await user.click(await within(panel).findByRole('button', { name: tr('conversationSidebar.deleteNamed', { title: 'Another' }) }));
    await user.click(await screen.findByRole('button', { name: tr('delete') }));
    expect(await within(panel).findByText(tr('conversationSidebar.deleteFailed'))).toBeInTheDocument();
    expect(nativeAlert).not.toHaveBeenCalled();
  });
});

describe('SidePanel on its own', () => {
  it('ignores Esc while a modal is open and when another layer already handled the key', async () => {
    const onClose = vi.fn();
    const { user } = renderWithProviders(
      <div className="relative">
        <button type="button">outside</button>
        <SidePanel open onClose={onClose} title="Panel"><button type="button">inside</button></SidePanel>
      </div>,
    );
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    event.preventDefault();
    document.dispatchEvent(event);
    expect(onClose).not.toHaveBeenCalled();
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe('Chat: reset asks first and reports failures (M3)', () => {
  const conversations = { 5: makeDetail(5, { title: 'Quarterly plan', message_count: 2 }) };
  const resetButton = () => screen.getByRole('button', { name: tr('agentPlayground.chat.reset') });

  it('does nothing when the confirmation is cancelled', async () => {
    setupChatApi({ conversations });
    apiMock.resetAppChatConversation.mockResolvedValue({} as never);
    const { user } = await ready('/apps/7/chat/5');
    await user.click(resetButton());
    const dialog = await screen.findByRole('dialog', { name: tr('agentPlayground.chat.resetConfirmTitle') });
    await user.click(within(dialog).getByRole('button', { name: tr('cancel') }));
    expect(apiMock.resetAppChatConversation).not.toHaveBeenCalled();
  });

  it('resets after confirming and announces it', async () => {
    setupChatApi({ conversations });
    apiMock.resetAppChatConversation.mockResolvedValue({} as never);
    const { user } = await ready('/apps/7/chat/5');
    await user.click(resetButton());
    const dialog = await screen.findByRole('dialog', { name: tr('agentPlayground.chat.resetConfirmTitle') });
    await user.click(within(dialog).getByRole('button', { name: tr('agentPlayground.chat.reset') }));
    await waitFor(() => expect(apiMock.resetAppChatConversation).toHaveBeenCalledWith(7, 5));
    await waitFor(() =>
      expect(screen.getAllByRole('status').some((n) => n.textContent === tr('agentPlayground.chat.statusReset'))).toBe(true),
    );
  });

  it('shows an alert when the reset fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    setupChatApi({ conversations });
    apiMock.resetAppChatConversation.mockRejectedValue(new Error('nope'));
    const { user } = await ready('/apps/7/chat/5');
    await user.click(resetButton());
    const dialog = await screen.findByRole('dialog', { name: tr('agentPlayground.chat.resetConfirmTitle') });
    await user.click(within(dialog).getByRole('button', { name: tr('agentPlayground.chat.reset') }));
    expect(await screen.findByText(tr('agentPlayground.chat.resetFailed'))).toBeInTheDocument();
  });
});

describe('Chat: Spanish wording of the new texts', () => {
  it('is translated', async () => {
    await i18n.changeLanguage('es');
    setupChatApi();
    const { user } = await ready();
    await startTurn(user);
    expect(await screen.findByText(/^Generando durante /)).toBeInTheDocument();
    expect(screen.getAllByRole('status').some((n) => n.textContent === 'Asistente está respondiendo…' || /está respondiendo/.test(n.textContent ?? ''))).toBe(true);
  });
});
