import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { apiError, apiMock, makeDetail, makeOptions, makeTurn, makeTurnConfig, setupChatApi } from './apiMock';
import {
  chip,
  composer,
  composerDescription,
  deferred,
  openConversationsPanel,
  pickOption,
  renderAppChat,
  sendButton,
  tr,
  waitForChat,
} from './testUtils';

/** The page is usable: options loaded, the selection resolved, the composer enabled. */
async function waitUntilReady(model: RegExp = /Alpha/) {
  await waitForChat();
  await waitFor(() => expect(chip('model')).toHaveAccessibleName(model));
  await waitFor(() => expect(composer()).toBeEnabled());
}

describe('AppChatPage first turn of a new conversation', () => {
  it('sends the selection on screen, keeps the chat in place when the URL catches up, and badges the answer', async () => {
    const stream = setupChatApi();
    const { user, navigations } = renderAppChat();
    await waitUntilReady();
    const textareaBefore = composer();
    const modelChipBefore = chip('model');

    // Change the model and a skill, then send: the payload carries what is on screen at that moment.
    await pickOption(user, 'model', /Beta/);
    await user.click(chip('skills'));
    await user.click(await screen.findByRole('option', { name: /Summarize/ }));
    await user.keyboard('{Escape}');
    await user.type(composer(), 'Hello there');
    await user.click(sendButton());

    await waitFor(() => expect(stream.turns).toHaveLength(1));
    const turn = stream.turns[0];
    expect(turn.request.message).toBe('Hello there');
    expect(turn.request.selection).toEqual({ ai_service_id: 2, silo_id: null, skill_ids: [20], mcp_config_ids: [] });
    expect(turn.request.conversationId ?? null).toBeNull();

    turn.metadata(99, makeTurnConfig({ ai_service: { id: 2, name: 'Beta' }, skills: [{ id: 20, name: 'Summarize' }] }));
    turn.token('Hi');
    expect(await screen.findByText('Hi')).toBeInTheDocument();
    // Still on the new-chat route while streaming.
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/apps\/7\/chat$/);

    turn.done(
      99,
      'Hi there, friend',
      makeTurn({ ai_service_id: 2, ai_service_name: 'Beta', skills: [{ id: 20, name: 'Summarize', deleted: false }] }),
    );

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/apps/7/chat/99'));
    expect(navigations.at(-1)).toEqual({ pathname: '/apps/7/chat/99', type: 'REPLACE' });

    // Not blanked, not reloaded from history.
    expect(screen.getByText('Hello there')).toBeInTheDocument();
    expect(screen.getByText('Hi there, friend')).toBeInTheDocument();
    expect(apiMock.getAppChatConversation).not.toHaveBeenCalled();
    // First assistant message carries its model badge (a disclosure because it also used a skill).
    expect(screen.getByRole('button', { name: tr('appChat.meta.toggle', { model: 'Beta' }) })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    // Not remounted: same DOM nodes, selection state survived the route change.
    expect(composer()).toBe(textareaBefore);
    expect(chip('model')).toBe(modelChipBefore);
    expect(chip('model')).toHaveAccessibleName(/Beta/);
    expect(chip('skills')).toHaveAccessibleName(/Summarize/);
    // The turn is persisted server-side, so the list is refreshed once for it (entry load + one refresh).
    await waitFor(() => expect(apiMock.listAppChatConversations).toHaveBeenCalledTimes(2));

    // The follow-up goes to the same conversation with the same selection.
    await user.type(composer(), 'And then?');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(2));
    expect(stream.turns[1].request.conversationId).toBe(99);
    expect(stream.turns[1].request.selection.ai_service_id).toBe(2);
  });

  it('keeps the warnings of the turn visible after the URL changes, and dismissing them focuses the composer', async () => {
    const stream = setupChatApi();
    const { user } = renderAppChat();
    await waitUntilReady();

    await user.type(composer(), 'use the tickets tool');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    stream.turns[0].metadata(41);
    stream.turns[0].done(41, 'Answered without it', makeTurn({ warnings: [{ kind: 'mcp_config', id: 30 }] }));

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/apps/7/chat/41'));
    const title = await screen.findByText(tr('appChat.warnings.title'));
    const alert = title.closest('[role="alert"]') as HTMLElement;
    expect(within(alert).getByText(tr('appChat.warnings.mcp_configNamed', { name: 'Tickets' }))).toBeInTheDocument();

    await user.click(within(alert).getByRole('button', { name: tr('alert.dismissNamed', { name: tr('appChat.warnings.title') }) }));
    expect(screen.queryByText(tr('appChat.warnings.title'))).not.toBeInTheDocument();
    expect(composer()).toHaveFocus();
  });
});

