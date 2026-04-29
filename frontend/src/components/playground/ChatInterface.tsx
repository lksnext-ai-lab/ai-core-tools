import React, { useState, useRef, useEffect, useCallback } from 'react';
import { apiService } from '../../services/api';
import { useStreamingChat } from '../../hooks/useStreamingChat';
import MessageContent from './MessageContent';
import StreamingMessage from './StreamingMessage';
import SearchFilters from './SearchFilters';
import type { SearchFilterMetadataField } from './SearchFilters';
import AttachedFilesPanel from './AttachedFilesPanel';
import type { PanelFile } from './AttachedFilesPanel';
import MediaUploadModal from './MediaUploadModal';
import VideoPlayer from './VideoPlayer';
import type { VideoTimestamp } from './VideoPlayer';

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
  onConversationReset?: () => void;
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
  onConversationReset,
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

  // Media upload state
  const [showMediaUploadModal, setShowMediaUploadModal] = useState(false);
  const [mediaConversationId, setMediaConversationId] = useState<number | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [playgroundMedia, setPlaygroundMedia] = useState<Array<{ media_id: number; name: string; status: string; source_type: string; media_type: string }>>([]);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  const playgroundStream = useCallback(
    (message: string, opts: Parameters<typeof apiService.chatWithAgentStream>[3]) =>
      apiService.chatWithAgentStream(appId, agentId, message, opts),
    [appId, agentId],
  );

  const { streamingContent, activeTools, thinkingMessage, isStreaming, sendMessage, abortStream } =
    useStreamingChat(playgroundStream);

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
    if (!conversationId) {
      setCurrentSessionId(null);
    }
  }, [conversationId]);

  useEffect(() => {
    const loadConversationHistory = async () => {
      try {
        setIsLoadingHistory(true);

        if (currentConversationId) {
          const response = await apiService.getConversationWithHistory(currentConversationId);

          if (response.session_id) {
            setCurrentSessionId(response.session_id);
          }

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

    // Load playground media if session exists
    if (currentSessionId) {
      apiService.listPlaygroundMedia(appId, agentId, currentSessionId)
        .then((media) => setPlaygroundMedia(Array.isArray(media) ? media : []))
        .catch(() => setPlaygroundMedia([]));
    } else {
      setPlaygroundMedia([]);
    }
  }, [appId, agentId, currentConversationId, currentSessionId]);

  // Poll for media processing status updates
  // Uses a ref-based approach so the interval is NOT recreated on every state change.
  useEffect(() => {
    const hasProcessing = playgroundMedia.some(
      (m) => m.status !== 'ready' && m.status !== 'error'
    );

    if (hasProcessing && currentSessionId && !pollingRef.current) {
      // Start polling only when there is processing media and no interval is active
      pollingRef.current = setInterval(async () => {
        try {
          const media = await apiService.listPlaygroundMedia(appId, agentId, currentSessionId);
          const list = Array.isArray(media) ? media : [];
          setPlaygroundMedia(list);
          // Stop polling if all done
          if (list.every((m: { status: string }) => m.status === 'ready' || m.status === 'error')) {
            if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
          }
        } catch {
          // keep polling — transient network errors should not kill the status display
        }
      }, 3000);
    } else if ((!hasProcessing || !currentSessionId) && pollingRef.current) {
      // All media finished or session gone — stop polling
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    return () => {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    };
  }, [playgroundMedia, appId, agentId, currentSessionId]);

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
      if (result.sessionId && !currentSessionId) {
        setCurrentSessionId(result.sessionId);
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
      await apiService.resetAgentConversation(appId, agentId, currentConversationId);
      setMessages([]);
      setPersistentFiles([]);
      setPlaygroundMedia([]);
      setMediaConversationId(null);
      setCurrentSessionId(null);
      setFilterMetadata(undefined);
      setFiltersKey((prev) => prev + 1);
      onConversationReset?.();
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
        if (convResponse.session_id) {
          setCurrentSessionId(convResponse.session_id);
        }
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
    // Handle media item removal
    if (fileId.startsWith('media_')) {
      await handleDeletePlaygroundMedia();
      return;
    }
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

  const handleMediaButtonClick = async () => {
    // Ensure conversation exists before opening media upload modal
    let convId = currentConversationId;
    if (!convId) {
      try {
        const convResponse = await apiService.createConversation(agentId);
        convId = convResponse.conversation_id;
        setCurrentConversationId(convId);
        setCurrentSessionId(convResponse.session_id);
        if (onConversationCreated && convId) {
          onConversationCreated(convId);
        }
      } catch (error) {
        console.error('Error creating conversation for media upload:', error);
        return;
      }
    }
    setMediaConversationId(convId ?? null);
    setShowMediaUploadModal(true);
  };

  const handleMediaUploadComplete = async () => {
    // Refresh playground media list after upload
    if (!currentSessionId) return;

    const fetchMedia = async () => {
      const media = await apiService.listPlaygroundMedia(appId, agentId, currentSessionId);
      return Array.isArray(media) ? media : [];
    };

    try {
      let list = await fetchMedia();
      // Retry once after a brief delay if the list is empty (DB commit timing)
      if (list.length === 0) {
        await new Promise((r) => setTimeout(r, 1000));
        list = await fetchMedia();
      }
      setPlaygroundMedia(list);
    } catch (error) {
      console.error('Error loading playground media:', error);
    }
  };

  const handleDeletePlaygroundMedia = async () => {
    if (!currentSessionId) return;
    try {
      await apiService.deletePlaygroundMedia(appId, agentId, currentSessionId);
      setPlaygroundMedia([]);
      // Revoke blob URL so the player stops
      if (videoBlobUrlRef.current) {
        URL.revokeObjectURL(videoBlobUrlRef.current);
        videoBlobUrlRef.current = null;
      }
      setVideoBlobUrl(null);
    } catch (error) {
      console.error('Error deleting playground media:', error);
    }
  };

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

  const panelFiles: PanelFile[] = [
    ...persistentFiles.map((f) => ({
      id: f.file_id,
      filename: f.filename,
      file_type: f.file_type,
      processing_status: f.processing_status,
      file_size_display: f.file_size_display,
      has_extractable_content: f.has_extractable_content,
      content_preview: f.content_preview,
    })),
    ...playgroundMedia.map((m) => ({
      id: `media_${m.media_id}`,
      filename: m.name,
      file_type: 'media' as const,
      processing_status: m.status,
    })),
  ];

  const canSend = !isStreaming && (inputMessage.trim().length > 0 || persistentFiles.length > 0);

  // ─── Video timestamp parsing ──────────────────────────────────────────────────

  /**
   * Parse timestamp patterns from agent response text.
   * Matches: [02:05 - 03:00], [02:05-03:00], [02:05], [1:02:05 - 1:03:00]
   */
  const parseTimestamps = (text: string): VideoTimestamp[] => {
    if (typeof text !== 'string') return [];
    // Match range patterns: [02:05 - 03:00] or [02:05-03:00]
    const rangeRegex = /\[(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}:\d{2}(?::\d{2})?)\]/g;
    // Match single timestamp patterns: [02:05]
    const singleRegex = /\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g;

    const results: VideoTimestamp[] = [];
    const seen = new Set<string>();

    const toSeconds = (t: string) => {
      const parts = t.split(':').map(Number);
      if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
      return parts[0] * 60 + parts[1];
    };

    // First pass: ranges
    let match: RegExpExecArray | null;
    while ((match = rangeRegex.exec(text)) !== null) {
      const startStr = match[1];
      const endStr = match[2];
      const key = `${startStr}-${endStr}`;
      if (seen.has(key)) continue;
      seen.add(key);
      // Also mark individual timestamps as seen so single-pass doesn't duplicate
      seen.add(startStr);
      seen.add(endStr);

      results.push({
        start_time: toSeconds(startStr),
        end_time: toSeconds(endStr),
        text_preview: '',
        is_agent_cited: true,
      });
    }

    // Second pass: single timestamps not already part of a range
    while ((match = singleRegex.exec(text)) !== null) {
      const ts = match[1];
      if (seen.has(ts)) continue;
      seen.add(ts);
      const secs = toSeconds(ts);

      results.push({
        start_time: secs,
        end_time: secs + 30, // Default 30s window for single timestamps
        text_preview: '',
        is_agent_cited: true,
      });
    }

    // Sort by start_time
    results.sort((a, b) => a.start_time - b.start_time);
    return results;
  };

  // Fetch video blob with auth and create object URL for the <video> element
  const readyVideoMedia = playgroundMedia.find((m) => m.status === 'ready');
  const [videoBlobUrl, setVideoBlobUrl] = useState<string | null>(null);
  const videoBlobUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!readyVideoMedia || !currentSessionId) {
      // Revoke previous blob URL when media is removed or conversation changes
      if (videoBlobUrlRef.current) {
        URL.revokeObjectURL(videoBlobUrlRef.current);
        videoBlobUrlRef.current = null;
      }
      setVideoBlobUrl(null);
      return;
    }

    let cancelled = false;
    apiService
      .fetchPlaygroundMediaBlob(appId, agentId, readyVideoMedia.media_id, currentSessionId)
      .then((blob) => {
        if (cancelled) return;
        // Revoke previous URL if any
        if (videoBlobUrlRef.current) {
          URL.revokeObjectURL(videoBlobUrlRef.current);
        }
        const url = URL.createObjectURL(blob);
        videoBlobUrlRef.current = url;
        setVideoBlobUrl(url);
      })
      .catch((err) => {
        console.error('Failed to fetch media blob:', err);
        if (!cancelled) setVideoBlobUrl(null);
      });

    return () => {
      cancelled = true;
    };
  }, [readyVideoMedia?.media_id, currentSessionId, appId, agentId]);

  // Clean up blob URL on unmount
  useEffect(() => {
    return () => {
      if (videoBlobUrlRef.current) {
        URL.revokeObjectURL(videoBlobUrlRef.current);
      }
    };
  }, []);

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
                  const msgTimestamps = videoBlobUrl ? parseTimestamps(String(message.content)) : [];
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
                        {msgTimestamps.length > 0 && videoBlobUrl && (
                          <VideoPlayer
                            videoUrl={videoBlobUrl}
                            timestamps={msgTimestamps}
                            title={readyVideoMedia?.name}
                            isAudio={readyVideoMedia?.media_type === 'audio'}
                          />
                        )}
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

              {/* Media attach button */}
              <button
                type="button"
                onClick={handleMediaButtonClick}
                disabled={isStreaming}
                className="p-1.5 rounded-lg text-gray-400 dark:text-gray-500
                           hover:text-purple-600 dark:hover:text-purple-400
                           hover:bg-purple-50 dark:hover:bg-purple-900/20
                           disabled:opacity-40 disabled:cursor-not-allowed
                           transition-all duration-150"
                title="Attach media (video/audio)"
                aria-label="Attach media"
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
                    d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
              </button>

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

      {/* Media Upload Modal */}
      {mediaConversationId && currentSessionId && (
        <MediaUploadModal
          isOpen={showMediaUploadModal}
          onClose={() => setShowMediaUploadModal(false)}
          appId={appId}
          agentId={agentId}
          sessionId={currentSessionId}
          onUploadComplete={handleMediaUploadComplete}
        />
      )}
    </div>
  );
}

export default ChatInterface;
