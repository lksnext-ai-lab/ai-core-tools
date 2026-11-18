import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { apiMock, makeDetail, makeOptions, makeTurn, setupChatApi } from './apiMock';
import {
  chip,
  clickNewConversation,
  composer,
  composerDescription,
  deferred,
  openConversationsPanel,
  pickOption,
  renderAppChat,
  sendButton,
  tr,
} from './testUtils';
import i18n from '../../src/i18n';
import type { ChatOptions } from '../../src/types/appChat';

async function waitUntilReady(model: RegExp = /Alpha/) {
  await waitFor(() => expect(chip('model')).toHaveAccessibleName(model));
  await waitFor(() => expect(composer()).toBeEnabled());
}

/** Conversation 5 was left with another model, a source and a skill; the user defaults are Alpha with nothing else. */
function conversationWithOwnSelection() {
  return {
    5: makeDetail(5, {
      current_selection: { ai_service_id: 2, silo_id: 10, skill_ids: [21], mcp_config_ids: [30] },
    }),
  };
}

describe('AppChatPage "New conversation" after an opened conversation', () => {
  it('blocks sending until the defaults refetch settles, never sends the old selection, then applies the fresh defaults', async () => {
    const stream = setupChatApi({ conversations: conversationWithOwnSelection() });
    const { user } = renderAppChat('/apps/7/chat/5');
    await waitUntilReady(/Beta/);

    // The defaults changed meanwhile (the backend updates them after every completed turn).
    const freshDefaults = makeOptions({
      default_selection: { ai_service_id: 1, silo_id: 10, skill_ids: [], mcp_config_ids: [] },
    });
    const refetch = deferred<ChatOptions>();
    apiMock.getAppChatOptions.mockImplementationOnce((() => refetch.promise) as never);

    await clickNewConversation(user);
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/apps\/7\/chat$/));

    // While the refetch is pending: nothing can be sent and the selectors are locked.
    await user.type(composer(), 'fresh question{Enter}');
    expect(sendButton()).toBeDisabled();
    // The selectors are locked while a model is in fact selected: the reason is "loading", not "select a model".
    expect(composerDescription()).toBe('Loading the chat settings...');
    expect(composerDescription()).toBe(tr('appChat.blocked.loading'));
    expect(composerDescription()).not.toBe(tr('appChat.blocked.noSelection'));
    expect(chip('model')).toBeDisabled();
    expect(apiMock.streamAppChatMessage).not.toHaveBeenCalled();

    refetch.resolve(freshDefaults);
    await waitFor(() => expect(sendButton()).toBeEnabled());
    expect(chip('model')).toHaveAccessibleName(/Alpha/);
    expect(chip('source')).toHaveAccessibleName(/Handbook/);
    expect(chip('skills')).not.toHaveAccessibleName(/Translate/);
    expect(chip('mcps')).not.toHaveAccessibleName(/Tickets/);

    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    expect(stream.turns[0].request.selection).toEqual({
      ai_service_id: 1,
      silo_id: 10,
      skill_ids: [],
      mcp_config_ids: [],
    });
    expect(stream.turns[0].request.conversationId ?? null).toBeNull();
    expect(apiMock.streamAppChatMessage).toHaveBeenCalledTimes(1);
  });

  it('a second click on "New" while the refetch is pending does not leave the page blocked', async () => {
    setupChatApi({ conversations: conversationWithOwnSelection() });
    const { user } = renderAppChat('/apps/7/chat/5');
    await waitUntilReady(/Beta/);

    const refetch = deferred<ChatOptions>();
    apiMock.getAppChatOptions.mockImplementationOnce((() => refetch.promise) as never);
    await clickNewConversation(user);
    await waitFor(() => expect(sendButton()).toBeDisabled());
    await clickNewConversation(user);
    expect(sendButton()).toBeDisabled();

    refetch.resolve(makeOptions());
    await user.type(composer(), 'hello');
    await waitFor(() => expect(sendButton()).toBeEnabled());
    expect(chip('model')).toBeEnabled();
    expect(chip('model')).toHaveAccessibleName(/Alpha/);
    // One refetch served both clicks.
    expect(apiMock.getAppChatOptions).toHaveBeenCalledTimes(2);
  });

  it('falls back to the options already loaded when the refetch fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const stream = setupChatApi({ conversations: conversationWithOwnSelection() });
    const { user } = renderAppChat('/apps/7/chat/5');
    await waitUntilReady(/Beta/);

    apiMock.getAppChatOptions.mockRejectedValueOnce(new Error('network down'));
    await clickNewConversation(user);

    await user.type(composer(), 'offline question');
    await waitFor(() => expect(sendButton()).toBeEnabled());
    // The loaded defaults (Alpha, nothing else), not the conversation that was left.
    expect(chip('model')).toHaveAccessibleName(/Alpha/);
    expect(screen.queryByText(tr('appChat.page.optionsLoadFailed'))).not.toBeInTheDocument();
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    expect(stream.turns[0].request.selection).toEqual({ ai_service_id: 1, silo_id: null, skill_ids: [], mcp_config_ids: [] });
  });

  it('keeps a selection the user changed while the refetch was pending', async () => {
    const stream = setupChatApi({ conversations: conversationWithOwnSelection() });
    const { user } = renderAppChat('/apps/7/chat/5');
    await waitUntilReady(/Beta/);
    const refetch = deferred<ChatOptions>();
    apiMock.getAppChatOptions.mockImplementationOnce((() => refetch.promise) as never);
    await clickNewConversation(user);
    // Selectors are locked while pending, so the change can only come after: unblock first, then adjust.
    refetch.resolve(makeOptions());
    await waitFor(() => expect(chip('model')).toBeEnabled());
    await pickOption(user, 'model', /Beta/);
    await user.type(composer(), 'with beta');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    expect(stream.turns[0].request.selection.ai_service_id).toBe(2);
  });
});

