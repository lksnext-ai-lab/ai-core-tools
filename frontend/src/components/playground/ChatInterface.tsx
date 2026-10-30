import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Bot, MessageCircle, RefreshCw, Square, Timer } from 'lucide-react';
import { apiService } from '../../services/api';
import { StreamingChatError, useStreamingChat, type StreamFnOptions } from '../../hooks/useStreamingChat';
import { formatDuration } from '../../utils/duration';
import MessageContent from './MessageContent';
import StreamingMessage from './StreamingMessage';
import SearchFilters from './SearchFilters';
import type { SearchFilterMetadataField } from './SearchFilters';
import AttachedFilesPanel from './AttachedFilesPanel';
import type { PanelFile } from './AttachedFilesPanel';
import BackgroundImage from '../ui/BackgroundImage';
import ToolHistoryPanel from './ToolHistoryPanel';
import MediaUploadModal from './MediaUploadModal';
import VideoPlayer from './VideoPlayer';
import HitlApprovalCard from './HitlApprovalCard';
import { useApprovalExpiryWatch } from '../../hooks/useApprovalExpiryWatch';
import type { HitlDecision } from '../../types/streaming';
import type { VideoTimestamp } from './VideoPlayer';
import { LoadingState } from '../ui/LoadingState';
import ButtonApp from '../ui/ButtonApp';

interface Message {
  id: string;
  type: 'user' | 'agent' | 'error';
  content: string;
  timestamp: Date;
  files?: string[];
  elapsedMs?: number;
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
  const { t } = useTranslation('common');
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
  const [playgroundMedia, setPlaygroundMedia] = useState<Array<{ media_id: number; name: string; status: string; source_type: string; media_type: string; error_message?: string | null }>>([]);
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

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const playgroundStream = useCallback(
    (message: string, opts: StreamFnOptions) => {
      if (opts.resume) {
        return apiService.decideApprovalStream(opts.resume.approvalId, opts.resume.decisions, {
          onEvent: opts.onEvent,
          signal: opts.signal,
        });
      }
      return apiService.chatWithAgentStream(appId, agentId, message, opts);
    },
    [appId, agentId],
  );

  const {
    streamingContent, activeTools, thinkingMessage, isStreaming, responseElapsedMs, sendMessage, abortStream,
    toolExecutionHistory, clearToolHistory, settleAwaitingTools, pendingApproval, setPendingApproval,
  } = useStreamingChat(playgroundStream);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [expiredApprovalId, setExpiredApprovalId] = useState<string | null>(null);
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  // While a person can still answer, a new message would discard the paused turn.
  const approvalBlocksInput =
    pendingApproval !== null && pendingApproval.status === 'pending' && pendingApproval.approval_id !== expiredApprovalId;

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
        setMessages([]);
        setPendingApproval(null);