describe('AppChatPage errors on send', () => {
  it('HTTP 409 SERVICE_RETIRED: translated error, options refetched, send blocked until another model is picked', async () => {
    const stream = setupChatApi();
    const retiredOptions = makeOptions({
      ai_services: [
        { service_id: 1, name: 'Alpha', is_system: false, lifecycle_status: 'retired' },
        { service_id: 2, name: 'Beta', is_system: false, lifecycle_status: 'active' },
      ],
    });
    apiMock.getAppChatOptions.mockResolvedValueOnce(makeOptions()).mockResolvedValue(retiredOptions);
    const { user } = renderAppChat();
    await waitUntilReady();

    await user.type(composer(), 'first try');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(apiError(409, 'SERVICE_RETIRED'));
    await user.click(sendButton());

    // Translated error in the conversation and the page notice.
    expect(await screen.findByText(tr('appChat.transportErrors.serviceRetired'))).toBeInTheDocument();
    expect(await screen.findByText(tr('appChat.notices.serviceRetired'))).toBeInTheDocument();
    await waitFor(() => expect(apiMock.getAppChatOptions).toHaveBeenCalledTimes(2));

    // The retired model stays selected but sending is blocked, with the reason announced.
    await user.type(composer(), 'second try');
    await waitFor(() => expect(sendButton()).toBeDisabled());
    await waitFor(() => expect(composerDescription()).toBe(tr('appChat.blocked.modelRetired')));
    await user.click(chip('model'));
    expect(await screen.findByRole('option', { name: /Alpha/ })).toHaveAttribute('aria-disabled', 'true');
    await user.click(screen.getByRole('option', { name: /Beta/ }));

    await waitFor(() => expect(sendButton()).toBeEnabled());
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    expect(stream.turns[0].request.selection.ai_service_id).toBe(2);
    expect(stream.turns[0].request.message).toBe('second try');
  });

  it('HTTP 403: translated error and no retired-model handling', async () => {
    setupChatApi();
    const { user } = renderAppChat();
    await waitUntilReady();
    await user.type(composer(), 'hello');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(apiError(403));
    await user.click(sendButton());

    expect(await screen.findByText(tr('appChat.transportErrors.forbidden'))).toBeInTheDocument();
    expect(screen.queryByText(tr('appChat.notices.serviceRetired'))).not.toBeInTheDocument();
    expect(apiMock.getAppChatOptions).toHaveBeenCalledTimes(1);
  });
});

describe('AppChatPage conversations sidebar', () => {
  it('refreshes the list in place after a turn: no spinner, same nodes, an in-progress rename survives', async () => {
    const stream = setupChatApi({ conversations: { 5: makeDetail(5, { title: 'Quarterly plan', message_count: 2 }) } });
    const { user } = renderAppChat('/apps/7/chat/5');
    await waitUntilReady();

    // Type the message first: once the rename input has the focus the keyboard no longer goes to the composer.
    await user.type(composer(), 'next question');
    await openConversationsPanel(user);
    await screen.findByRole('button', { name: /^Quarterly plan/ });
    expect(apiMock.listAppChatConversations).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: tr('conversationSidebar.renameNamed', { title: 'Quarterly plan' }) }));
    const input = screen.getByRole('textbox', { name: tr('marketplaceHome.renameConversation') });
    await user.clear(input);
    await user.type(input, 'Quarterly pl');

    // The next list request stays pending so the in-flight state can be observed.
    const refreshed = deferred<{ conversations: unknown[]; total: number }>();
    apiMock.listAppChatConversations.mockImplementationOnce((() => refreshed.promise) as never);
    // fireEvent does not move the focus away from the rename input.
    fireEvent.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    stream.turns[0].done(5, 'Answer');
    await waitFor(() => expect(apiMock.listAppChatConversations).toHaveBeenCalledTimes(2));

    expect(screen.queryByText(tr('conversationSidebar.loading'))).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: tr('marketplaceHome.renameConversation') })).toBe(input);

    refreshed.resolve({
      conversations: [
        { conversation_id: 5, title: 'Quarterly plan', created_at: '2026-01-01T10:00:00Z', updated_at: '2026-01-01T11:00:00Z', message_count: 4 },
        { conversation_id: 6, title: 'Another', created_at: '2026-01-01T10:30:00Z', updated_at: '2026-01-01T10:30:00Z', message_count: 1 },
      ],
      total: 2,
    });
    expect(await screen.findByText('Another')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: tr('marketplaceHome.renameConversation') })).toBe(input);
    expect(input).toHaveValue('Quarterly pl');
    expect(input).toHaveFocus();
    expect(screen.queryByText(tr('conversationSidebar.loading'))).not.toBeInTheDocument();
    // One refresh per turn, not two.
    expect(apiMock.listAppChatConversations).toHaveBeenCalledTimes(2);
  });
});
