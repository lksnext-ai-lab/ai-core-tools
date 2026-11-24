import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import i18n from '../../src/i18n';
import type { ChatAttachmentIndexing } from '../../src/types/appChat';
import { apiError, apiMock, makeOptions, makeTurn, setupChatApi } from './apiMock';
import { chip, composer, deferred, dismissName, renderAppChat, sendButton, tr } from './testUtils';

const NO_DEFAULT: ChatAttachmentIndexing = { enabled: false, reason: 'no_default_embedding_service' };
const RETIRED: ChatAttachmentIndexing = { enabled: false, reason: 'embedding_service_retired' };

async function ready() {
  await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Alpha|Alfa/));
  await waitFor(() => expect(composer()).toBeEnabled());
}

/** Waits for the role request, which is separate from the options, before asserting something is absent. */
async function roleLoaded() {
  await waitFor(() => expect(apiMock.getApp).toHaveBeenCalled());
  await apiMock.getApp.mock.results[0].value;
}

const noticeTitle = () => screen.queryByText(tr('appChat.attachmentIndexing.title'));

describe('Chat notice: attachment indexing is off', () => {
  it.each([
    ['no_default', NO_DEFAULT, 'noDefault'],
    ['retired', RETIRED, 'retired'],
  ])('administrators see the %s notice with a link to the App settings', async (_name, indexing, key) => {
    setupChatApi({ options: makeOptions({ attachment_indexing: indexing }), role: 'administrator' });
    renderAppChat();
    await ready();

    const title = await screen.findByText(tr('appChat.attachmentIndexing.title'));
    const notice = title.closest('[role]') as HTMLElement;
    expect(within(notice).getByText(new RegExp(tr(`appChat.attachmentIndexing.${key}`).slice(0, 40)))).toBeInTheDocument();
    // What happens to the files meanwhile is stated.
    expect(notice).toHaveTextContent(/sent whole to the model/);
    const link = await within(notice).findByRole('link', { name: tr('appChat.attachmentIndexing.configureLink') });
    expect(link).toHaveAttribute('href', '/apps/7/settings');
    expect(within(notice).queryByText(tr('appChat.attachmentIndexing.askAdmin'))).not.toBeInTheDocument();
  });

  it.each(['viewer', 'editor'])('a %s is told to ask an administrator or owner, with no link', async (role) => {
    setupChatApi({ options: makeOptions({ attachment_indexing: NO_DEFAULT }), role });
    renderAppChat();
    await ready();
    await roleLoaded();

    expect(await screen.findByText(new RegExp(tr('appChat.attachmentIndexing.askAdmin')))).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: tr('appChat.attachmentIndexing.configureLink') })).not.toBeInTheDocument();
  });

  it('chatting still works while the notice is shown', async () => {
    const stream = setupChatApi({ options: makeOptions({ attachment_indexing: NO_DEFAULT }), role: 'owner' });
    const { user } = renderAppChat();
    await ready();
    await screen.findByText(tr('appChat.attachmentIndexing.title'));
    await user.type(composer(), 'hello');
    await waitFor(() => expect(sendButton()).toBeEnabled());
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
  });

  it('is dismissible, focuses the composer, and stays dismissed while the page lives', async () => {
    setupChatApi({ options: makeOptions({ attachment_indexing: NO_DEFAULT }), role: 'owner' });
    const { user } = renderAppChat();
    await ready();
    const notice = (await screen.findByText(tr('appChat.attachmentIndexing.title'))).closest('[role]') as HTMLElement;
    await user.click(within(notice).getByRole('button', { name: dismissName }));
    expect(noticeTitle()).not.toBeInTheDocument();
    expect(composer()).toHaveFocus();
  });

  it('comes back on the next visit while the condition holds', async () => {
    setupChatApi({ options: makeOptions({ attachment_indexing: NO_DEFAULT }), role: 'owner' });
    const first = renderAppChat();
    await ready();
    const notice = (await screen.findByText(tr('appChat.attachmentIndexing.title'))).closest('[role]') as HTMLElement;
    await first.user.click(within(notice).getByRole('button', { name: dismissName }));
    first.unmount();

    renderAppChat();
    await ready();
    expect(await screen.findByText(tr('appChat.attachmentIndexing.title'))).toBeInTheDocument();
  });

  it.each([
    ['enabled', { enabled: true, reason: null } as ChatAttachmentIndexing],
    ['absent (older backend)', undefined],
  ])('is not shown when indexing is %s', async (_name, indexing) => {
    setupChatApi({ options: makeOptions(indexing ? { attachment_indexing: indexing } : {}), role: 'owner' });
    renderAppChat();
    await ready();
    await roleLoaded();
    expect(noticeTitle()).not.toBeInTheDocument();
  });

  it('is translated in Spanish', async () => {
    await i18n.changeLanguage('es');
    setupChatApi({ options: makeOptions({ attachment_indexing: RETIRED }), role: 'viewer' });
    renderAppChat();
    await screen.findByText('Los archivos adjuntos no se indexarán');
    await roleLoaded();
    expect(await screen.findByText(/ha llegado a su fin de servicio, así que los archivos adjuntos/)).toBeInTheDocument();
    expect(screen.getByText(/Pide a un administrador o propietario de esta App que lo configure/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/appChat\.attachmentIndexing/);
    expect(document.body).not.toHaveTextContent('Attached files will not be indexed');
  });
});

