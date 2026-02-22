import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { apiService } from '../services/api';
import MessageContent from '../components/playground/MessageContent';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';

interface ChatMessage {
  readonly id: string;
  readonly type: 'user' | 'agent' | 'error';
  readonly content: string;
  readonly timestamp: Date;
}

/**
 * Marketplace chat page — simplified consumer-focused chat experience.
 * URL: /marketplace/chat/:conversationId
 */
export default function MarketplaceChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const numericId = Number(conversationId);

  // Conversation & agent state
  const [agentId, setAgentId] = useState<number | null>(null);
  const [agentName, setAgentName] = useState('Agent');
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);

  // Messages
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Load conversation history
  useEffect(() => {
    if (!numericId || isNaN(numericId)) {
      setError('Invalid conversation ID');
      setLoadingHistory(false);
      return;
    }

    const loadHistory = async () => {
      setLoadingHistory(true);
      setError(null);
      try {
        const data = await apiService.getMarketplaceConversationHistory(numericId);
        setAgentId(data.agent_id);
        setConversationTitle(data.title);

        // Try to get agent display name from marketplace conversations
        try {
          const convData = await apiService.getMarketplaceConversations(100, 0);
          const match = convData.conversations.find(
            (c) => c.conversation_id === numericId,
          );
          if (match) {
            setAgentName(match.agent_display_name);
          }
        } catch {
          // Non-critical — keep default name
        }

        if (data.messages && data.messages.length > 0) {
          const loaded: ChatMessage[] = data.messages.map(
            (msg: { role: string; content: string }, idx: number) => ({
              id: `history-${idx}`,
              type: msg.role === 'user' ? 'user' : 'agent',
              content: msg.content,
              timestamp: new Date(),
            }),
          );
          setMessages(loaded);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to load conversation';
        setError(msg);
      } finally {
        setLoadingHistory(false);
      }
    };

    loadHistory();
  }, [numericId]);

  // Auto-resize textarea
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInputMessage(e.target.value);
      const el = e.target;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    },
    [],
  );

  // Send message
  const handleSend = useCallback(async () => {
    const trimmed = inputMessage.trim();
    if (!trimmed && selectedFiles.length === 0) return;
    if (isSending) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: trimmed || `[${selectedFiles.length} file(s) attached]`,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputMessage('');
    setSelectedFiles([]);
    setIsSending(true);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const response = await apiService.sendMarketplaceMessage(
        numericId,
        trimmed,
        selectedFiles.length > 0 ? selectedFiles : undefined,
      );

      let responseContent = response.response || 'No response received';
      if (typeof responseContent === 'object') {
        responseContent = JSON.stringify(responseContent, null, 2);
      }

      const agentMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        type: 'agent',
        content: responseContent,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, agentMsg]);
    } catch (err) {
      const errMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        type: 'error',
        content:
          err instanceof Error ? err.message : 'Failed to send message. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsSending(false);
    }
  }, [inputMessage, selectedFiles, isSending, numericId]);

  // Handle Enter key
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  // File handling
  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        setSelectedFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
      }
      // Reset input so same file can be re-selected
      e.target.value = '';
    },
    [],
  );

  const removeFile = useCallback((index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // New chat with same agent
  const handleNewChat = useCallback(async () => {
    if (!agentId) return;
    try {
      const conv = await apiService.createMarketplaceConversation(agentId);
      navigate(`/marketplace/chat/${conv.conversation_id ?? conv.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create conversation');
    }
  }, [agentId, navigate]);

  // Loading state
  if (loadingHistory) {
    return <LoadingState message="Loading conversation..." />;
  }

  // Error state (fatal)
  if (error && messages.length === 0) {
    return (
      <div className="space-y-4">
        <ErrorState error={error} onRetry={() => window.location.reload()} />
        <div className="text-center">
          <Link
            to="/marketplace"
            className="text-sm text-blue-600 hover:text-blue-800 underline"
          >
            ← Back to Marketplace
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Top bar */}
      <div className="flex items-center justify-between border-b bg-white px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-2xl" aria-hidden="true">🤖</span>
          <div>
            <h2 className="text-sm font-semibold text-gray-900">{agentName}</h2>
            <p className="text-xs text-gray-500">
              {conversationTitle || 'New conversation'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {agentId && (
            <button
              type="button"
              onClick={handleNewChat}
              className="text-sm px-3 py-1.5 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              New Chat
            </button>
          )}
          {agentId && (
            <Link
              to={`/marketplace/agents/${agentId}`}
              className="text-sm px-3 py-1.5 text-gray-600 hover:text-gray-800"
            >
              Agent Details
            </Link>
          )}
        </div>
      </div>

      {/* Chat messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <span className="text-4xl block mb-3" aria-hidden="true">💬</span>
            <p className="text-sm">Send a message to start chatting with this agent.</p>
          </div>
        )}

        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}

        {isSending && (
          <div className="flex items-start gap-3">
            <span className="text-lg flex-shrink-0" aria-hidden="true">🤖</span>
            <div className="bg-gray-100 rounded-lg px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600" />
                Thinking...
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* File chips */}
      {selectedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 px-4 py-2 border-t bg-gray-50">
          {selectedFiles.map((file, idx) => (
            <span
              key={`${file.name}-${idx}`}
              className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded-full"
            >
              📎 {file.name}
              <button
                type="button"
                onClick={() => removeFile(idx)}
                className="ml-1 text-blue-600 hover:text-blue-900"
                aria-label={`Remove ${file.name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="border-t bg-white px-4 py-3 flex-shrink-0">
        <div className="flex items-end gap-2">
          {/* File upload button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex-shrink-0 p-2 text-gray-400 hover:text-gray-600 transition-colors"
            title="Attach file"
          >
            📎
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />

          {/* Message input */}
          <textarea
            ref={textareaRef}
            value={inputMessage}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (Shift+Enter for new line)"
            rows={1}
            className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />

          {/* Send button */}
          <button
            type="button"
            onClick={handleSend}
            disabled={isSending || (!inputMessage.trim() && selectedFiles.length === 0)}
            className="flex-shrink-0 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

/* ========== Sub-components ========== */

interface ChatBubbleProps {
  readonly message: ChatMessage;
}

function ChatBubble({ message }: ChatBubbleProps) {
  if (message.type === 'user') {
    return (
      <div className="flex items-start gap-3 justify-end">
        <div className="bg-blue-600 text-white rounded-lg px-4 py-3 max-w-[75%]">
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  if (message.type === 'error') {
    return (
      <div className="flex items-start gap-3">
        <span className="text-lg flex-shrink-0" aria-hidden="true">⚠️</span>
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 max-w-[75%]">
          <p className="text-sm text-red-700">{message.content}</p>
        </div>
      </div>
    );
  }

  // Agent message
  return (
    <div className="flex items-start gap-3">
      <span className="text-lg flex-shrink-0" aria-hidden="true">🤖</span>
      <div className="bg-gray-100 rounded-lg px-4 py-3 max-w-[75%]">
        <MessageContent content={message.content} />
      </div>
    </div>
  );
}
