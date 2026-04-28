import React, { useState, useRef, useEffect, useCallback } from 'react';
import { apiService } from '../../services/api';
import { useStreamingChat } from '../../hooks/useStreamingChat';
import MessageContent from './MessageContent';
import StreamingMessage from './StreamingMessage';
import SearchFilters from './SearchFilters';
import type { SearchFilterMetadataField } from './SearchFilters';
import AttachedFilesPanel from './AttachedFilesPanel';
import type { PanelFile } from './AttachedFilesPanel';

interface Message {
  id: string;
  type: 'user' | 'agent' | 'error';
  content: string;
  timestamp: Date;
  files?: string[];
}

/** Shape returned by the API for each history message. */
interface RawHistoryMessage {
  role: string;
  content: string;
}

/** Shape returned by the API for each attached/persistent file. */
interface RawAttachedFile {
  file_id: string;
  filename: string;
  file_type?: string;
  processing_status?: string;
  file_size_display?: string;
  has_extractable_content?: boolean;
  content_preview?: string;
}

interface ChatInterfaceProps {
  appId: number;
  agentId: number;
  agentName: string;
  conversationId?: number | null;
  onConversationCreated?: (conversationId: number) => void;
  onMessageSent?: () => void;
  metadataFields?: SearchFilterMetadataField[];
  vectorDbType?: string;
}