describe('Chat notices: accessible names, kinds and role', () => {
  it('gives each stacked alert a dismiss button with its own name', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    setupChatApi({ options: makeOptions({ attachment_indexing: NO_DEFAULT }), role: 'owner' });
    renderAppChat('/apps/7/chat/404');
    await screen.findByText(tr('appChat.notices.conversationNotFound'));
    await screen.findByText(tr('appChat.attachmentIndexing.title'));
    const names = screen.getAllByRole('button', { name: /^Dismiss/ }).map((b) => b.getAttribute('aria-label'));
    expect(names).toEqual(
      expect.arrayContaining([
        tr('alert.dismissNamed', { name: tr('appChat.attachmentIndexing.title') }),
        tr('alert.dismissNamed', { name: tr('appChat.notices.label') }),
      ]),
    );
    expect(new Set(names).size).toBe(names.length);
  });

  it('dismissing one kind of notice does not hide a different one that appears later', async () => {
    setupChatApi({ options: makeOptions({ attachment_indexing: NO_DEFAULT }), role: 'owner' });
    const retiredOptions = makeOptions({
      attachment_indexing: RETIRED,
      ai_services: [
        { service_id: 1, name: 'Alpha', is_system: false, lifecycle_status: 'retired' },
        { service_id: 2, name: 'Beta', is_system: false, lifecycle_status: 'active' },
      ],
    });
    apiMock.getAppChatOptions
      .mockResolvedValueOnce(makeOptions({ attachment_indexing: NO_DEFAULT }))
      .mockResolvedValue(retiredOptions);
    const { user } = renderAppChat();
    await ready();
    const notice = (await screen.findByText(tr('appChat.attachmentIndexing.title'))).closest('[role]') as HTMLElement;
    await user.click(within(notice).getByRole('button', { name: dismissName }));
    expect(noticeTitle()).not.toBeInTheDocument();

    // A turn finds the model retired; the options refetch now reports the embedding service as retired too.
    await user.type(composer(), 'hi');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(apiError(409, 'SERVICE_RETIRED'));
    await user.click(sendButton());
    expect(await screen.findByText(new RegExp(tr('appChat.attachmentIndexing.retired').slice(0, 40)))).toBeInTheDocument();
  });

  it('an unknown reason gets a generic text, not a claim about the default service', async () => {
    setupChatApi({
      options: makeOptions({ attachment_indexing: { enabled: false, reason: 'something_new' as never } }),
      role: 'owner',
    });
    renderAppChat();
    await ready();
    expect(await screen.findByText(new RegExp(tr('appChat.attachmentIndexing.unavailable').slice(0, 40)))).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(tr('appChat.attachmentIndexing.noDefault'));
  });

  it('says nothing role-specific until the role is known, so an administrator never sees "ask an administrator"', async () => {
    const role = deferred<unknown>();
    setupChatApi({ options: makeOptions({ attachment_indexing: NO_DEFAULT }), role: 'administrator' });
    apiMock.getApp.mockImplementation((() => role.promise) as never);
    renderAppChat();
    await ready();
    await screen.findByText(tr('appChat.attachmentIndexing.title'));
    expect(screen.queryByText(new RegExp(tr('appChat.attachmentIndexing.askAdmin')))).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: tr('appChat.attachmentIndexing.configureLink') })).not.toBeInTheDocument();

    role.resolve({ app_id: 7, name: 'Demo', user_role: 'administrator' });
    expect(await screen.findByRole('link', { name: tr('appChat.attachmentIndexing.configureLink') })).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(tr('appChat.attachmentIndexing.askAdmin')))).not.toBeInTheDocument();
  });

  it('the empty-model state also waits for the role before choosing its wording', async () => {
    const role = deferred<unknown>();
    setupChatApi({
      options: makeOptions({ ai_services: [], default_selection: null, has_usable_model: false }),
      role: 'administrator',
    });
    apiMock.getApp.mockImplementation((() => role.promise) as never);
    renderAppChat();
    await screen.findByText(tr('appChat.empty.title'));
    expect(screen.queryByText(tr('appChat.empty.messageMember'))).not.toBeInTheDocument();
    expect(screen.queryByText(tr('appChat.empty.messageAdmin'))).not.toBeInTheDocument();
    role.resolve({ app_id: 7, name: 'Demo', user_role: 'administrator' });
    expect(await screen.findByText(tr('appChat.empty.messageAdmin'))).toBeInTheDocument();
  });
});