        if (currentConversationId) {
          const response = await apiService.getConversationWithHistory(currentConversationId);

          if (response.session_id) {
            setCurrentSessionId(response.session_id);
          }
          // Restore an approval the conversation is still waiting for (e.g. after a reload).
          setPendingApproval(response.pending_approval ?? null);

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

    void loadConversationHistory();
    void loadPersistentFiles();

    // Load playground media if session exists
    if (currentSessionId) {
      apiService.listPlaygroundMedia(appId, agentId, currentSessionId)
        .then((media) => setPlaygroundMedia(Array.isArray(media) ? media : []))
        .catch(() => setPlaygroundMedia([]));
    } else {
      setPlaygroundMedia([]);
    }
  }, [appId, agentId, currentConversationId, currentSessionId, historyReloadKey]);

  useApprovalExpiryWatch(
    currentConversationId ? expiredApprovalId : null,
    useCallback(async () => {
      if (!currentConversationId) return null;
      const response = await apiService.getConversationWithHistory(currentConversationId);
      return response.pending_approval?.approval_id ?? null;
    }, [currentConversationId]),
    useCallback(() => {
      setExpiredApprovalId(null);
      setHistoryReloadKey((k) => k + 1);
    }, []),
  );

  // Poll for media processing status updates
  // Keep the interval alive across playgroundMedia updates by depending on a stable boolean.
  const playgroundMediaRef = useRef(playgroundMedia);
  const hasProcessingMediaForPolling = playgroundMedia.some(
    (m) => m.status !== 'ready' && m.status !== 'error'
  );

  useEffect(() => {
    playgroundMediaRef.current = playgroundMedia;
  }, [playgroundMedia]);

  useEffect(() => {
    if (!currentSessionId || !hasProcessingMediaForPolling) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }

    if (pollingRef.current) {
      return;
    }

    // Cap total polling so a media item stuck in a processing state (e.g. a
    // dead background task) does not poll forever: 3s interval × 200 = 10 min.
    const MAX_POLLS = 200;
    let polls = 0;

    // Start polling only when there is processing media and no interval is active
    pollingRef.current = setInterval(async () => {
      polls += 1;
      try {
        const media = await apiService.listPlaygroundMedia(appId, agentId, currentSessionId);
        const list = Array.isArray(media) ? media : [];
        playgroundMediaRef.current = list;
        setPlaygroundMedia(list);

        // Stop polling if all done or the max poll budget is exhausted
        const allDone = list.every(
          (m: { status: string }) => m.status === 'ready' || m.status === 'error'
        );
        if (allDone || polls >= MAX_POLLS) {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
        }
      } catch {
        // keep polling — transient network errors should not kill the status display
        if (polls >= MAX_POLLS && pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }
    }, 3000);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [appId, agentId, currentSessionId, hasProcessingMediaForPolling]);

  useEffect(() => {
    if ((!metadataFields || metadataFields.length === 0) && filterMetadata !== undefined) {
      setFilterMetadata(undefined);
      setFiltersKey((prev) => prev + 1);
    }
  }, [metadataFields, filterMetadata]);

  // ─── Message sending ─────────────────────────────────────────────────────────

  /** Commit a finished turn as an agent message (nothing to commit while it awaits approval). */
  const commitAgentResponse = (
    rawResponse: string | Record<string, unknown>,
    elapsedMs: number,
    awaitingApproval: boolean,
  ) => {
    const responseContent: string =
      typeof rawResponse === 'object' ? JSON.stringify(rawResponse, null, 2) : rawResponse || '';
    if (awaitingApproval && !responseContent.trim()) {
      setHoldStreamingContent(false);
      return;
    }
    const agentMsgId = (Date.now() + 1).toString();
    lastStreamedMsgIdRef.current = agentMsgId;
    const agentMsg: Message = {
      id: agentMsgId,
      type: 'agent',
      content: responseContent,
      timestamp: new Date(),
      elapsedMs,
    };
    // Commit the message and release the streaming hold in the same batch
    setMessages((prev) => [...prev, agentMsg]);
    setHoldStreamingContent(false);
  };

  const handleApprovalDecision = async (decisions: HitlDecision[]) => {
    const approval = pendingApproval;
    if (!currentConversationId || !approval) return;
    resetScrollLock();
    try {
      setHoldStreamingContent(true);
      const result = await sendMessage('', {
        conversationId: currentConversationId,
        resume: { approvalId: approval.approval_id, decisions },
      });
      commitAgentResponse(result.response, result.elapsedMs, result.pendingApproval !== null);
      await refreshFileList(currentConversationId);
      onMessageSent?.();
    } catch (error) {
      setHoldStreamingContent(false);
      // The decision was not applied: keep the request on screen so it can be answered again.
      setPendingApproval(approval);
      setMessages((prev) => [...prev, {
        id: (Date.now() + 1).toString(),
        type: 'error',
        content: error instanceof Error ? error.message : t('agentPlayground.chat.approvalCouldNotBeSent'),
        timestamp: new Date(),
      }]);
    }
  };

  const handleApprovalCancel = async () => {
    const approval = pendingApproval;
    if (!approval) return;
    setApprovalBusy(true);
    try {
      const result = await apiService.cancelApproval(approval.approval_id);
      settleAwaitingTools('cancelled');
      setPendingApproval(result.pending_approval);
      commitAgentResponse(result.response, 0, result.pending_approval !== null);
    } catch (error) {
      setMessages((prev) => [...prev, {
        id: (Date.now() + 1).toString(),
        type: 'error',
        content: error instanceof Error ? error.message : t('agentPlayground.chat.requestCouldNotBeCancelled'),
        timestamp: new Date(),
      }]);
    } finally {
      setApprovalBusy(false);
    }
  };

  const handleApprovalExpire = useCallback(() => {
    if (!pendingApproval) return;
    settleAwaitingTools('expired');
    setExpiredApprovalId(pendingApproval.approval_id);
  }, [pendingApproval, settleAwaitingTools]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() && persistentFiles.length === 0) return;
    // The server resolves an expired approval within this turn; reloading the history
    // mid-turn would drop the message being sent.
    setExpiredApprovalId(null);

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

      commitAgentResponse(result.response, result.elapsedMs, result.pendingApproval !== null);

      if (result.conversationId && !currentConversationId) {
        setCurrentConversationId(result.conversationId);
        onConversationCreated?.(result.conversationId);
      }
      if (result.sessionId && !currentSessionId) {
        setCurrentSessionId(result.sessionId);
      }

      await refreshFileList(result.conversationId || currentConversationId);
      onMessageSent?.();

      textareaRef.current?.focus();
    } catch (error) {
      setHoldStreamingContent(false);
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        type: 'error',
        content: error instanceof Error ? error.message : t('agentPlayground.chat.sendMessageFailed'),
        timestamp: new Date(),
        elapsedMs: error instanceof StreamingChatError ? error.elapsedMs : responseElapsedMs,
      };
      setMessages((prev) => [...prev, errorMsg]);
    }
  };

  useEffect(() => {
    if (!textareaRef.current) return;

    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${Math.min(
      textareaRef.current.scrollHeight,
      160
    )}px`;
  }, [inputMessage]);

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
      clearToolHistory();
      onConversationReset?.();
    } catch (error) {
      console.error('Error resetting conversation:', error);
    }
  };

  // ─── File upload ─────────────────────────────────────────────────────────────

  const uploadFiles = async (files: File[] | FileList) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    const existingNames = new Set(persistentFiles.map((file) => file.filename));
    const newFiles = fileArray.filter((file) => !existingNames.has(file.name));
    if (newFiles.length === 0) return;

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
        return;
      }
    }

    for (const file of newFiles) {
      try {
        await apiService.uploadFileForChat(appId, agentId, file, targetConversationId);
      } catch (error) {
        console.error(`Error uploading file ${file.name}:`, error);
      }
    }

    try {
      const response = await apiService.listAttachedFiles(appId, agentId, targetConversationId);
      setPersistentFiles(response.files || []);
    } catch (error) {
      console.error('Error reloading persistent files:', error);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    await uploadFiles(event.target.files ?? []);
    event.target.value = '';
  };

  const handlePaste = async (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const imageFiles = Array.from(event.clipboardData?.files ?? []).filter((file) =>
      file.type.startsWith('image/')
    );
    if (imageFiles.length === 0) return;
    event.preventDefault();
    await uploadFiles(imageFiles);
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
    // Media items are currently stored in a single playground media repo for the
    // session, so removing any individual media entry deletes all uploaded media.
    // Make that scope explicit to avoid a surprising destructive action.
    if (fileId.startsWith('media_')) {
      const confirmed = window.confirm(
        t('agentPlayground.chat.removePlaygroundMediaConfirm')
      );
      if (!confirmed) {
        return;
      }
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
        setCurrentSessionId(convResponse.session_id ?? null);
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
      if (canSend) void handleSendMessage();
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
      error_message: m.error_message ?? undefined,
    })),
  ];

  const hasMediaProcessing = playgroundMedia.some(
    (m) => m.status !== 'ready' && m.status !== 'error'
  );
  const canSend =
    !isStreaming && !hasMediaProcessing && !approvalBlocksInput
    && (inputMessage.trim().length > 0 || persistentFiles.length > 0);

  // ─── Video timestamp parsing ──────────────────────────────────────────────────

  /**
   * Parse timestamp patterns from agent response text.
   * Matches optional media label prefixes so timestamps can be tied to a
   * specific video/audio when several media are uploaded:
   *   [lesson.mp4 @ 02:05 - 03:00], [02:05 - 03:00], [02:05-03:00],
   *   [lesson.mp4 @ 02:05], [02:05], [1:02:05 - 1:03:00]
   */
  const parseTimestamps = (text: string): VideoTimestamp[] => {
    if (typeof text !== 'string') return [];
    // Optional label prefix "<name> @ " inside the bracket, then a time range.
    const rangeRegex = /\[(?:\s*([^[\]@]+?)\s*@\s*)?(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}:\d{2}(?::\d{2})?)\]/g;
    // Optional label prefix, then a single timestamp.
    const singleRegex = /\[(?:\s*([^[\]@]+?)\s*@\s*)?(\d{1,2}:\d{2}(?::\d{2})?)\]/g;

    const results: VideoTimestamp[] = [];
    const seen = new Set<string>();

    const toSeconds = (t: string) => {
      const parts = t.split(':').map(Number);
      if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
      return parts[0] * 60 + parts[1];
    };

    const normalizeLabel = (label?: string) => {
      const trimmed = label?.trim();
      return trimmed ? trimmed : undefined;
    };

    // First pass: ranges
    let match: RegExpExecArray | null;
    while ((match = rangeRegex.exec(text)) !== null) {
      const mediaLabel = normalizeLabel(match[1]);
      const startStr = match[2];
      const endStr = match[3];
      const key = `${mediaLabel ?? ''}|${startStr}-${endStr}`;
      if (seen.has(key)) continue;
      seen.add(key);

      results.push({
        start_time: toSeconds(startStr),
        end_time: toSeconds(endStr),
        text_preview: '',
        is_agent_cited: true,
        mediaLabel,
      });
    }

    // Second pass: single timestamps not already part of a range
    while ((match = singleRegex.exec(text)) !== null) {
      const mediaLabel = normalizeLabel(match[1]);
      const ts = match[2];
      const key = `${mediaLabel ?? ''}|${ts}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const secs = toSeconds(ts);

      results.push({
        start_time: secs,
        end_time: secs + 30, // Default 30s window for single timestamps
        text_preview: '',
        is_agent_cited: true,
        mediaLabel,
      });
    }

    // Sort by start_time
    results.sort((a, b) => a.start_time - b.start_time);
    return results;
  };

  /**
   * Associate parsed timestamps to a specific media so each VideoPlayer only
   * shows the moments the agent actually cited for that video/audio.
   * - With a single uploaded media, every cited timestamp belongs to it (the
   *   agent may omit the filename when there is no ambiguity).
   * - With multiple media, only timestamps explicitly labelled with this
   *   media's name are attributed to it; ambiguous/unlabelled ones are skipped.
   */
  const getTimestampsForMedia = (
    all: VideoTimestamp[],
    mediaName: string,
    readyCount: number,
  ): VideoTimestamp[] => {
    if (readyCount <= 1) return all;

    const name = mediaName.toLowerCase().trim();
    const nameNoExt = name.replace(/\.[^./\\]+$/, '');
    return all.filter((t) => {
      if (t.mediaLabel === undefined) return false;
      const label = t.mediaLabel.toLowerCase().trim();
      const labelNoExt = label.replace(/\.[^./\\]+$/, '');
      return label === name || label === nameNoExt || labelNoExt === nameNoExt || label.includes(name);
    });
  };

  /**
   * Remove the media-name prefix from timestamp citations for display, keeping
   * only the time portion. The raw text still carries the label so the players
   * can be associated to the right media, but the user sees plain timestamps:
   *   [lesson.mp4 @ 02:05 - 03:00] -> [02:05 - 03:00]
   *   [lesson.mp4 @ 02:05]         -> [02:05]
   */
  const stripTimestampLabels = (content: string | object): string | object => {
    if (typeof content !== 'string') return content;
    return content.replace(
      /\[\s*[^[\]@]+?\s*@\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[-–]\s*\d{1,2}:\d{2}(?::\d{2})?)?)\]/g,
      '[$1]',
    );
  };

  // Direct stream URLs for ready media so the <video>/<audio> element issues
  // HTTP Range requests for true seeking instead of downloading the whole file
  // into browser memory. Same-origin requests carry the session cookie.
  const readyVideoMedias = playgroundMedia.filter((m) => m.status === 'ready');
  const readyMediaIdsKey = readyVideoMedias.map((m) => m.media_id).join(',');

  const videoStreamUrls = useMemo<Record<number, string>>(() => {
    if (!currentSessionId) return {};
    return readyVideoMedias.reduce<Record<number, string>>((map, media) => {
      map[media.media_id] = apiService.getPlaygroundMediaStreamUrl(
        appId,
        agentId,
        media.media_id,
        currentSessionId,
      );
      return map;
    }, {});
  }, [readyMediaIdsKey, currentSessionId, appId, agentId]);

  // ─── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
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
              {t('agentPlayground.chat.filterByMetadata')}
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
        <div className="flex-1 min-w-0 bg-canvas dark:bg-canvas-dark flex flex-col h-[calc(100vh-20rem)] min-h-[480px] overflow-hidden">
          {/* Reset button — subtle, top-right corner */}
          <div className="flex justify-end px-6 pt-3 pb-1">
            <ButtonApp
              label={t('agentPlayground.chat.reset')}
              variant="secondary"
              size="compact"
              onClick={handleResetConversation}
              icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
            />
          </div>

          {/* Messages container */}
          <div
            ref={messagesContainerRef}
            className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-[26px] space-y-[22px]
                       bg-canvas dark:bg-canvas-dark
                       scroll-smooth"
          >
            {isLoadingHistory ? (
              <div className="flex justify-center items-center h-full">
                <LoadingState variant="section" message={t('agentPlayground.chat.loadingConversation')} />
              </div>
            ) : (
              <>
                {messages.length === 0 && !showStreaming && (
                  <div className="flex flex-col items-center justify-center h-full py-10 text-center animate-fade-in">
                    <BackgroundImage
                      icon={MessageCircle}
                      size={52}
                      iconSize={26}
                      variant="marron"
                      className="mb-5 rounded-xl"
                    />
                    <div className="space-y-2">
                      <p className="font-display text-[26px] font-normal tracking-tight text-fg dark:text-fg-dark">
                        {t('agentPlayground.chat.startChatting', { agent: agentName })}
                      </p>
                      <p className="text-[14.5px] text-fg-secondary dark:text-fg-secondary-dark max-w-[400px] mx-auto">
                        {t('agentPlayground.chat.starterPromptDescription')}
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
                        className="flex justify-end max-w-[760px] mx-auto animate-slide-in-right gap-4"
                      >
                        <BackgroundImage text={t('agentPlayground.chat.youLabel')} size={38} iconSize={18} variant="vacio" className="mt-0.5 border border-accent dark:border-accent-dark" />
                        <div className="max-w-[82%] min-w-0">
                          <div className="bg-bronze-bg dark:bg-bronze-bg-dark border border-bronze-border dark:border-bronze-border-dark rounded-md px-4 py-[13px] text-sm leading-relaxed text-fg dark:text-fg-dark">
                            <MessageContent
                              content={message.content}
                              resolveFileUrl={resolveFileUrl}
                            />
                            {message.files && message.files.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-bronze-border dark:border-bronze-border-dark">
                                {message.files.map((filename) => (
                                  <span
                                    key={filename}
                                    className="inline-flex items-center gap-1 text-xs bg-canvas dark:bg-canvas-dark text-fg-secondary  dark:text-fg-secondary-dark rounded-full px-2 py-0.5"
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
                            <span className="text-[11.5px] text-fg-faint dark:text-fg-faint-dark">
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
                        className="flex justify-start max-w-[760px] mx-auto animate-slide-in-left"
                      >
                        <div className="max-w-[82%] min-w-0">
                          <div className="bg-error-bg dark:bg-error-bg-dark border border-error-border dark:border-error-border-dark text-error dark:text-error-dark rounded-md px-4 py-[13px]">
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
                                {t('agentPlayground.chat.errorLabel')}
                              </span>
                            </div>
                            <p className="text-sm">{message.content}</p>
                          </div>
                          <div className="mt-1">
                            <span className="text-[11.5px] text-fg-faint dark:text-fg-faint-dark">
                              {message.timestamp.toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                            {message.elapsedMs !== undefined && (
                              <span className="ml-2 inline-flex items-center gap-1 text-[11.5px] tabular-nums text-fg-faint dark:text-fg-faint-dark">
                                <Timer className="h-3 w-3" aria-hidden="true" />
                                {formatDuration(message.elapsedMs)}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  }

                  // Agent message — skip entrance animation for the message just committed from streaming
                  const wasStreamed = message.id === lastStreamedMsgIdRef.current;
                  const msgTimestamps = readyVideoMedias.length > 0 ? parseTimestamps(String(message.content)) : [];
                  return (
                    <div
                      key={message.id}
                      className={`flex justify-start max-w-[760px] mx-auto ${wasStreamed ? '' : 'animate-slide-in-left'}`}
                    >
                      <div className="flex items-start gap-4 max-w-[82%] min-w-0">
                        <BackgroundImage icon={Bot} size={38} iconSize={18} variant="vacio" className="mt-0.5 border border-accent dark:border-accent-dark" />
                        <div className="min-w-0 flex-1">
                          <div className="bg-surface dark:bg-surface-dark border border-line dark:border-line-dark rounded-md px-4 py-[13px] text-sm leading-relaxed text-fg dark:text-fg-dark">
                            <MessageContent
                              content={stripTimestampLabels(message.content)}
                              resolveFileUrl={resolveFileUrl}
                            />
                          </div>
                          {msgTimestamps.length > 0 &&
                            readyVideoMedias.map((media) => {
                              const streamUrl = videoStreamUrls[media.media_id];
                              const mediaTimestamps = getTimestampsForMedia(
                                msgTimestamps,
                                media.name,
                                readyVideoMedias.length,
                              );
                              if (!streamUrl || mediaTimestamps.length === 0) return null;
                              return (
                                <VideoPlayer
                                  key={media.media_id}
                                  videoUrl={streamUrl}
                                  timestamps={mediaTimestamps}
                                  title={media.name}
                                  isAudio={media.media_type === 'audio'}
                                />
                              );
                            })}
                          <div className="mt-1">
                            <span className="text-[11.5px] text-fg-faint dark:text-fg-faint-dark">
                              {message.timestamp.toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                            {message.elapsedMs !== undefined && (
                              <span className="ml-2 inline-flex items-center gap-1 text-[11.5px] tabular-nums text-fg-faint dark:text-fg-faint-dark">
                                <Timer className="h-3 w-3" aria-hidden="true" />
                                {formatDuration(message.elapsedMs)}
                              </span>
                            )}
                          </div>
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
                    content={stripTimestampLabels(streamingContent) as string}
                    isStreaming={isStreaming}
                    elapsedMs={responseElapsedMs}
                    activeTools={activeTools}
                    thinkingMessage={thinkingMessage}
                  />
                )}
                {pendingApproval && !isStreaming && (
                  <HitlApprovalCard
                    approval={pendingApproval}
                    disabled={approvalBusy}
                    onDecide={(decisions) => void handleApprovalDecision(decisions)}
                    onCancel={() => void handleApprovalCancel()}
                    onExpire={handleApprovalExpire}
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
                aria-label={t('agentPlayground.chat.scrollToBottom')}
              >
                <svg
                  className="w-4 h-4 text-fg-secondary dark:text-fg-secondary-dark"
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
          <div className="w-full max-w-[808px] mx-auto px-4 pb-4 pt-3 flex-shrink-0">
            <div className="flex items-end gap-2 bg-surface dark:bg-surface-dark border-[1.5px] border-line dark:border-line-dark rounded-xl py-2 pr-2 pl-2.5 shadow-sm focus-within:border-accent dark:focus-within:border-accent-dark transition-colors duration-150">
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
                  className="w-9 h-9 flex items-center justify-center shrink-0 rounded-lg
                             text-fg-tertiary dark:text-fg-tertiary-dark
                             disabled:opacity-40 disabled:cursor-not-allowed
                             transition-colors duration-150"
                  title={t('agentPlayground.chat.attachFile')}
                  aria-label={t('agentPlayground.chat.attachFile')}
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
                className="w-[38px] h-[38px] flex items-center justify-center rounded-lg shrink-0
                           text-fg-tertiary dark:text-fg-tertiary-dark
                          disabled:opacity-40 disabled:cursor-not-allowed
                           transition-colors duration-150"
                title={t('agentPlayground.chat.attachMediaTitle')}
                aria-label={t('agentPlayground.chat.attachMedia')}
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
                ref={textareaRef}
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                placeholder={approvalBlocksInput
                  ? t('agentPlayground.chat.answerApprovalToContinue')
                  : t('agentPlayground.chat.messagePlaceholder', { agent: agentName })}
                disabled={isStreaming || approvalBlocksInput}
                className="flex-1 py-[9px] bg-transparent border-none outline-none resize-none
                           text-[14.5px] text-fg dark:text-fg-dark
                           placeholder:text-fg-tertiary dark:placeholder:text-fg-tertiary-dark
                           disabled:opacity-50
                           focus:outline-none focus:ring-0 focus:border-accent dark:focus:border-accent
                           max-h-40 input-login"
                rows={1}
                style={{ minHeight: '1.5rem' }}
              />

              {/* Send / Abort button */}
              {isStreaming ? (
                <button
                  type="button"
                  onClick={abortStream}
                  className="w-[38px] h-[38px] flex items-center justify-center rounded-lg shrink-0
                             bg-error-bg dark:bg-error-bg-dark border border-error-border dark:border-error-border-dark
                             text-error dark:text-error-dark
                             hover:border-error dark:hover:border-error-dark transition-colors duration-150"
                  aria-label={t('agentPlayground.chat.stopGenerating')}
                  title={t('agentPlayground.chat.stopGenerating')}
                >
                  <Square className="w-4 h-4" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSendMessage}
                  disabled={!canSend}
                  className="w-[38px] h-[38px] flex items-center justify-center rounded-lg shrink-0
                             bg-ink dark:bg-ink-dark text-ink-on dark:text-ink-on-dark
                             hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
                             transition-opacity duration-150"
                  aria-label={t('agentPlayground.chat.sendMessage')}
                >
                  <ArrowRight className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Hint text */}
            <p className="text-[11.5px] text-fg-faint dark:text-fg-faint-dark mt-[9px] text-center">
              {t('agentPlayground.chat.sendKeyboardHint')}
            </p>
          </div>
        </div>

        {/* Right column: attached files on top, tool activity below */}
        <div className="w-72 shrink-0 flex flex-col gap-3 h-full min-h-0 [&>*:first-child]:w-full [&>*:first-child]:h-auto [&>*:first-child]:max-h-[50%]">
          {/* Attached Files Panel */}
          <AttachedFilesPanel
            files={panelFiles}
            isLoading={isLoadingFiles}
            onRemoveFile={handleRemovePersistentFile}
            onDownloadFile={handleDownloadFile}
          />

          {/* Tool Execution History Panel */}
          <ToolHistoryPanel
            history={toolExecutionHistory}
            onClear={clearToolHistory}
          />
        </div>
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