function ChatInterface({
  appId,
  agentId,
  agentName,
  conversationId,
  onConversationCreated,
  onMessageSent,
  metadataFields,
  vectorDbType,
}: Readonly<ChatInterfaceProps>) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [persistentFiles, setPersistentFiles] = useState<RawAttachedFile[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isFilterExpanded, setIsFilterExpanded] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(
    conversationId || null
  );
  const [filterMetadata, setFilterMetadata] = useState<Record<string, unknown> | undefined>(
    undefined
  );
  const [filtersKey, setFiltersKey] = useState(0);
  /** UI-only state to render the floating "scroll to bottom" button. Behaviour
   *  is driven by refs to avoid scroll-handler re-renders racing the streaming flush. */
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  /** Tracks the ID of the message just committed from streaming — skips entrance animation */
  const lastStreamedMsgIdRef = useRef<string | null>(null);
  /** True while the user has manually scrolled away from the bottom. Pauses auto-scroll
   *  during streaming so the wheel/touch input is respected. Resets on send or on reaching bottom. */
  const userScrolledUpRef = useRef(false);
  const lastScrollTopRef = useRef(0);
  const filterPanelId = `metadata-filters-${agentId}`;

  const { streamingContent, activeTools, thinkingMessage, isStreaming, sendMessage, abortStream } =
    useStreamingChat(appId, agentId);

  // Hold streaming content visible briefly after isStreaming flips to false,
  // so the transition to the final committed message is seamless.
  const [holdStreamingContent, setHoldStreamingContent] = useState(false);
  const showStreaming = isStreaming || holdStreamingContent;

  // ─── Scroll helpers ──────────────────────────────────────────────────────────

  /** Scroll the messages container to its bottom. Uses scrollTo on the container
   *  itself (not scrollIntoView on a child) so the scroll never propagates to
   *  ancestor scroll containers — critical now that <main> is scrollable. */
  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior });
  }, []);

  /** Reset the scroll-up lock — used when sending a new message or clicking the FAB. */
  const resetScrollLock = useCallback(() => {
    userScrolledUpRef.current = false;
    setShowScrollToBottom(false);
  }, []);

  // Track scroll direction with refs so streaming flushes never race the state update.
  // The FAB visibility uses a state but only updates when the boolean actually flips.
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const threshold = 80;
    lastScrollTopRef.current = container.scrollTop;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const atBottom = scrollHeight - scrollTop - clientHeight < threshold;
      const scrolledUp = scrollTop < lastScrollTopRef.current;
      lastScrollTopRef.current = scrollTop;

      if (atBottom) {
        if (userScrolledUpRef.current) {
          userScrolledUpRef.current = false;
          setShowScrollToBottom(false);
        }
        return;
      }

      if (scrolledUp && !userScrolledUpRef.current) {
        userScrolledUpRef.current = true;
        setShowScrollToBottom(true);
      }
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Auto-scroll when new messages arrive (only if user has not scrolled up)
  useEffect(() => {
    if (!userScrolledUpRef.current) {
      scrollToBottom();
    }
  }, [messages, scrollToBottom]);

  // Auto-scroll while streaming — driven by ref so wheel events win the race
  useEffect(() => {
    if (isStreaming && !userScrolledUpRef.current) {
      scrollToBottom('instant');
    }
  }, [streamingContent, isStreaming, scrollToBottom]);

  // ─── Conversation / file loading ─────────────────────────────────────────────

  useEffect(() => {
    setCurrentConversationId(conversationId || null);
  }, [conversationId]);

  useEffect(() => {
    const loadConversationHistory = async () => {
      try {
        setIsLoadingHistory(true);

        if (currentConversationId) {
          const response = await apiService.getConversationWithHistory(currentConversationId);

          if (response.messages && response.messages.length > 0) {
            const loadedMessages: Message[] = response.messages.map(
              (msg: RawHistoryMessage, index: number) => ({
                id: `history-${index}`,
                type: msg.role === 'user' ? 'user' : 'agent',
                content: msg.content,
                timestamp: new Date(),
              })
            );
            setMessages(loadedMessages);
          } else {
            setMessages([]);
          }
        } else {
          const response = await apiService.getConversationHistory(appId, agentId);

          if (response.messages && response.messages.length > 0) {
            const loadedMessages: Message[] = response.messages.map(
              (msg: RawHistoryMessage, index: number) => ({
                id: `history-${index}`,
                type: msg.role === 'user' ? 'user' : 'agent',
                content: msg.content,
                timestamp: new Date(),
              })
            );
            setMessages(loadedMessages);
          } else {
            setMessages([]);
          }
        }
      } catch (error) {
        console.error('Error loading conversation history:', error);
        setMessages([]);
      } finally {
        setIsLoadingHistory(false);
      }
    };

    const loadPersistentFiles = async () => {
      try {
        const response = await apiService.listAttachedFiles(appId, agentId, currentConversationId);
        setPersistentFiles(response.files || []);
      } catch (error) {
        console.error('Error loading persistent files:', error);
        setPersistentFiles([]);
      }
    };

    loadConversationHistory();
    loadPersistentFiles();
  }, [appId, agentId, currentConversationId]);

  useEffect(() => {
    if ((!metadataFields || metadataFields.length === 0) && filterMetadata !== undefined) {
      setFilterMetadata(undefined);
      setFiltersKey((prev) => prev + 1);
    }
  }, [metadataFields, filterMetadata]);

  // ─── Message sending ─────────────────────────────────────────────────────────

  const handleSendMessage = async () => {
    if (!inputMessage.trim() && persistentFiles.length === 0) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputMessage,
      timestamp: new Date(),
      files: persistentFiles.map((f) => f.filename),
    };

    setMessages((prev) => [...prev, userMsg]);
    const messageText = inputMessage;
    setInputMessage('');
    // Force scroll to bottom so the user sees the streaming response
    resetScrollLock();
    setTimeout(() => scrollToBottom('instant'), 50);

    try {
      const hasFilters =
        filterMetadata !== undefined && Object.keys(filterMetadata).length > 0;
      const searchParams = hasFilters ? filterMetadata : undefined;

      // Hold streaming content visible while we commit the final message
      setHoldStreamingContent(true);

      const result = await sendMessage(messageText, {
        conversationId: currentConversationId,
        searchParams,
      });

      const rawResponse = result.response || '';
      const responseContent: string =
        typeof rawResponse === 'object'
          ? JSON.stringify(rawResponse, null, 2)
          : rawResponse;

      const agentMsgId = (Date.now() + 1).toString();
      lastStreamedMsgIdRef.current = agentMsgId;
      const agentMsg: Message = {
        id: agentMsgId,
        type: 'agent',
        content: responseContent,
        timestamp: new Date(),
      };
      // Commit the message and release the streaming hold in the same batch
      setMessages((prev) => [...prev, agentMsg]);
      setHoldStreamingContent(false);

      if (result.conversationId && !currentConversationId) {
        setCurrentConversationId(result.conversationId);
        onConversationCreated?.(result.conversationId);
      }

      await refreshFileList(result.conversationId || currentConversationId);
      onMessageSent?.();
    } catch (error) {
      setHoldStreamingContent(false);
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        type: 'error',
        content: error instanceof Error ? error.message : 'An error occurred',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    }
  };

  // ─── Reset ───────────────────────────────────────────────────────────────────

  const handleResetConversation = async () => {
    try {
      await apiService.resetAgentConversation(appId, agentId);
      setMessages([]);
      setPersistentFiles([]);
      setFilterMetadata(undefined);
      setFiltersKey((prev) => prev + 1);
    } catch (error) {
      console.error('Error resetting conversation:', error);
    }
  };

  // ─── File upload ─────────────────────────────────────────────────────────────

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    setIsLoadingFiles(true);

    let targetConversationId = currentConversationId;

    if (!targetConversationId) {
      try {
        const convResponse = await apiService.createConversation(agentId);
        targetConversationId = convResponse.conversation_id;
        setCurrentConversationId(targetConversationId);
        if (onConversationCreated && targetConversationId) {
          onConversationCreated(targetConversationId);
        }
      } catch (convError) {
        console.error('Error creating conversation for file upload:', convError);
        setIsLoadingFiles(false);
        event.target.value = '';
        return;
      }
    }

    for (const file of files) {
      try {
        await apiService.uploadFileForChat(appId, agentId, file, targetConversationId);
      } catch (error) {
        console.error(`Error uploading file ${file.name}:`, error);
      }
    }

    try {
      const response = await apiService.listAttachedFiles(
        appId,
        agentId,
        targetConversationId
      );
      setPersistentFiles(response.files || []);
    } catch (error) {
      console.error('Error reloading persistent files:', error);
    } finally {
      setIsLoadingFiles(false);
    }

    event.target.value = '';
  };

  const refreshFileList = async (convId: number | null) => {
    if (!convId) return;
    try {
      const filesResponse = await apiService.listAttachedFiles(appId, agentId, convId);
      setPersistentFiles(filesResponse.files || []);
    } catch {
      // Non-critical
    }
  };

  // ─── File helpers ─────────────────────────────────────────────────────────────

  const resolveFileUrl = useCallback(
    (fileId: string): Promise<string> =>
      apiService.getFileDownloadUrl(appId, agentId, fileId, currentConversationId),
    [appId, agentId, currentConversationId]
  );

  const handleDownloadFile = async (fileId: string) => {
    try {
      const url = await resolveFileUrl(fileId);
      window.open(url, '_blank');
    } catch (error) {
      console.error('Error getting download URL:', error);
    }
  };

  const handleRemovePersistentFile = async (fileId: string) => {
    try {
      await apiService.removeAttachedFile(appId, agentId, fileId, currentConversationId);
      const response = await apiService.listAttachedFiles(
        appId,
        agentId,
        currentConversationId
      );
      setPersistentFiles(response.files || []);
    } catch (error) {
      console.error(`Error removing file ${fileId}:`, error);
    }
  };

  // ─── Misc handlers ────────────────────────────────────────────────────────────

  const handleFilterMetadataChange = useCallback(
    (metadata: Record<string, unknown> | undefined) => {
      setFilterMetadata(metadata);
    },
    []
  );

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const panelFiles: PanelFile[] = persistentFiles.map((f) => ({
    id: f.file_id,
    filename: f.filename,
    file_type: f.file_type,
    processing_status: f.processing_status,
    file_size_display: f.file_size_display,
    has_extractable_content: f.has_extractable_content,
    content_preview: f.content_preview,
  }));

  const canSend = !isStreaming && (inputMessage.trim().length > 0 || persistentFiles.length > 0);

  // ─── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Metadata Filters Section */}
      {metadataFields && metadataFields.length > 0 && (
        <div className="pg-glass rounded-xl overflow-hidden">
          <button
            type="button"
            className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-white/30 dark:hover:bg-gray-700/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-colors"
            onClick={() => setIsFilterExpanded((prev) => !prev)}
            aria-expanded={isFilterExpanded}
            aria-controls={filterPanelId}
          >
            <span className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              <svg
                className="w-4 h-4 text-indigo-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
                />
              </svg>
              Filter by Metadata
            </span>
            <svg
              className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${
                isFilterExpanded ? 'rotate-180' : ''
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>

          <div
            id={filterPanelId}
            className={`border-t border-white/20 dark:border-gray-700/30 px-4 py-3 bg-white/20 dark:bg-gray-800/20 ${
              isFilterExpanded ? '' : 'hidden'
            }`}
          >
            <SearchFilters
              key={filtersKey}
              metadataFields={metadataFields}
              dbType={vectorDbType?.toUpperCase()}
              disabled={isStreaming}
              onFilterMetadataChange={handleFilterMetadataChange}
            />
          </div>
        </div>
      )}

      {/* Chat Interface + File Panel */}
      <div className="flex gap-4 items-start">
        {/* Chat card */}
        <div className="flex-1 pg-glass rounded-2xl flex flex-col h-[calc(100vh-20rem)] min-h-[480px]">
          {/* Reset button — subtle, top-right corner */}
          <div className="flex justify-end px-4 pt-3 pb-1">
            <button
              type="button"
              onClick={handleResetConversation}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg
                         text-gray-500 dark:text-gray-400
                         hover:text-red-600 dark:hover:text-red-400
                         hover:bg-red-50 dark:hover:bg-red-900/20
                         border border-transparent hover:border-red-200 dark:hover:border-red-800/40
                         transition-all duration-150"
            >
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Reset
            </button>
          </div>

          {/* Messages container */}
          <div
            ref={messagesContainerRef}
            className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-2 space-y-3
                       bg-gradient-to-b from-gray-50/50 to-white/30
                       dark:from-gray-900/50 dark:to-gray-800/30
                       scroll-smooth"
          >
            {isLoadingHistory ? (
              <div className="flex justify-center items-center h-full">
                <div className="flex flex-col items-center gap-2 text-gray-400 dark:text-gray-500">
                  <div className="animate-spin rounded-full h-6 w-6 border-2 border-indigo-300 border-t-transparent" />
                  <span className="text-sm">Loading conversation...</span>
                </div>
              </div>
            ) : (
              <>
                {messages.length === 0 && !showStreaming && (
                  <div className="flex flex-col items-center justify-center h-full gap-3 text-center py-12">
                    <div className="w-12 h-12 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
                      <svg
                        className="w-6 h-6 text-indigo-500"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1.5}
                          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                        />
                      </svg>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-600 dark:text-gray-300">
                        Start a conversation with {agentName}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                        Type a message below to begin
                      </p>
                    </div>
                  </div>
                )}

                {messages.map((message) => {
                  const isUser = message.type === 'user';
                  const isError = message.type === 'error';

                  if (isUser) {
                    return (
                      <div
                        key={message.id}
                        className="flex justify-end animate-slide-in-right"
                      >
                        <div className="max-w-[85%] lg:max-w-[75%]">
                          <div className="pg-bubble-user">
                            <MessageContent
                              content={message.content}
                              resolveFileUrl={resolveFileUrl}
                            />
                            {message.files && message.files.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-gray-200 dark:border-gray-600">
                                {message.files.map((filename) => (
                                  <span
                                    key={filename}
                                    className="inline-flex items-center gap-1 text-xs bg-gray-200/60 dark:bg-gray-600/60 text-gray-600 dark:text-gray-300 rounded-full px-2 py-0.5"
                                  >
                                    <svg
                                      className="w-3 h-3"
                                      fill="none"
                                      stroke="currentColor"
                                      viewBox="0 0 24 24"
                                      aria-hidden="true"
                                    >
                                      <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={2}
                                        d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
                                      />
                                    </svg>
                                    {filename}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="text-right mt-1">
                            <span className="text-xs text-gray-400 dark:text-gray-500">
                              {message.timestamp.toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  if (isError) {
                    return (
                      <div
                        key={message.id}
                        className="flex justify-start animate-slide-in-left"
                      >
                        <div className="max-w-[85%] lg:max-w-[75%]">
                          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700/40 text-red-700 dark:text-red-300 rounded-2xl rounded-bl-sm px-4 py-3">
                            <div className="flex items-center gap-2 mb-1">
                              <svg
                                className="w-4 h-4 shrink-0"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                                aria-hidden="true"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                                />
                              </svg>
                              <span className="text-xs font-semibold uppercase tracking-wide">
                                Error
                              </span>
                            </div>
                            <p className="text-sm">{message.content}</p>
                          </div>
                          <div className="mt-1">
                            <span className="text-xs text-gray-400 dark:text-gray-500">
                              {message.timestamp.toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  // Agent message — skip entrance animation for the message just committed from streaming
                  const wasStreamed = message.id === lastStreamedMsgIdRef.current;
                  return (
                    <div
                      key={message.id}
                      className={`flex justify-start ${wasStreamed ? '' : 'animate-slide-in-left'}`}
                    >
                      <div className="max-w-[90%] lg:max-w-[80%]">
                        <div className="pg-bubble-agent text-gray-800 dark:text-gray-100">
                          <MessageContent
                            content={message.content}
                            resolveFileUrl={resolveFileUrl}
                          />
                        </div>
                        <div className="mt-1">
                          <span className="text-xs text-gray-400 dark:text-gray-500">
                            {message.timestamp.toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Streaming state — single component handles thinking + tools + content.
                    showStreaming stays true briefly after isStreaming flips to false,
                    keeping content visible until the final message is committed. */}
                {showStreaming && (
                  <StreamingMessage
                    content={streamingContent}
                    isStreaming={isStreaming}
                    activeTools={activeTools}
                    thinkingMessage={thinkingMessage}
                  />
                )}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Scroll-to-bottom FAB */}
          {showScrollToBottom && (
            <div className="relative h-0 pointer-events-none">
              <button
                type="button"
                onClick={() => {
                  resetScrollLock();
                  scrollToBottom();
                }}
                className="pg-scroll-fab pointer-events-auto"
                aria-label="Scroll to bottom"
              >
                <svg
                  className="w-4 h-4 text-gray-600 dark:text-gray-300"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </button>
            </div>
          )}

          {/* Input area */}
          <div className="px-4 pb-4 pt-3 border-t border-white/20 dark:border-gray-700/30">
            <div className="pg-glass rounded-xl px-3 py-2.5 flex items-end gap-2">
              {/* File attach button */}
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={handleFileUpload}
                  className="hidden"
                  id="file-upload"
                  accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.doc,.docx"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isStreaming}
                  className="p-1.5 rounded-lg text-gray-400 dark:text-gray-500
                             hover:text-indigo-600 dark:hover:text-indigo-400
                             hover:bg-indigo-50 dark:hover:bg-indigo-900/20
                             disabled:opacity-40 disabled:cursor-not-allowed
                             transition-all duration-150"
                  title="Attach file"
                  aria-label="Attach file"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
                    />
                  </svg>
                </button>
              </div>

              {/* Textarea */}
              <textarea
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Message ${agentName}...`}
                disabled={isStreaming}
                className="flex-1 bg-transparent border-none outline-none resize-none
                           text-sm text-gray-800 dark:text-gray-100
                           placeholder:text-gray-400 dark:placeholder:text-gray-500
                           disabled:opacity-50
                           max-h-40 input-login"
                rows={1}
                style={{ minHeight: '1.5rem' }}
                onInput={(e) => {
                  // Auto-resize textarea
                  const target = e.target as HTMLTextAreaElement;
                  target.style.height = 'auto';
                  target.style.height = `${Math.min(target.scrollHeight, 160)}px`;
                }}
              />

              {/* Send / Abort button */}
              {isStreaming ? (
                <button
                  type="button"
                  onClick={abortStream}
                  className="p-2 rounded-xl bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400
                             hover:bg-red-200 dark:hover:bg-red-900/50 transition-all duration-150
                             active:scale-95 shrink-0"
                  aria-label="Stop generating"
                  title="Stop generating"
                >
                  <svg
                    className="w-4 h-4"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSendMessage}
                  disabled={!canSend}
                  className="pg-btn-send shrink-0 !p-2"
                  aria-label="Send message"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                    />
                  </svg>
                </button>
              )}
            </div>

            {/* Hint text */}
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5 px-1">
              Press Enter to send, Shift+Enter for new line
            </p>
          </div>
        </div>

        {/* Attached Files Panel */}
        <AttachedFilesPanel
          files={panelFiles}
          isLoading={isLoadingFiles}
          onRemoveFile={handleRemovePersistentFile}
          onDownloadFile={handleDownloadFile}
        />
      </div>
    </div>
  );
}

export default ChatInterface;