describe('AppChatPage while the selection is being resolved', () => {
  it('a deep link shows the loading reason and a loading chip, never "select a model", until the conversation loads', async () => {
    const detail = deferred<ReturnType<typeof makeDetail>>();
    setupChatApi({ conversations: conversationWithOwnSelection() });
    apiMock.getAppChatConversation.mockImplementation((() => detail.promise) as never);
    renderAppChat('/apps/7/chat/5');
    await waitFor(() => expect(composer()).toBeInTheDocument());
    await waitFor(() => expect(composerDescription()).toBe(tr('appChat.blocked.loading')));
    expect(chip('model')).toBeDisabled();
    expect(chip('model')).toHaveAccessibleName(`Model ${tr('appChat.page.loading')}`);
    expect(document.body).not.toHaveTextContent(tr('appChat.selection.modelPlaceholder'));
    expect(document.body).not.toHaveTextContent(tr('appChat.blocked.noSelection'));

    detail.resolve(conversationWithOwnSelection()[5]);
    await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Beta/));
    await waitFor(() => expect(composerDescription()).toBe(''));
  });

  it('in Spanish the pending "New" refetch says "loading", not "select a model"', async () => {
    await i18n.changeLanguage('es');
    setupChatApi({ conversations: conversationWithOwnSelection() });
    const { user } = renderAppChat('/apps/7/chat/5');
    await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Beta/));
    await waitFor(() => expect(composer()).toBeEnabled());
    const refetch = deferred<ChatOptions>();
    apiMock.getAppChatOptions.mockImplementationOnce((() => refetch.promise) as never);
    await clickNewConversation(user);
    await waitFor(() => expect(composerDescription()).toBe('Cargando los ajustes del chat...'));
    expect(composerDescription()).not.toBe(tr('appChat.blocked.noSelection'));
    refetch.resolve(makeOptions());
    await waitFor(() => expect(composerDescription()).toBe(''));
  });
});

describe('AppChatPage switching conversation while a first turn is streaming', () => {
  it('does not navigate away when the old stream finishes, keeps the new selection, and refreshes the sidebar', async () => {
    const stream = setupChatApi({
      conversations: {
        5: makeDetail(5, {
          title: 'Other conversation',
          current_selection: { ai_service_id: 1, silo_id: null, skill_ids: [21], mcp_config_ids: [] },
        }),
      },
    });
    const { user } = renderAppChat();
    await waitUntilReady();

    await pickOption(user, 'model', /Beta/);
    await user.type(composer(), 'long running question');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    const oldTurn = stream.turns[0];
    oldTurn.metadata(99);
    oldTurn.token('partial');

    // The user opens another conversation from the list while the first turn is still running.
    await openConversationsPanel(user);
    await user.click(await screen.findByRole('button', { name: /^Other conversation/ }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/apps/7/chat/5'));
    await waitFor(() => expect(chip('skills')).toHaveAccessibleName(/Translate/));
    expect(chip('model')).toHaveAccessibleName(/Alpha/);
    const listCallsBefore = apiMock.listAppChatConversations.mock.calls.length;

    // The old stream completes, with a warning that belongs to the conversation that was left.
    oldTurn.done(99, 'late answer', makeTurn({ warnings: [{ kind: 'mcp_config', id: 30 }] }));
    await waitFor(() => expect(apiMock.listAppChatConversations.mock.calls.length).toBe(listCallsBefore + 1));

    expect(screen.getByTestId('location')).toHaveTextContent(/^\/apps\/7\/chat\/5$/);
    expect(chip('model')).toHaveAccessibleName(/Alpha/);
    expect(chip('skills')).toHaveAccessibleName(/Translate/);
    expect(screen.queryByText('late answer')).not.toBeInTheDocument();
    expect(screen.queryByText('long running question')).not.toBeInTheDocument();
    expect(screen.queryByText(tr('appChat.warnings.title'))).not.toBeInTheDocument();
    // The new conversation is usable and carries its own selection.
    await user.type(composer(), 'in conversation five');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(2));
    expect(stream.turns[1].request.conversationId).toBe(5);
    expect(stream.turns[1].request.selection).toEqual({ ai_service_id: 1, silo_id: null, skill_ids: [21], mcp_config_ids: [] });
  });
});

