import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Clock, MessageCircle, Paperclip, Square, Timer, Bot } from 'lucide-react';
import { toast } from 'sonner';
import { apiService, ApiError } from '../services/api';
import MessageContent from '../components/playground/MessageContent';
import StreamingMessage from '../components/playground/StreamingMessage';
import AttachedFilesPanel from '../components/playground/AttachedFilesPanel';
import type { PanelFile } from '../components/playground/AttachedFilesPanel';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import BackgroundImage from '../components/ui/BackgroundImage';
import { SidePanel } from '../components/ui/SidePanel';
import { StreamingChatError, useStreamingChat, type StreamFnOptions } from '../hooks/useStreamingChat';
import { useApprovalExpiryWatch } from '../hooks/useApprovalExpiryWatch';
import HitlApprovalCard from '../components/playground/HitlApprovalCard';
import type { HitlDecision } from '../types/streaming';
import { formatDuration } from '../utils/duration';
import { errorMessage } from '../constants/messages';
import type { MarketplaceAgentDetail, MarketplaceConversation } from '../types/marketplace';

interface ChatMessage {
  readonly id: string;
  readonly type: 'user' | 'agent' | 'error';
  readonly content: string;
  readonly timestamp: Date;
  readonly elapsedMs?: number;
}

interface RawAttachedFile {
  readonly file_id: string;
  readonly filename: string;
  readonly file_type?: string;
  readonly processing_status?: string;
  readonly file_size_display?: string;
  readonly has_extractable_content?: boolean;
  readonly content_preview?: string;
}

interface QuotaInfo {
  readonly call_count: number;
  readonly quota: number;
  readonly is_exempt: boolean;
}

interface HistoryGroup {
  readonly label: string;
  readonly items: MarketplaceConversation[];
}

/** Buckets conversations (newest first) into Today / Yesterday / Previous 7 days / Older. */
function groupConversationsByDate(conversations: MarketplaceConversation[]): HistoryGroup[] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const today = startOfToday.getTime();
  const dayMs = 24 * 60 * 60 * 1000;
  const groups: HistoryGroup[] = [
    { label: 'Today', items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'Previous 7 days', items: [] },
    { label: 'Older', items: [] },
  ];
  const sorted = [...conversations].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
  for (const conv of sorted) {
    const time = new Date(conv.updated_at).getTime();
    if (time >= today) groups[0].items.push(conv);
    else if (time >= today - dayMs) groups[1].items.push(conv);
    else if (time >= today - 7 * dayMs) groups[2].items.push(conv);
    else groups[3].items.push(conv);
  }
  return groups.filter((g) => g.items.length > 0);
}

