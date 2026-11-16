import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { apiMock, apiError, makeDetail, makeOptions, setupChatApi } from './apiMock';
import {
  chip,
  composer,
  composerDescription,
  renderAppChat,
  sendButton,
  tr,
  waitForChat,
} from './testUtils';

describe('AppChatPage entry', () => {
  it('loads the options once and shows the user default selection', async () => {
    setupChatApi({
      options: makeOptions({
        default_selection: { ai_service_id: 2, silo_id: 10, skill_ids: [20], mcp_config_ids: [30] },
      }),
    });
    renderAppChat();
    await waitForChat();

    await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Beta/));
    expect(chip('source')).toHaveAccessibleName(/Handbook/);
    expect(chip('skills')).toHaveAccessibleName(/Summarize/);
    expect(chip('mcps')).toHaveAccessibleName(/Tickets/);
    expect(apiMock.getAppChatOptions).toHaveBeenCalledTimes(1);
    expect(apiMock.getAppChatOptions).toHaveBeenCalledWith(7);
  });

  describe('without a usable model', () => {
    const noModel = () =>
      makeOptions({
        ai_services: [
          { service_id: 3, name: 'Gamma', is_system: false, lifecycle_status: 'retired' },
        ],
        default_selection: null,
        has_usable_model: false,
      });

    it('shows the empty state, blocks sending and explains why in the status region the textarea points to', async () => {
      const { user } = setupAndRender('owner');
      await waitForChat();

      expect(await screen.findByText(tr('appChat.empty.title'))).toBeInTheDocument();
      const reason = tr('appChat.blocked.noUsableModel');
      expect(composerDescription()).toBe(reason);
      const status = document.getElementById(composer().getAttribute('aria-describedby') as string) as HTMLElement;
      expect(status).toHaveAttribute('role', 'status');
      expect(sendButton()).toHaveAttribute('aria-describedby', status.id);

      await user.type(composer(), 'hello{Enter}');
      expect(sendButton()).toBeDisabled();
      expect(apiMock.streamAppChatMessage).not.toHaveBeenCalled();
    });

    it('offers the settings link to administrators and owners', async () => {
      setupAndRender('administrator');
      const link = await screen.findByRole('link', { name: tr('appChat.empty.configureLink') });
      expect(link).toHaveAttribute('href', '/apps/7/settings/ai-services');
      expect(screen.getByText(tr('appChat.empty.messageAdmin'))).toBeInTheDocument();
    });

    it.each(['editor', 'viewer'])('does not offer the settings link to a %s', async (role) => {
      setupAndRender(role);
      await waitForChat();
      // The role arrives with a separate request: wait for it before asserting an absence.
      await waitFor(() => expect(apiMock.getApp).toHaveBeenCalled());
      await apiMock.getApp.mock.results[0].value;
      expect(await screen.findByText(tr('appChat.empty.messageMember'))).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: tr('appChat.empty.configureLink') })).not.toBeInTheDocument();
      expect(screen.queryByText(tr('appChat.empty.messageAdmin'))).not.toBeInTheDocument();
    });

    function setupAndRender(role: string) {
      setupChatApi({ options: noModel(), role });
      return renderAppChat();
    }
  });
});

describe('AppChatPage opening a conversation by URL', () => {
  it('uses the conversation own selection, not the defaults, and sends it', async () => {
    const stream = setupChatApi({
      options: makeOptions({ default_selection: { ai_service_id: 1, silo_id: null, skill_ids: [], mcp_config_ids: [] } }),
      conversations: {
        5: makeDetail(5, {
          current_selection: { ai_service_id: 2, silo_id: 10, skill_ids: [21], mcp_config_ids: [30] },
        }),
      },
    });
    const { user } = renderAppChat('/apps/7/chat/5');

    await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Beta/));
    expect(chip('source')).toHaveAccessibleName(/Handbook/);
    expect(chip('skills')).toHaveAccessibleName(/Translate/);
    expect(chip('mcps')).toHaveAccessibleName(/Tickets/);

    await waitFor(() => expect(composer()).toBeEnabled());
    await user.type(composer(), 'continue');
    await waitFor(() => expect(sendButton()).toBeEnabled());
    await user.click(sendButton());

    await waitFor(() => expect(stream.turns).toHaveLength(1));
    expect(stream.turns[0].request.selection).toEqual({
      ai_service_id: 2,
      silo_id: 10,
      skill_ids: [21],
      mcp_config_ids: [30],
    });
    expect(stream.turns[0].request.conversationId).toBe(5);
  });

  it('shows the "not available" notice and redirects to /chat when the conversation does not exist (404)', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    setupChatApi({ conversations: {} });
    const { user, navigations } = renderAppChat('/apps/7/chat/404');

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/apps\/7\/chat$/));
    expect(navigations.at(-1)).toEqual({ pathname: '/apps/7/chat', type: 'REPLACE' });

    const notice = screen.getByText(tr('appChat.notices.conversationNotFound'));
    expect(notice.closest('[role="alert"]')).toBeInTheDocument();
    // The redirect must not clear the notice, and the new chat is usable with the defaults.
    await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Alpha/));
    await waitFor(() => expect(composer()).toBeEnabled());
    await user.type(composer(), 'hello');
    await waitFor(() => expect(sendButton()).toBeEnabled());
    expect(screen.getByText(tr('appChat.notices.conversationNotFound'))).toBeInTheDocument();
    expect(apiMock.getAppChatConversation).toHaveBeenCalledWith(7, 404);
  });

  it('keeps the notice until it is dismissed, then moves focus to the composer', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    setupChatApi({ conversations: {} });
    const { user } = renderAppChat('/apps/7/chat/404');
    const notice = (await screen.findByText(tr('appChat.notices.conversationNotFound'))).closest(
      '[role="alert"]',
    ) as HTMLElement;
    await user.click(within(notice).getByRole('button', { name: tr('alert.dismissNamed', { name: tr('appChat.notices.label') }) }));
    expect(screen.queryByText(tr('appChat.notices.conversationNotFound'))).not.toBeInTheDocument();
    expect(composer()).toHaveFocus();
  });

  it('shows an error with a retry when the options cannot be loaded', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    setupChatApi();
    apiMock.getAppChatOptions.mockRejectedValueOnce(apiError(500));
    const { user } = renderAppChat();
    expect(await screen.findByText(tr('appChat.page.optionsLoadFailed'))).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: tr('appChat.page.retry') }));
    await waitForChat();
  });
});
