import { useState } from 'react';
import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ChatInterface from '../../src/components/playground/ChatInterface';
import type { StreamEvent } from '../../src/types/streaming';
import { apiMock } from './apiMock';
import { renderWithProviders, tr } from './testUtils';

const AGENT_ID = 3;

interface PlaygroundTurn {
  readonly message: string;
  readonly conversationId?: number | null;
  emit(event: StreamEvent): void;
  finish(): void;
}

/** The agent playground endpoints `createAgentPlaygroundTransport` wraps. */
function setupPlayground() {
  const turns: PlaygroundTurn[] = [];
  apiMock.getAgentChatFilters.mockResolvedValue({ filters: [] } as never);
  apiMock.listAttachedFiles.mockResolvedValue({ files: [] } as never);
  apiMock.listPlaygroundMedia.mockResolvedValue([] as never);
  apiMock.getConversationHistory.mockResolvedValue({
    messages: [
      { role: 'user', content: 'earlier question' },
      { role: 'assistant', content: 'earlier answer' },
    ],
  } as never);
  apiMock.getConversationWithHistory.mockImplementation((async (conversationId: number) => ({
    session_id: `session-${conversationId}`,
    // Conversation 55 is the one the first turn creates: its stored history already holds that turn's answer.
    messages:
      conversationId === 55
        ? [
            { role: 'assistant', content: 'streamed answer' },
            { role: 'assistant', content: 'history of 55' },
          ]
        : [{ role: 'assistant', content: `history of ${conversationId}` }],
    pending_approval: null,
  })) as never);
  apiMock.chatWithAgentStream.mockImplementation(((
    _appId: number,
    _agentId: number,
    message: string,
    options: { conversationId?: number | null; onEvent: (event: StreamEvent) => void },
  ) =>
    new Promise<void>((resolve) => {
      turns.push({
        message,
        conversationId: options.conversationId,
        emit: options.onEvent,
        finish: resolve,
      });
    })) as never);
  return turns;
}

function Playground({ initialConversationId = null }: Readonly<{ initialConversationId?: number | null }>) {
  const [conversationId, setConversationId] = useState<number | null>(initialConversationId);
  return (
    <>
      <button type="button" onClick={() => setConversationId(12)}>
        open-12
      </button>
      <output data-testid="conversation-id">{String(conversationId)}</output>
      <ChatInterface
        appId={7}
        agentId={AGENT_ID}
        agentName="Helper"
        conversationId={conversationId}
        onConversationCreated={setConversationId}
      />
    </>
  );
}

const composerName = () => tr('agentPlayground.chat.messagePlaceholder', { agent: 'Helper' });

describe('ChatInterface with the agent playground transport', () => {
  it('loads the default history, sends, streams and commits the answer', async () => {
    const turns = setupPlayground();
    const { user } = renderWithProviders(<Playground />);

    expect(await screen.findByText('earlier answer')).toBeInTheDocument();
    expect(apiMock.getConversationHistory).toHaveBeenCalledWith(7, AGENT_ID);

    await user.type(screen.getByRole('textbox', { name: composerName() }), 'new question');
    await user.click(screen.getByRole('button', { name: tr('agentPlayground.chat.sendMessage') }));

    await waitFor(() => expect(turns).toHaveLength(1));
    expect(turns[0].message).toBe('new question');
    expect(apiMock.chatWithAgentStream.mock.calls[0].slice(0, 3)).toEqual([7, AGENT_ID, 'new question']);
    expect(screen.getByText('new question')).toBeInTheDocument();

    turns[0].emit({ type: 'token', data: { content: 'streamed ' } });
    expect(await screen.findByText(/streamed/)).toBeInTheDocument();
    turns[0].emit({ type: 'done', data: { response: 'streamed answer', conversation_id: 55 } });
    turns[0].finish();

    // The answer is on screen whether it is the committed message or the reloaded history of conversation 55.
    await waitFor(() => expect(apiMock.getConversationWithHistory).toHaveBeenCalledWith(55));
    expect(await screen.findByText('streamed answer')).toBeInTheDocument();
    // Playground has no per-turn badge.
    expect(screen.queryByRole('button', { name: /Details of/ })).not.toBeInTheDocument();
  });

  it('reloads the history of the new conversation after the first turn creates it (the Chat-only skip does not apply)', async () => {
    const turns = setupPlayground();
    const { user } = renderWithProviders(<Playground />);
    await screen.findByText('earlier answer');

    await user.type(screen.getByRole('textbox', { name: composerName() }), 'start');
    await user.click(screen.getByRole('button', { name: tr('agentPlayground.chat.sendMessage') }));
    await waitFor(() => expect(turns).toHaveLength(1));
    turns[0].emit({ type: 'metadata', data: { conversation_id: 55, session_id: 'session-55' } });
    turns[0].emit({ type: 'done', data: { response: 'first answer', conversation_id: 55 } });
    turns[0].finish();

    await waitFor(() => expect(screen.getByTestId('conversation-id')).toHaveTextContent('55'));
    // The playground reloads from the server (its session id comes from that reload); the Chat would not.
    await waitFor(() => expect(apiMock.getConversationWithHistory).toHaveBeenCalledWith(55));
    expect(await screen.findByText('history of 55')).toBeInTheDocument();
  });

  it('reloads the history when the conversation changes', async () => {
    setupPlayground();
    const { user } = renderWithProviders(<Playground />);
    await screen.findByText('earlier answer');

    await user.click(screen.getByRole('button', { name: 'open-12' }));

    expect(await screen.findByText('history of 12')).toBeInTheDocument();
    expect(apiMock.getConversationWithHistory).toHaveBeenCalledWith(12);
    expect(screen.queryByText('earlier answer')).not.toBeInTheDocument();
    expect(apiMock.listAttachedFiles).toHaveBeenLastCalledWith(7, AGENT_ID, 12);
  });
});