describe('Chat: conversation busy (HTTP 409 CONVERSATION_BUSY)', () => {
  async function sendBusy(language?: string) {
    if (language) await i18n.changeLanguage(language);
    const stream = setupChatApi({ role: 'owner' });
    const { user } = renderAppChat();
    await ready();
    await user.type(composer(), 'my long question');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(apiError(409, 'CONVERSATION_BUSY'));
    await user.click(sendButton());
    return { stream, user };
  }

  it('shows the translated error, gives the message back to the composer and does not touch options or selection', async () => {
    await sendBusy();
    expect(await screen.findByText(tr('appChat.transportErrors.conversationBusy'))).toBeInTheDocument();
    expect(composer()).toHaveValue('my long question');
    // The rejected message is not left in the conversation as if it had been sent.
    expect(screen.queryByText('my long question', { selector: 'p, div' })).not.toBeInTheDocument();
    expect(apiMock.getAppChatOptions).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(tr('appChat.notices.serviceRetired'))).not.toBeInTheDocument();
    expect(chip('model')).toHaveAccessibleName(/Alpha/);
  });

  it('does not block sending: the same message can be resent and then goes through', async () => {
    const { stream, user } = await sendBusy();
    await screen.findByText(tr('appChat.transportErrors.conversationBusy'));
    await waitFor(() => expect(sendButton()).toBeEnabled());
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    expect(stream.turns[0].request.message).toBe('my long question');
    stream.turns[0].done(31, 'finally', makeTurn());
    expect(await screen.findByText('finally')).toBeInTheDocument();
  });

  it('locks the composer while the turn is in flight and hands the message back on rejection', async () => {
    // The composer cannot be edited during the turn, so the rejected message always returns into an empty box.
    setupChatApi({ role: 'owner' });
    const { user } = renderAppChat();
    await ready();
    await user.type(composer(), 'first');
    let rejectTurn!: (error: Error) => void;
    apiMock.streamAppChatMessage.mockImplementationOnce((() =>
      new Promise((_resolve, reject) => {
        rejectTurn = reject;
      })) as never);
    await user.click(sendButton());
    await waitFor(() => expect(composer()).toBeDisabled());
    expect(composer()).toHaveValue('');
    rejectTurn(apiError(409, 'CONVERSATION_BUSY'));
    await waitFor(() => expect(composer()).toHaveValue('first'));
  });

  it('announces the rejection (role=alert) and returns focus to the composer, which says the message was kept', async () => {
    await sendBusy();
    const message = await screen.findByText(tr('appChat.transportErrors.conversationBusy'));
    expect(tr('appChat.transportErrors.conversationBusy')).toMatch(/kept/);
    expect(message.closest('[role="alert"]')).toBeInTheDocument();
    await waitFor(() => expect(composer()).toHaveFocus());
  });

  it.each([
    ['403', apiError(403), 'appChat.transportErrors.forbidden'],
    ['a generic failure', new Error('boom'), null],
  ])('after %s the error is announced and the composer gets focus back', async (_n, error, key) => {
    setupChatApi({ role: 'owner' });
    const { user } = renderAppChat();
    await ready();
    await user.type(composer(), 'hello');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(error);
    await user.click(sendButton());
    const text = await screen.findByText(key ? tr(key) : 'boom');
    expect(text.closest('[role="alert"]')).toBeInTheDocument();
    await waitFor(() => expect(composer()).toHaveFocus());
  });

  it('does not steal focus when the user moved to another control while the turn was running', async () => {
    setupChatApi({ role: 'owner' });
    const { user } = renderAppChat();
    await ready();
    await user.type(composer(), 'hello');
    let rejectTurn!: (error: Error) => void;
    apiMock.streamAppChatMessage.mockImplementationOnce((() =>
      new Promise((_resolve, reject) => {
        rejectTurn = reject;
      })) as never);
    await user.click(sendButton());
    await waitFor(() => expect(composer()).toBeDisabled());
    chip('model').focus();
    rejectTurn(apiError(409, 'CONVERSATION_BUSY'));
    await screen.findByText(tr('appChat.transportErrors.conversationBusy'));
    await waitFor(() => expect(composer()).toBeEnabled());
    expect(chip('model')).toHaveFocus();
  });

  it('is translated in Spanish and differs from the retired-model error', async () => {
    await sendBusy('es');
    expect(
      await screen.findByText('Esta conversación sigue respondiendo a un mensaje anterior. Espera a que termine e inténtalo de nuevo. Tu mensaje se ha conservado en el cuadro de texto.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(tr('appChat.notices.serviceRetired'))).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/appChat\.transportErrors/);
  });
});
