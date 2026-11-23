import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import i18n from '../../src/i18n';
import { apiError, apiMock, setupChatApi } from './apiMock';
import { chip, composer, renderAppChat, sendButton, tr, waitForChat } from './testUtils';

async function ready() {
  const view = renderAppChat();
  await waitForChat();
  await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Alpha|Alfa/));
  await waitFor(() => expect(composer()).toBeEnabled());
  return view;
}

const STEP_LIMIT = { message: 'fixed backend text', code: 'step_limit_reached' };

describe('Chat: the agent runs out of steps', () => {
  it('first turn (SSE): shows the translated error once, keeps the message and the new conversation, and the next message continues it', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await user.type(composer(), 'do the long task');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));

    stream.turns[0].metadata(99);
    stream.turns[0].emit({ type: 'error', data: STEP_LIMIT } as never);
    stream.turns[0].close();

    const message = tr('appChat.transportErrors.stepLimitReached');
    const alert = (await screen.findByText(message)).closest('[role="alert"]') as HTMLElement;
    expect(screen.getAllByText(message)).toHaveLength(1);
    expect(alert).toBeInTheDocument();
    // The failed user message stays, and the composer is usable again.
    expect(screen.getByText('do the long task')).toBeInTheDocument();
    await waitFor(() => expect(composer()).toBeEnabled());
    await waitFor(() => expect(composer()).toHaveFocus());
    // The conversation was kept: the URL moved to it and the list is refreshed.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/apps/7/chat/99'));
    await waitFor(() => expect(apiMock.listAppChatConversations).toHaveBeenCalledTimes(2));

    await user.type(composer(), 'continue');
    await waitFor(() => expect(sendButton()).toBeEnabled());
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(2));
    expect(stream.turns[1].request.conversationId).toBe(99);
    expect(stream.turns[1].request.message).toBe('continue');
  });

  it('HTTP 422 STEP_LIMIT_REACHED shows the same text and does not touch the model notice', async () => {
    setupChatApi();
    const { user } = await ready();
    await user.type(composer(), 'task');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(apiError(422, 'STEP_LIMIT_REACHED'));
    await user.click(sendButton());
    expect(await screen.findByText(tr('appChat.transportErrors.stepLimitReached'))).toBeInTheDocument();
    expect(screen.queryByText(tr('appChat.notices.serviceRetired'))).not.toBeInTheDocument();
    await waitFor(() => expect(composer()).toBeEnabled());
  });

  it('SSE conversation_busy gives the message back to the composer', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await user.type(composer(), 'my message');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    stream.turns[0].emit({ type: 'error', data: { message: 'busy', code: 'conversation_busy' } } as never);
    stream.turns[0].close();
    expect(await screen.findByText(tr('appChat.transportErrors.conversationBusy'))).toBeInTheDocument();
    await waitFor(() => expect(composer()).toHaveValue('my message'));
  });

  it('is announced in Spanish, with the wording of the other Chat texts', async () => {
    await i18n.changeLanguage('es');
    const stream = setupChatApi();
    const { user } = await ready();
    await user.type(composer(), 'tarea larga');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    stream.turns[0].metadata(99);
    stream.turns[0].emit({ type: 'error', data: STEP_LIMIT } as never);
    stream.turns[0].close();
    const text = await screen.findByText(/El asistente se quedó sin pasos antes de terminar/);
    expect(text).toHaveTextContent('escribe «continúa» para que siga');
    expect(within(text.closest('[role="alert"]') as HTMLElement).queryByText(/fichero/)).toBeNull();
  });
});

describe('Chat: too many files in one message', () => {
  it('shows the translated error and gives the message back to the composer', async () => {
    const stream = setupChatApi();
    const { user } = await ready();
    await user.type(composer(), 'with many files');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(apiError(422, 'TOO_MANY_FILES'));
    await user.click(sendButton());
    expect(await screen.findByText(tr('appChat.transportErrors.tooManyFiles'))).toBeInTheDocument();
    await waitFor(() => expect(composer()).toHaveValue('with many files'));
    expect(screen.queryByText(tr('appChat.notices.serviceRetired'))).not.toBeInTheDocument();
    expect(stream.turns).toHaveLength(0);
  });

  it('is translated in Spanish', async () => {
    await i18n.changeLanguage('es');
    setupChatApi();
    const { user } = await ready();
    await user.type(composer(), 'muchos archivos');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(apiError(422, 'TOO_MANY_FILES'));
    await user.click(sendButton());
    expect(await screen.findByText('Demasiados archivos en un mensaje. Envía menos archivos cada vez.')).toBeInTheDocument();
    await waitFor(() => expect(composer()).toHaveValue('muchos archivos'));
  });
});

