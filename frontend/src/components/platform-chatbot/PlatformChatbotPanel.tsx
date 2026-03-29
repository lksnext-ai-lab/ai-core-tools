import React, { useRef, useState, useEffect } from 'react';
import { X, RotateCcw, Send } from 'lucide-react';
import { usePlatformChatbot } from '../../contexts/PlatformChatbotContext';
import { apiService } from '../../services/api';
import MessageContent from '../playground/MessageContent';
import StreamingMessage from '../playground/StreamingMessage';
import type { StreamEvent } from '../../types/streaming';

interface PlatformChatbotPanelProps {
  agentName: string | null;
  onClose: () => void;
  onNewConversation: () => void;
}

const PlatformChatbotPanel: React.FC<PlatformChatbotPanelProps> = ({
  agentName,
  onClose,
  onNewConversation,
}) => {
  const { messages, addMessage, sessionId } = usePlatformChatbot();
  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text || isSending) return;

    // Append user message
    addMessage({ role: 'user', content: text, timestamp: Date.now() });
    setInputText('');
    setIsSending(true);
    setStreamingContent('');
    setIsStreaming(true);

    abortControllerRef.current = new AbortController();
    let accumulated = '';

    try {
      await apiService.streamPlatformChatbotMessage(text, sessionId, {
        signal: abortControllerRef.current.signal,
        onEvent: (event: StreamEvent) => {
          if (event.type === 'token') {
            const token = (event.data as { content?: string }).content || '';
            accumulated += token;
            setStreamingContent(accumulated);
          } else if (event.type === 'done') {
            const response = (event.data as { response?: string }).response;
            const finalContent = response || accumulated;
            setIsStreaming(false);
            setStreamingContent('');
            addMessage({ role: 'assistant', content: finalContent, timestamp: Date.now() });
          } else if (event.type === 'error') {
            const errMsg = (event.data as { message?: string }).message || 'Something went wrong.';
            setIsStreaming(false);
            setStreamingContent('');
            addMessage({
              role: 'assistant',
              content: `Sorry, something went wrong. ${errMsg}`,
              timestamp: Date.now(),
            });
          }
        },
      });
    } catch (err: unknown) {
      setIsStreaming(false);
      setStreamingContent('');
      // Don't add error message if the request was aborted intentionally
      if (err instanceof Error && err.name !== 'AbortError') {
        addMessage({
          role: 'assistant',
          content: 'Sorry, something went wrong. Please try again.',
          timestamp: Date.now(),
        });
      }
    } finally {
      setIsSending(false);
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewConversation = () => {
    // Abort any in-progress stream
    abortControllerRef.current?.abort();
    setStreamingContent('');
    setIsStreaming(false);
    setIsSending(false);
    onNewConversation();
  };

  return (
    <div className="fixed bottom-20 right-4 z-50 w-96 h-[600px] flex flex-col rounded-xl shadow-2xl border bg-background overflow-hidden transition-all duration-300">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/50">
        <span className="font-semibold text-sm truncate">
          {agentName || 'AI Assistant'}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleNewConversation}
            className="text-xs px-2 py-1 rounded border hover:bg-muted transition-colors"
            title="New conversation"
          >
            <RotateCcw size={12} className="inline mr-1" />
            New
          </button>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-muted transition-colors"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !isStreaming && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Hi! How can I help you today?
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-foreground'
              }`}
            >
              {msg.role === 'assistant' ? (
                <MessageContent content={msg.content} />
              ) : (
                <span className="whitespace-pre-wrap">{msg.content}</span>
              )}
            </div>
          </div>
        ))}

        {isStreaming && (
          <StreamingMessage
            content={streamingContent}
            isStreaming={isStreaming}
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="flex gap-2 p-3 border-t">
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          rows={1}
          disabled={isSending}
          className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
          style={{ minHeight: '38px', maxHeight: '120px' }}
        />
        <button
          onClick={handleSend}
          disabled={isSending || !inputText.trim()}
          className="shrink-0 p-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 transition-opacity"
          aria-label="Send"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
};

export default PlatformChatbotPanel;
