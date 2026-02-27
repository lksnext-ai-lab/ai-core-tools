import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { apiService } from '../services/api';
import MessageContent from '../components/playground/MessageContent';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import AttachedFilesPanel from '../components/playground/AttachedFilesPanel';
import type { PanelFile } from '../components/playground/AttachedFilesPanel';


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
  const [isSending, setIsSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Persistent files (server-side, scoped to this conversation)
  const [persistentFiles, setPersistentFiles] = useState<any[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);

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

  // Load persistent files whenever the conversation changes
  useEffect(() => {
    if (!numericId || isNaN(numericId)) return;
    const loadFiles = async () => {
      try {
        const response = await apiService.listMarketplaceFiles(numericId);
        setPersistentFiles(response.files || []);
      } catch {
        setPersistentFiles([]);
      }
    };
    loadFiles();
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
    if (!trimmed && persistentFiles.length === 0) return;
    if (isSending) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: trimmed || `[${persistentFiles.length} file(s) attached]`,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputMessage('');
    setIsSending(true);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const fileRefs = persistentFiles.length > 0
        ? persistentFiles.map((f) => f.file_id)
        : undefined;
      const response = await apiService.sendMarketplaceMessage(
        numericId,
        trimmed,
        fileRefs,
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
  }, [inputMessage, persistentFiles, isSending, numericId]);

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

  // File handling — upload to server so files persist across navigation
  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files ? Array.from(e.target.files) : [];
      e.target.value = '';
      if (files.length === 0) return;

      setIsLoadingFiles(true);
      for (const file of files) {
        try {
          await apiService.uploadMarketplaceFile(numericId, file);
        } catch (err) {
          console.error(`Error uploading file ${file.name}:`, err);
        }
      }
      try {
        const response = await apiService.listMarketplaceFiles(numericId);
        setPersistentFiles(response.files || []);
      } catch {
        // keep existing list
      } finally {
        setIsLoadingFiles(false);
      }
    },
    [numericId],
  );

  const handleDownloadFile = useCallback(
    async (fileId: string) => {
      try {
        const url = await apiService.getMarketplaceFileDownloadUrl(numericId, fileId);
        window.open(url, '_blank');
      } catch (error) {
        console.error('Error getting download URL:', error);
      }
    },
    [numericId],
  );

  const handleRemoveFile = useCallback(
    async (fileId: string) => {
      try {
        await apiService.removeMarketplaceFile(numericId, fileId);
        const response = await apiService.listMarketplaceFiles(numericId);
        setPersistentFiles(response.files || []);
      } catch (err) {
        console.error(`Error removing file ${fileId}:`, err);
      }
    },
    [numericId],
  );

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

  const panelFiles: PanelFile[] = persistentFiles.map((f) => ({
    id: f.file_id,
    filename: f.filename,
    file_type: f.file_type,
    processing_status: f.processing_status,
    file_size_display: f.file_size_display,
    has_extractable_content: f.has_extractable_content,
    content_preview: f.content_preview,
  }));

  return (
    <div className="flex h-[calc(100vh-8rem)]">
      {/* Chat column */}
      <div className="flex-1 flex flex-col min-w-0">

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
            disabled={isSending || (!inputMessage.trim() && persistentFiles.length === 0)}
            className="flex-shrink-0 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      </div>

      </div> {/* end chat column */}

      {/* Attached Files Panel */}
      <div className="border-l">
        <AttachedFilesPanel
          files={panelFiles}
          isLoading={isLoadingFiles}
          onRemoveFile={handleRemoveFile}
          onDownloadFile={handleDownloadFile}
        />
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