function formatHistoryTime(iso: string, isToday: boolean): string {
  const date = new Date(iso);
  return isToday
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/**
 * Marketplace chat page — consumer-facing chat with the same streaming UX
 * as the playground (`ChatInterface`). Uses `useStreamingChat` bound to the
 * marketplace SSE endpoint so tool/thinking pills, token streaming, abort
 * and scroll behaviour match exactly.
 */
export default function MarketplaceChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const numericId = Number(conversationId);

  const [agentId, setAgentId] = useState<number | null>(null);
  const [agentName, setAgentName] = useState('Agent');
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [starters, setStarters] = useState<{ id: number; prompt: string }[]>([]);
  const [agentDetail, setAgentDetail] = useState<MarketplaceAgentDetail | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [persistentFiles, setPersistentFiles] = useState<RawAttachedFile[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [quotaInfo, setQuotaInfo] = useState<QuotaInfo | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historySearch, setHistorySearch] = useState('');
  const [historyConversations, setHistoryConversations] = useState<MarketplaceConversation[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastStreamedMsgIdRef = useRef<string | null>(null);
  const userScrolledUpRef = useRef(false);
  const lastScrollTopRef = useRef(0);

  const isQuotaExceeded =
    quotaInfo !== null &&
    quotaInfo.quota > 0 &&
    !quotaInfo.is_exempt &&
    quotaInfo.call_count >= quotaInfo.quota;

  const marketplaceStream = useCallback(
    (message: string, opts: StreamFnOptions) => {
      if (opts.resume) {
        return apiService.decideApprovalStream(opts.resume.approvalId, opts.resume.decisions, {
          onEvent: opts.onEvent,
          signal: opts.signal,
        });
      }
      return apiService.chatMarketplaceStream(numericId, message, {
        files: opts.files,
        fileReferences: persistentFiles.length > 0 ? persistentFiles.map((f) => f.file_id) : undefined,
        onEvent: opts.onEvent,
        signal: opts.signal,
      });
    },
    [numericId, persistentFiles],
  );

  const {
    streamingContent, activeTools, thinkingMessage, isStreaming, responseElapsedMs, sendMessage, abortStream,
    pendingApproval, setPendingApproval, settleAwaitingTools,
  } = useStreamingChat(marketplaceStream);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [expiredApprovalId, setExpiredApprovalId] = useState<string | null>(null);
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  // While a person can still answer, a new message would discard the paused turn.
  const approvalBlocksInput =
    pendingApproval !== null && pendingApproval.status === 'pending' && pendingApproval.approval_id !== expiredApprovalId;

  useApprovalExpiryWatch(
    expiredApprovalId,
    useCallback(async () => {
      const data = await apiService.getMarketplaceConversationHistory(numericId);
      return (data.pending_approval?.approval_id as string | undefined) ?? null;
    }, [numericId]),
    useCallback(() => {
      setExpiredApprovalId(null);
      setHistoryReloadKey((k) => k + 1);
    }, []),
  );

  const [holdStreamingContent, setHoldStreamingContent] = useState(false);
  const showStreaming = isStreaming || holdStreamingContent;

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior });
  }, []);

  const resetScrollLock = useCallback(() => {
    userScrolledUpRef.current = false;
    setShowScrollToBottom(false);
  }, []);

  useEffect(() => {
    if (!textareaRef.current) return;

    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${Math.min(
      textareaRef.current.scrollHeight,
      160
    )}px`;
  }, [inputMessage]);

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

  useEffect(() => {
    if (!userScrolledUpRef.current) {
      scrollToBottom();
    }
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (isStreaming && !userScrolledUpRef.current) {
      scrollToBottom('instant');
    }
  }, [streamingContent, isStreaming, scrollToBottom]);

  const fetchQuotaInfo = useCallback(async () => {
    try {
      const data = await apiService.getMarketplaceQuotaUsage();
      setQuotaInfo(data);
    } catch {
      // Quota display is informational; failing silently is acceptable.
    }
  }, []);

  useEffect(() => {
    void fetchQuotaInfo();
  }, [fetchQuotaInfo]);

  useEffect(() => {
    if (!agentId) return;
    let isMounted = true;
    apiService
      .getMarketplaceAgentDetail(agentId)
      .then((detail) => {
        if (isMounted) {
          setAgentDetail(detail);
          setAgentName(detail.display_name);
        }
      })
      .catch(() => {
        // Agent details panel is informational; failing silently is acceptable.
      });
    return () => {
      isMounted = false;
    };
  }, [agentId]);

  useEffect(() => {
    if (!numericId || Number.isNaN(numericId)) {
      setHistoryError('Invalid conversation ID');
      setLoadingHistory(false);
      return;
    }

    let isMounted = true;

    const loadHistory = async () => {
      setLoadingHistory(true);
      setHistoryError(null);
      setMessages([]);
      try {
        const data = await apiService.getMarketplaceConversationHistory(numericId);
        if (!isMounted) return;
        setAgentId(data.agent_id);
        // Restore an approval the conversation is still waiting for (e.g. after a reload).
        setPendingApproval(data.pending_approval ?? null);
        setConversationTitle(data.title);

        try {
          const starters = await apiService.getAgentConversationStarters(data.agent_id);
          if (starters && starters.length > 0) {
            setStarters(starters.map((s) => ({ id: s.id, prompt: s.prompt })));
          }
        } catch {
          // Non-critical
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
        if (!isMounted) return;
        setHistoryError(errorMessage(err, 'Failed to load conversation'));
      } finally {
        if (isMounted) setLoadingHistory(false);
      }
    };

    void loadHistory();
    return () => {
      isMounted = false;
    };
  }, [numericId, historyReloadKey, setPendingApproval]);

  useEffect(() => {
    if (!numericId || Number.isNaN(numericId)) return;
    let isMounted = true;
    const loadFiles = async () => {
      try {
        const response = await apiService.listMarketplaceFiles(numericId);
        if (isMounted) setPersistentFiles(response.files || []);
      } catch {
        if (isMounted) setPersistentFiles([]);
      }
    };
    void loadFiles();
    return () => {
      isMounted = false;
    };
  }, [numericId]);

  useEffect(() => {
    if (!isStreaming && textareaRef.current && !isQuotaExceeded) {
      textareaRef.current.focus();
    }
  }, [isStreaming, isQuotaExceeded]);

  const refreshFileList = useCallback(async () => {
    try {
      const response = await apiService.listMarketplaceFiles(numericId);
      setPersistentFiles(response.files || []);
    } catch {
      // Non-critical
    }
  }, [numericId]);

  const handleStarterClick = useCallback((prompt: string) => {
    setInputMessage(prompt);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
      textareaRef.current.focus();
    }
  }, []);

  /** Commit a finished turn as an agent message (nothing to commit while it awaits approval). */
  const commitAgentResponse = useCallback(
    (rawResponse: string | Record<string, unknown>, elapsedMs: number, awaitingApproval: boolean) => {
      const responseContent: string =
        typeof rawResponse === 'object' ? JSON.stringify(rawResponse, null, 2) : rawResponse || '';
      if (awaitingApproval && !responseContent.trim()) {
        setHoldStreamingContent(false);
        return;
      }
      const agentMsgId = (Date.now() + 1).toString();
      lastStreamedMsgIdRef.current = agentMsgId;
      setMessages((prev) => [
        ...prev,
        { id: agentMsgId, type: 'agent', content: responseContent, timestamp: new Date(), elapsedMs },
      ]);
      setHoldStreamingContent(false);
    },
    [],
  );

  const pushError = useCallback((content: string) => {
    setMessages((prev) => [...prev, { id: (Date.now() + 1).toString(), type: 'error', content, timestamp: new Date() }]);
  }, []);

  const handleApprovalDecision = useCallback(async (decisions: HitlDecision[]) => {
    const approval = pendingApproval;
    if (!approval) return;
    resetScrollLock();
    try {
      setHoldStreamingContent(true);
      const result = await sendMessage('', {
        conversationId: numericId,
        resume: { approvalId: approval.approval_id, decisions },
      });
      commitAgentResponse(result.response, result.elapsedMs, result.pendingApproval !== null);
    } catch (err) {
      setHoldStreamingContent(false);
      // The decision was not applied: keep the request on screen so it can be answered again.
      setPendingApproval(approval);
      pushError(errorMessage(err, 'The approval could not be sent'));
    }
  }, [pendingApproval, resetScrollLock, sendMessage, numericId, commitAgentResponse, setPendingApproval, pushError]);

  const handleApprovalCancel = useCallback(async () => {
    const approval = pendingApproval;
    if (!approval) return;
    setApprovalBusy(true);
    try {
      const result = await apiService.cancelApproval(approval.approval_id);
      settleAwaitingTools('cancelled');
      setPendingApproval(result.pending_approval);
      commitAgentResponse(result.response, 0, result.pending_approval !== null);
    } catch (err) {
      pushError(errorMessage(err, 'The request could not be cancelled'));
    } finally {
      setApprovalBusy(false);
    }
  }, [pendingApproval, settleAwaitingTools, setPendingApproval, commitAgentResponse, pushError]);

  const handleApprovalExpire = useCallback(() => {
    if (!pendingApproval) return;
    settleAwaitingTools('expired');
    setExpiredApprovalId(pendingApproval.approval_id);
  }, [pendingApproval, settleAwaitingTools]);

  const handleSendMessage = useCallback(async () => {
    const trimmed = inputMessage.trim();
    if (!trimmed && persistentFiles.length === 0) return;
    if (isStreaming) return;
    if (isQuotaExceeded) return;
    if (approvalBlocksInput) return;
    // The server resolves an expired approval within this turn; reloading the history
    // mid-turn would drop the message being sent.
    setExpiredApprovalId(null);

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: trimmed || `[${persistentFiles.length} file(s) attached]`,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputMessage('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    resetScrollLock();
    setTimeout(() => scrollToBottom('instant'), 50);

    try {
      setHoldStreamingContent(true);
      const result = await sendMessage(trimmed, {
        conversationId: numericId,
      });

      commitAgentResponse(result.response, result.elapsedMs, result.pendingApproval !== null);

      void refreshFileList();
      void fetchQuotaInfo();
    } catch (err) {
      setHoldStreamingContent(false);
      const isQuotaError = err instanceof ApiError && err.status === 429;
      const content = isQuotaError
        ? 'Marketplace call quota exceeded. Your quota resets at the start of next month.'
        : errorMessage(err, 'Failed to send message. Please try again.');
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          type: 'error',
          content,
          timestamp: new Date(),
          elapsedMs: err instanceof StreamingChatError ? err.elapsedMs : responseElapsedMs,
        },
      ]);
      void fetchQuotaInfo();
    }
  }, [
    inputMessage,
    persistentFiles.length,
    isStreaming,
    isQuotaExceeded,
    approvalBlocksInput,
    sendMessage,
    numericId,
    resetScrollLock,
    scrollToBottom,
    refreshFileList,
    fetchQuotaInfo,
    commitAgentResponse,
  ]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSendMessage();
      }
    },
    [handleSendMessage],
  );

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files ? Array.from(e.target.files) : [];
      e.target.value = '';
      if (files.length === 0) return;

      setIsLoadingFiles(true);
      const failed: string[] = [];
      for (const file of files) {
        try {
          await apiService.uploadMarketplaceFile(numericId, file);
        } catch (err) {
          failed.push(file.name);
          console.error(`Error uploading file ${file.name}:`, err);
        }
      }
      await refreshFileList();
      setIsLoadingFiles(false);

      if (failed.length > 0) {
        toast.error(`Failed to upload: ${failed.join(', ')}`);
      }
    },
    [numericId, refreshFileList],
  );

  const resolveFileUrl = useCallback(
    (fileId: string): Promise<string> =>
      apiService.getMarketplaceFileDownloadUrl(numericId, fileId),
    [numericId],
  );

  const handleDownloadFile = useCallback(
    async (fileId: string) => {
      try {
        const url = await resolveFileUrl(fileId);
        window.open(url, '_blank');
      } catch (err) {
        toast.error(errorMessage(err, 'Failed to download file'));
      }
    },
    [resolveFileUrl],
  );

  const handleRemoveFile = useCallback(
    async (fileId: string) => {
      try {
        await apiService.removeMarketplaceFile(numericId, fileId);
        await refreshFileList();
      } catch (err) {
        toast.error(errorMessage(err, 'Failed to remove file'));
      }
    },
    [numericId, refreshFileList],
  );

  const handleNewChat = useCallback(async () => {
    if (!agentId) return;
    try {
      const conv = await apiService.createMarketplaceConversation(agentId);
      navigate(`/marketplace/chat/${conv.conversation_id ?? conv.id}`);
    } catch (err) {
      toast.error(errorMessage(err, 'Failed to create conversation'));
    }
  }, [agentId, navigate]);

  // Load this agent's conversations each time the history panel opens.
  useEffect(() => {
    if (!historyOpen || !agentId) return;
    let isMounted = true;
    setHistoryLoading(true);
    apiService
      .getMarketplaceConversations(100, 0)
      .then((data) => {
        if (isMounted) {
          setHistoryConversations(data.conversations.filter((c) => c.agent_id === agentId));
        }
      })
      .catch((err) => {
        if (isMounted) toast.error(errorMessage(err, 'Failed to load conversation history'));
      })
      .finally(() => {
        if (isMounted) setHistoryLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [historyOpen, agentId]);

  const closeHistory = useCallback(() => {
    setHistoryOpen(false);
    setHistorySearch('');
  }, []);

  const handleOpenConversation = useCallback(
    (id: number) => {
      closeHistory();
      if (id !== numericId) navigate(`/marketplace/chat/${id}`);
    },
    [closeHistory, navigate, numericId],
  );

  if (loadingHistory) {
    return <LoadingState message="Loading conversation..." />;
  }

  if (historyError && messages.length === 0) {
    return (
      <div className="space-y-4">
        <ErrorState error={historyError} onRetry={() => globalThis.location.reload()} />
        <div className="text-center">
          <Link
            to="/marketplace"
            className="text-sm text-blue-600 hover:text-blue-800 underline inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-4 h-4" /> Back to Marketplace
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

  const historyQuery = historySearch.trim().toLowerCase();
  const historyGroups = groupConversationsByDate(
    historyConversations.filter((c) =>
      `${c.title ?? ''} ${c.last_message ?? ''}`.toLowerCase().includes(historyQuery),
    ),
  );

  const canSend =
    !isStreaming && !isQuotaExceeded && !approvalBlocksInput
    && (inputMessage.trim().length > 0 || persistentFiles.length > 0);

  return (
    <div className="relative flex items-stretch h-full min-h-0">
      <SidePanel
        open={historyOpen}
        onClose={closeHistory}
        title="History"
        closeLabel="Close history"
        headerActions={
          <button
            type="button"
            onClick={() => {
              closeHistory();
              void handleNewChat();
            }}
            className="font-display text-[12.5px] px-[11px] py-[5px] rounded-md
                       border border-ink dark:border-ink-dark text-fg dark:text-fg-dark
                       hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors duration-150"
          >
            New
          </button>
        }
        toolbar={
          <input
            type="search"
            value={historySearch}
            onChange={(e) => setHistorySearch(e.target.value)}
            placeholder="Search conversations…"
            aria-label="Search conversations"
            className="w-full rounded-md px-[11px] py-2 text-[13px]
                       bg-surface dark:bg-surface-dark border border-line dark:border-line-dark
                       text-fg dark:text-fg-dark placeholder:text-fg-tertiary dark:placeholder:text-fg-tertiary-dark
                       focus:outline-none focus:border-accent dark:focus:border-accent-dark"
          />
        }
      >
        {historyLoading && historyConversations.length === 0 && (
          <p className="text-[13px] text-fg-tertiary dark:text-fg-tertiary-dark px-2.5 py-3.5">Loading…</p>
        )}
        {!historyLoading && historyGroups.length === 0 && (
          <p className="text-[13px] text-fg-tertiary dark:text-fg-tertiary-dark px-2.5 py-3.5">
            {historyQuery ? 'No conversations match your search.' : 'No previous conversations.'}
          </p>
        )}
        {historyGroups.map((group) => (
          <div key={group.label} className="mb-3.5">
            <div className="text-[11px] uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark px-2.5 pt-1.5 pb-1">
              {group.label}
            </div>
            {group.items.map((conv) => {
              const isCurrent = conv.conversation_id === numericId;
              return (
                <button
                  key={conv.conversation_id}
                  type="button"
                  onClick={() => handleOpenConversation(conv.conversation_id)}
                  aria-current={isCurrent ? 'page' : undefined}
                  className={`w-full text-left flex flex-col gap-[3px] rounded-md px-2.5 py-[9px]
                              hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors duration-150
                              ${isCurrent ? 'bg-surface-hover dark:bg-surface-hover-dark' : ''}`}
                >
                  <span className="flex items-baseline gap-2 w-full">
                    <span className="flex-1 min-w-0 truncate text-[13.5px] font-medium text-fg dark:text-fg-dark">
                      {conv.title || 'New conversation'}
                    </span>
                    <span className="flex-none text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark">
                      {formatHistoryTime(conv.updated_at, group.label === 'Today')}
                    </span>
                  </span>
                  {conv.last_message && (
                    <span className="truncate max-w-full text-[12.5px] leading-snug text-fg-tertiary dark:text-fg-tertiary-dark">
                      {conv.last_message}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </SidePanel>

      <div className="flex-1 min-w-0 bg-canvas dark:bg-canvas-dark flex flex-col h-full min-h-0">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-8 py-[18px] border-b border-line dark:border-line-dark flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <BackgroundImage icon={Bot} size={32} iconSize={17} variant="marron" />
            <div className="min-w-0">
              <h2 className="font-display text-lg font-normal tracking-tight text-fg dark:text-fg-dark truncate">
                {conversationTitle || 'New conversation'}
              </h2>
              <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark truncate">
                {agentName}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {agentId && (
              <button
                type="button"
                onClick={() => setHistoryOpen(true)}
                title="Conversation history"
                aria-label="Conversation history"
                aria-expanded={historyOpen}
                className="w-[34px] h-[34px] flex-none flex items-center justify-center rounded-lg
                           border border-line dark:border-line-dark
                           text-fg-secondary dark:text-fg-secondary-dark
                           hover:bg-surface-hover dark:hover:bg-surface-hover-dark hover:text-fg dark:hover:text-fg-dark
                           transition-colors duration-150"
              >
                <Clock className="w-[17px] h-[17px]" />
              </button>
            )}
            {quotaInfo && quotaInfo.quota > 0 && !quotaInfo.is_exempt && (
              <span
                className={`text-xs rounded-full px-3 py-1 border ${
                  isQuotaExceeded
                    ? 'bg-error-bg dark:bg-error-bg-dark border-error-border dark:border-error-border-dark text-error dark:text-error-dark font-medium'
                    : 'bg-surface-hover dark:bg-surface-hover-dark border-line dark:border-line-dark text-fg-secondary dark:text-fg-secondary-dark'
                }`}
              >
                {quotaInfo.call_count}/{quotaInfo.quota} Marketplace usage
              </span>
            )}
            {/*{agentId && (
              <button
                type="button"
                onClick={handleNewChat}
                className="inline-flex items-center gap-1.5 h-[34px] px-3 rounded-lg text-[13px]
                           border border-line dark:border-line-dark
                           text-fg-secondary dark:text-fg-secondary-dark
                           hover:bg-surface-hover dark:hover:bg-surface-hover-dark hover:text-fg dark:hover:text-fg-dark
                           transition-colors duration-150"
              >
                <Plus className="w-3.5 h-3.5" /> New chat
              </button>
            )}
            {/*{agentId && (
              <Link
                to={`/marketplace/agents/${agentId}`}
                className="inline-flex items-center h-[34px] px-3 rounded-lg text-[13px]
                           border border-line dark:border-line-dark
                           text-fg-secondary dark:text-fg-secondary-dark
                           hover:bg-surface-hover dark:hover:bg-surface-hover-dark hover:text-fg dark:hover:text-fg-dark
                           transition-colors duration-150"
              >
                Agent details
              </Link>
            )}*/}
          </div>
        </div>

        {/* Messages */}
         <div
           ref={messagesContainerRef}
           className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-[26px] space-y-[22px]
                      bg-canvas dark:bg-canvas-dark
                      scroll-smooth"
         >
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
                   Start chatting with {agentName}
                 </p>
                 <p className="text-[14.5px] text-fg-secondary dark:text-fg-secondary-dark max-w-[400px] mx-auto">
                   Ask a question or choose a suggestion below to get started
                 </p>
               </div>

               {starters.length > 0 && (
                 <div className="mt-7 grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-[620px] mx-auto">
                   {starters.map((starter) => (
                     <button
                       key={starter.id}
                       onClick={() => handleStarterClick(starter.prompt)}
                       className="
                         text-left
                         px-4 py-3.5
                         bg-surface dark:bg-surface-dark
                         border border-line dark:border-line-dark
                         rounded-lg
                         text-[13.5px] leading-snug text-fg dark:text-fg-dark
                         hover:border-ink dark:hover:border-ink-dark
                         hover:bg-surface-tint dark:hover:bg-surface-tint-dark
                         transition-colors duration-150
                         whitespace-pre-wrap break-words
                       "
                     >
                       {starter.prompt}
                     </button>
                   ))}
                 </div>
               )}
            </div>
          )}

          {messages.map((message) => {
            if (message.type === 'user') {
              return (
                <div key={message.id} className="flex justify-end max-w-[760px] mx-auto animate-slide-in-right gap-4">
                  <BackgroundImage text='YOU' size={38} iconSize={18} variant="vacio" className="mt-0.5 border border-accent dark:border-accent-dark" />
                  
                  <div className="max-w-[82%]">
                    <div className="bg-bronze-bg dark:bg-bronze-bg-dark border border-bronze-border dark:border-bronze-border-dark rounded-md px-4 py-[13px] text-sm leading-relaxed text-fg dark:text-fg-dark">
                      <MessageContent content={message.content} resolveFileUrl={resolveFileUrl} />
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

            if (message.type === 'error') {
              return (
                <div key={message.id} className="flex justify-start max-w-[760px] mx-auto animate-slide-in-left">
                  <div className="max-w-[82%]">
                    <div className="bg-error-bg dark:bg-error-bg-dark border border-error-border dark:border-error-border-dark text-error dark:text-error-dark rounded-md px-4 py-[13px]">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-semibold uppercase tracking-wide">Error</span>
                      </div>
                      <p className="text-sm">{message.content}</p>
                    </div>
                  </div>
                </div>
              );
            }

            const wasStreamed = message.id === lastStreamedMsgIdRef.current;
            return (
              <div
                key={message.id}
                className={`flex justify-start max-w-[760px] mx-auto ${wasStreamed ? '' : 'animate-slide-in-left'}`}
              >
                <div className="flex items-start gap-4 max-w-[82%]">
                  <BackgroundImage icon={Bot} size={38} iconSize={18} variant="vacio" className="mt-0.5 border border-accent dark:border-accent-dark" />
                  <div className="min-w-0 flex-1">
                    <div className="bg-surface dark:bg-surface-dark border border-line dark:border-line-dark rounded-md px-4 py-[13px] text-sm leading-relaxed text-fg dark:text-fg-dark">
                      <MessageContent content={message.content} resolveFileUrl={resolveFileUrl} />
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
              </div>
            );
          })}

          {showStreaming && (
            <StreamingMessage
              content={streamingContent}
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

          <div ref={messagesEndRef} />
        </div>

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

        {/* Input */}
        <div className="w-full max-w-[808px] mx-auto px-6 pb-[22px] pt-3 flex-shrink-0">
          {isQuotaExceeded && quotaInfo && (
            <div className="bg-error-bg dark:bg-error-bg-dark border border-error-border dark:border-error-border-dark rounded-lg p-3 mb-3 flex items-start gap-2">
              <span className="text-error dark:text-error-dark flex-shrink-0" aria-hidden="true">⚠️</span>
              <span className="text-error dark:text-error-dark text-sm font-medium">
                You've reached your monthly marketplace call limit
                ({quotaInfo.call_count}/{quotaInfo.quota}).
                Your quota resets at the start of next month (UTC).
              </span>
            </div>
          )}

           <div className="flex items-end gap-2 bg-surface dark:bg-surface-dark border-[1.5px] border-line dark:border-line-dark rounded-xl py-2 pr-2 pl-2.5 shadow-sm focus-within:border-accent dark:focus-within:border-accent-dark transition-colors duration-150">
             <input
               ref={fileInputRef}
               type="file"
               multiple
               onChange={handleFileSelect}
               className="hidden"
               id="marketplace-file-upload"
             />
             <button
               type="button"
               onClick={() => fileInputRef.current?.click()}
               disabled={isStreaming || isQuotaExceeded}
               className="w-9 h-9 flex items-center justify-center shrink-0 rounded-lg
                          text-fg-tertiary dark:text-fg-tertiary-dark
                          hover:text-fg dark:hover:text-fg-dark
                          hover:bg-surface-hover dark:hover:bg-surface-hover-dark
                          disabled:opacity-40 disabled:cursor-not-allowed
                          transition-colors duration-150"
               title={isQuotaExceeded ? 'Monthly quota reached' : 'Attach file'}
               aria-label="Attach file"
             >
               <Paperclip className="w-5 h-5" />
             </button>
 
             <textarea
               ref={textareaRef}
               value={inputMessage}
               onChange={(e) => setInputMessage(e.target.value)}
               onKeyDown={handleKeyDown}
               placeholder={approvalBlocksInput ? 'Answer the approval request to continue' : `Message ${agentName}…`}
               disabled={isStreaming || isQuotaExceeded || approvalBlocksInput}
               rows={1}
               className="flex-1 py-[9px] bg-transparent border-none outline-none resize-none
                          text-[14.5px] text-fg dark:text-fg-dark
                          placeholder:text-fg-tertiary dark:placeholder:text-fg-tertiary-dark
                          disabled:opacity-50
                          focus:outline-none focus:ring-0 focus:border-accent dark:focus:border-accent
                          max-h-40 input-login"
               style={{ minHeight: '1.5rem' }}
             />
 
             {isStreaming ? (
               <button
                 type="button"
                 onClick={abortStream}
                 className="w-[38px] h-[38px] flex items-center justify-center rounded-lg shrink-0
                            bg-error-bg dark:bg-error-bg-dark border border-error-border dark:border-error-border-dark
                            text-error dark:text-error-dark
                            hover:border-error dark:hover:border-error-dark transition-colors duration-150"
                 aria-label="Stop generating"
                 title="Stop generating"
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
                 aria-label="Send message"
               >
                 <ArrowRight className="w-4 h-4" />
               </button>
             )}
           </div>

          <p className="text-[11.5px] text-fg-faint dark:text-fg-faint-dark mt-[9px] text-center">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>

      <AttachedFilesPanel
        files={panelFiles}
        isLoading={isLoadingFiles}
        onRemoveFile={handleRemoveFile}
        onDownloadFile={handleDownloadFile}
      />

      {agentDetail && (
        <aside
          aria-label="Agent details"
          className="w-80 flex-none h-full min-h-0 overflow-y-auto overscroll-contain p-5
                     bg-canvas-alt dark:bg-canvas-alt-dark border-l border-line dark:border-line-dark"
        >
          <h2 className="font-display text-[17px] font-normal tracking-tight text-fg dark:text-fg-dark mb-4">
            Agent details
          </h2>

          <div className="flex flex-col gap-3.5">
            {/* Capabilities */}
            {(agentDetail.category || agentDetail.has_knowledge_base || agentDetail.has_memory || (agentDetail.tags && agentDetail.tags.length > 0)) && (
              <section className="bg-surface dark:bg-surface-dark border border-line dark:border-line-dark rounded-lg px-[18px] py-4">
                <h3 className="text-[11px] font-[700] uppercase tracking-[0.06em] text-fg-tertiary dark:text-fg-tertiary-dark mb-3">
                  Capabilities
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {agentDetail.category && (
                    <span className="text-xs rounded-full px-[11px] py-1 bg-bronze-bg dark:bg-bronze-bg-dark text-bronze dark:text-bronze-dark">
                      {agentDetail.category}
                    </span>
                  )}
                  {agentDetail.has_knowledge_base && (
                    <span className="text-xs rounded-full px-[11px] py-1 bg-bronze-bg dark:bg-bronze-bg-dark text-bronze dark:text-bronze-dark">
                      Knowledge-enhanced
                    </span>
                  )}
                  {agentDetail.has_memory && (
                    <span className="text-xs rounded-full px-[11px] py-1 bg-bronze-bg dark:bg-bronze-bg-dark text-bronze dark:text-bronze-dark">
                      Memory
                    </span>
                  )}
                  {agentDetail.tags?.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs rounded-full px-[11px] py-1 bg-bronze-bg dark:bg-bronze-bg-dark text-bronze dark:text-bronze-dark"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* Details */}
            <section className="bg-surface dark:bg-surface-dark border border-line dark:border-line-dark rounded-lg px-[18px] py-4">
              <h3 className="text-[11px] font-[700] uppercase tracking-[0.06em] text-fg-tertiary dark:text-fg-tertiary-dark mb-3">
                Details
              </h3>
              <dl className="flex flex-col gap-2.5 text-[13px]">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-fg-tertiary dark:text-fg-tertiary-dark">Published by</dt>
                  <dd className="font-medium text-fg dark:text-fg-dark truncate">{agentDetail.app_name}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-fg-tertiary dark:text-fg-tertiary-dark">Knowledge base</dt>
                  <dd className="font-medium text-fg dark:text-fg-dark">{agentDetail.has_knowledge_base ? 'Yes' : 'No'}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-fg-tertiary dark:text-fg-tertiary-dark">Memory</dt>
                  <dd className="font-medium text-fg dark:text-fg-dark">{agentDetail.has_memory ? 'Enabled' : 'Disabled'}</dd>
                </div>
                {agentDetail.rating_avg !== null && (
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-fg-tertiary dark:text-fg-tertiary-dark">Rating</dt>
                    <dd className="font-medium text-fg dark:text-fg-dark tabular-nums">
                      {agentDetail.rating_avg.toFixed(1)} ({agentDetail.rating_count})
                    </dd>
                  </div>
                )}
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-fg-tertiary dark:text-fg-tertiary-dark">Conversations</dt>
                  <dd className="font-medium text-fg dark:text-fg-dark tabular-nums">{agentDetail.conversation_count}</dd>
                </div>
                {agentDetail.published_at && (
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-fg-tertiary dark:text-fg-tertiary-dark">Published</dt>
                    <dd className="font-medium text-fg dark:text-fg-dark">
                      {new Date(agentDetail.published_at).toLocaleDateString()}
                    </dd>
                  </div>
                )}
              </dl>
            </section>

            {/* Marketplace usage */}
            {quotaInfo && quotaInfo.quota > 0 && !quotaInfo.is_exempt && (
              <section className="bg-surface dark:bg-surface-dark border border-line dark:border-line-dark rounded-lg px-[18px] py-4">
                <div className="flex items-center justify-between mb-[9px]">
                  <h3 className="text-[11px] uppercase tracking-[0.06em] text-fg-tertiary dark:text-fg-tertiary-dark">
                    Marketplace usage
                  </h3>
                  <span className="text-xs font-medium tabular-nums text-fg dark:text-fg-dark">
                    {Math.min(100, Math.round((quotaInfo.call_count / quotaInfo.quota) * 100))}%
                  </span>
                </div>
                <progress
                  value={Math.min(quotaInfo.call_count, quotaInfo.quota)}
                  max={quotaInfo.quota}
                  aria-label="Marketplace usage"
                  className="block w-full h-[5px] mb-[7px] appearance-none overflow-hidden rounded-full
                             bg-surface-tint dark:bg-surface-tint-dark
                             [&::-webkit-progress-bar]:bg-surface-tint dark:[&::-webkit-progress-bar]:bg-surface-tint-dark
                             [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:bg-accent dark:[&::-webkit-progress-value]:bg-accent-dark
                             [&::-moz-progress-bar]:rounded-full [&::-moz-progress-bar]:bg-accent dark:[&::-moz-progress-bar]:bg-accent-dark"
                />
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark tabular-nums">
                  {quotaInfo.call_count} / {quotaInfo.quota} calls this month
                </p>
              </section>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
