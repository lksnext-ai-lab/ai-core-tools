import React, { useState, useRef, useEffect, useCallback, useMemo, useId } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Bot, MessageCircle, RefreshCw, Square, Timer } from 'lucide-react';
import { apiService } from '../../services/api';
import { StreamingChatError, useStreamingChat, type StreamFnOptions } from '../../hooks/useStreamingChat';
import { formatDuration } from '../../utils/duration';
import { formatClockTime, prefersReducedMotion } from '../../utils/clockTime';
import { useConfirm } from '../../contexts/ConfirmContext';
import Alert from '../ui/Alert';
import MessageContent from './MessageContent';
import StreamingMessage from './StreamingMessage';
import SearchFilters from './SearchFilters';
import type { SearchFilterMetadataField } from './SearchFilters';
import AttachedFilesPanel from './AttachedFilesPanel';
import type { PanelFile } from './AttachedFilesPanel';
import BackgroundImage from '../ui/BackgroundImage';
import UserAvatar from '../ui/UserAvatar';
import { useOptionalUser } from '../../contexts/UserContext';
import OrchestratorFilterDropdowns, { toSearchFilter } from './OrchestratorFilterDropdowns';
import type { ChatFilterField, ChatFilterSelection } from './OrchestratorFilterDropdowns';
import { SEARCH_RESULT_LIMIT } from './SearchableMultiSelect';
import ToolHistoryPanel from './ToolHistoryPanel';
import MediaUploadModal from './MediaUploadModal';
import VideoPlayer from './VideoPlayer';
import HitlApprovalCard from './HitlApprovalCard';
import { useApprovalExpiryWatch } from '../../hooks/useApprovalExpiryWatch';
import type { HitlDecision } from '../../types/streaming';
import type { ChatTurnConfig, ChatTurnInfo } from '../../types/appChat';
import type { VideoTimestamp } from './VideoPlayer';
import { LoadingState } from '../ui/LoadingState';
import ButtonApp from '../ui/ButtonApp';
import { SegmentedTabs } from '../ui/SegmentedTabs';
import { ChatTransportError, createAgentPlaygroundTransport } from './chatTransport';
import type { ChatMessageModel, ChatTransport, TransportFile } from './chatTransport';

type Message = ChatMessageModel;

/**
 * Legacy "Filter by Metadata" panel sends its filter as the entire search_params
 * root (a pre-existing bug, out of scope here — see SearchFilters.tsx). The new
 * orchestrator dropdowns must be nested under a "filter" key per resolve_search_params.
 * Merge defensively so neither panel clobbers the other if both happen to render.
 */
function buildSearchParams(
  legacyFilter: Record<string, unknown> | undefined,
  exposedSelection: ChatFilterSelection,
): Record<string, unknown> | undefined {
  const hasLegacyFilter = legacyFilter !== undefined && Object.keys(legacyFilter).length > 0;
  const exposedFilter = toSearchFilter(exposedSelection);
  if (!hasLegacyFilter && !exposedFilter) return undefined;
  return {
    ...(hasLegacyFilter ? legacyFilter : {}),
    ...(exposedFilter ? { filter: exposedFilter } : {}),
  };
}

interface ChatInterfaceBaseProps {
  appId: number;
  agentName: string;
  conversationId?: number | null;
  onConversationCreated?: (conversationId: number) => void;
  onConversationReset?: () => void;
  onMessageSent?: () => void;
  metadataFields?: SearchFilterMetadataField[];
  vectorDbType?: string;
  /** Extra controls rendered at the start of the chat toolbar (left of "Reset"). */
  toolbarStart?: React.ReactNode;
  /** When set, the "Reset" button is drawn inside this element (a page-level header slot) instead of the toolbar. */
  resetButtonTarget?: HTMLElement | null;
  /** Height classes of the chat card on `sm` and up. Defaults to the playground's `sm:h-[calc(100vh-20rem)]`. */
  cardHeightClassName?: string;
  /** Gives the conversation more room: a narrower side column and wider messages (App Chat). */
  wide?: boolean;
  /** Extra content rendered under each agent message (e.g. the App Chat's per-turn badge). */
  renderMessageMeta?: (message: ChatMessageModel) => React.ReactNode;
  /** Translated reason why sending is blocked (e.g. no model selected). Disables sending and is shown under the composer. */
  sendBlockedReason?: string;
  /** Moves focus to the composer whenever this number changes (and on mount when it is above 0). */
  focusComposerSignal?: number;
  /**
   * Chat only: called when a turn started by an instance that has since been replaced (the user moved to
   * another conversation) finishes. The turn still completes and is stored server-side, but no other parent
   * callback runs for it.
   */
  onDetachedTurnFinished?: () => void;
}

/**
 * Without `transport` the component talks to the agent playground and needs `agentId`.
 * A custom transport (e.g. the App Chat's) must be memoized by the caller.
 */
type ChatInterfaceProps = ChatInterfaceBaseProps & (
  | { agentId: number; transport?: undefined }
  | { agentId?: number; transport: ChatTransport }
);

function ChatInterface({
  appId,
  agentId,
  transport: transportProp,
  renderMessageMeta,
  sendBlockedReason,
  focusComposerSignal,
  onDetachedTurnFinished,
  agentName,
  conversationId,
  onConversationCreated,
  onConversationReset,
  onMessageSent,
  metadataFields,
  vectorDbType,
  toolbarStart,
  resetButtonTarget,
  cardHeightClassName = 'sm:h-[calc(100vh-20rem)]',
  wide = false,
}: Readonly<ChatInterfaceProps>) {
  const { t, i18n } = useTranslation('common');
  const userContext = useOptionalUser();
  const user = userContext?.user;
  const avatarUrl = userContext?.avatarUrl ?? null;
  const confirm = useConfirm();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const transport = useMemo(
    () => transportProp ?? createAgentPlaygroundTransport(appId, agentId as number),
    [transportProp, appId, agentId],
  );
  const { agentMedia, exposedFilters, approvals } = transport.capabilities;
  const [persistentFiles, setPersistentFiles] = useState<readonly TransportFile[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [sidePanelTab, setSidePanelTab] = useState<'info' | 'filters'>('info');
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(
    conversationId || null
  );
  const [filterMetadata, setFilterMetadata] = useState<Record<string, unknown> | undefined>(
    undefined
  );
  const [filtersKey, setFiltersKey] = useState(0);
  const [chatFilters, setChatFilters] = useState<ChatFilterField[]>([]);
  const [exposedFilterValues, setExposedFilterValues] = useState<ChatFilterSelection>({});
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
  const filterPanelId = `metadata-filters-${agentId ?? 'chat'}`;
  const sendBlockedReasonId = useId();
  /** Id of a conversation this component just created by sending its first turn (see the history effect). */
  const createdBySendRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  /**
   * False once a Chat instance was replaced: its in-flight turn must not call parent callbacks (they would
   * navigate the user away from the conversation they moved to). The playground is deliberately unchanged.
   */
  const isAlive = () => agentMedia || mountedRef.current;
  const hasMetadataFilters = !!metadataFields && metadataFields.length > 0;

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sendButtonRef = useRef<HTMLButtonElement>(null);
  const stopButtonRef = useRef<HTMLButtonElement>(null);
  /** Text of the single polite status region (turn started / finished / failed / reset). Never token text. */
  const [statusMessage, setStatusMessage] = useState('');
  const [resetFailed, setResetFailed] = useState(false);

  useEffect(() => {
    if (focusComposerSignal) textareaRef.current?.focus();
  }, [focusComposerSignal]);

  const playgroundStream = useCallback(
    (message: string, opts: StreamFnOptions) => transport.streamMessage(message, opts),
    [transport],
  );

  const {
    streamingContent, activeTools, thinkingMessage, isStreaming, responseElapsedMs, sendMessage, abortStream,
    toolExecutionHistory, clearToolHistory, settleAwaitingTools, pendingApproval, setPendingApproval,
  } = useStreamingChat(playgroundStream);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [expiredApprovalId, setExpiredApprovalId] = useState<string | null>(null);
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  const [focusAfterErrorTick, setFocusAfterErrorTick] = useState(0);
  // While a person can still answer, a new message would discard the paused turn.
  const approvalBlocksInput =
    approvals && pendingApproval !== null && pendingApproval.status === 'pending' && pendingApproval.approval_id !== expiredApprovalId;

  // Hold streaming content visible briefly after isStreaming flips to false,
  // so the transition to the final committed message is seamless.
  const [holdStreamingContent, setHoldStreamingContent] = useState(false);
  const showStreaming = isStreaming || holdStreamingContent;

  /** Focus is "lost" when it sits on <body> or on a composer control that was just disabled or removed. */
  const composerFocusLost = () => {
    const active = document.activeElement;
    return (
      !active || active === document.body || active === textareaRef.current
      || active === sendButtonRef.current || active === stopButtonRef.current
    );
  };

  // The composer locks while a turn runs and the Send button becomes Stop: without this, focus falls to
  // <body> and a keyboard user can no longer reach Stop. Only when focus was in the composer (or lost).
  useEffect(() => {
    if (isStreaming && composerFocusLost()) stopButtonRef.current?.focus();
  }, [isStreaming]);

  // ─── Scroll helpers ──────────────────────────────────────────────────────────

  /** Scroll the messages container to its bottom. Uses scrollTo on the container
   *  itself (not scrollIntoView on a child) so the scroll never propagates to
   *  ancestor scroll containers — critical now that <main> is scrollable. */
  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const container = messagesContainerRef.current;
    if (!container) return;
    // Reduced motion: never animate the scroll.
    container.scrollTo({ top: container.scrollHeight, behavior: prefersReducedMotion() ? 'auto' : behavior });
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
    // The Chat creates its conversation with the first turn: what is on screen is already that turn, so
    // reloading would blank the chat. (The playground keeps reloading: its session id comes from the reload.)
    if (!agentMedia && currentConversationId !== null && createdBySendRef.current === currentConversationId) {
      createdBySendRef.current = null;
      return;
    }
    let cancelled = false;
    const loadConversationHistory = async () => {
      try {
        setIsLoadingHistory(true);
        setMessages([]);
        setPendingApproval(null);

        const response = await transport.loadHistory(currentConversationId);
        // A slow answer of a previous conversation must not overwrite the current one.
        if (cancelled) return;

        if (currentConversationId) {
          if (agentMedia && response.sessionId) {
            setCurrentSessionId(response.sessionId);
          }
          // Restore an approval the conversation is still waiting for (e.g. after a reload).
          if (approvals) setPendingApproval(response.pendingApproval ?? null);
        }

        if (response.messages.length > 0) {
          const loadedMessages: Message[] = response.messages.map(
            (msg, index: number) => ({
              id: `history-${index}`,
              type: msg.role === 'user' ? 'user' : 'agent',
              content: msg.content,
              timestamp: new Date(),
              ...(msg.turn ? { turn: msg.turn } : {}),
            })
          );
          setMessages(loadedMessages);
        } else {
          setMessages([]);
        }
      } catch (error) {
        if (cancelled) return;
        console.error('Error loading conversation history:', error);
        setMessages([]);
      } finally {
        if (!cancelled) setIsLoadingHistory(false);
      }
    };

    const loadPersistentFiles = async () => {
      try {
        const response = await transport.listFiles(currentConversationId);
        if (cancelled) return;
        setPersistentFiles(response.files || []);
      } catch (error) {
        if (cancelled) return;
        console.error('Error loading persistent files:', error);
        setPersistentFiles([]);
      }
    };

    void loadConversationHistory();
    void loadPersistentFiles();

    // Load playground media if session exists
    if (agentMedia && transport.media && currentSessionId) {
      transport.media.list(currentSessionId)
        .then((media) => setPlaygroundMedia(Array.isArray(media) ? media : []))
        .catch(() => setPlaygroundMedia([]));
    } else {
      setPlaygroundMedia([]);
    }
    return () => {
      cancelled = true;
    };
  }, [appId, transport, currentConversationId, currentSessionId, historyReloadKey]);

  useApprovalExpiryWatch(
    approvals && currentConversationId ? expiredApprovalId : null,
    useCallback(async () => {
      if (!currentConversationId) return null;
      const response = await transport.loadHistory(currentConversationId);
      return response.pendingApproval?.approval_id ?? null;
    }, [currentConversationId, transport]),
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
    if (!agentMedia || !transport.media || !currentSessionId || !hasProcessingMediaForPolling) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }

    if (pollingRef.current) {
      return;
    }

    const mediaApi = transport.media;

    // Cap total polling so a media item stuck in a processing state (e.g. a
    // dead background task) does not poll forever: 3s interval × 200 = 10 min.
    const MAX_POLLS = 200;
    let polls = 0;

    // Start polling only when there is processing media and no interval is active
    pollingRef.current = setInterval(async () => {
      polls += 1;
      try {
        const media = await mediaApi.list(currentSessionId);
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
  }, [appId, transport, currentSessionId, hasProcessingMediaForPolling]);

  useEffect(() => {
    if ((!metadataFields || metadataFields.length === 0) && filterMetadata !== undefined) {
      setFilterMetadata(undefined);
      setFiltersKey((prev) => prev + 1);
    }
  }, [metadataFields, filterMetadata]);

  // Orchestrator-level exposed chat filters — aggregated across the agent's own
  // silo + all its subagents' silos, for whatever field names the designer whitelisted.
  useEffect(() => {
    let isMounted = true;

    const loadChatFilters = async () => {
      if (!exposedFilters || !transport.filters) {
        setChatFilters([]);
        return;
      }
      try {
        const response = await transport.filters.list();
        if (isMounted) setChatFilters(response.filters || []);
      } catch (error) {
        console.error('Error loading chat filters:', error);
        if (isMounted) setChatFilters([]);
      }
    };

    void loadChatFilters();
    setExposedFilterValues({});

    return () => {
      isMounted = false;
    };
  }, [transport]);

  const searchChatFilterValues = useCallback(
    async (fieldName: string, query: string) => {
      if (!transport.filters) return [];
      const response = await transport.filters.searchValues(fieldName, query, SEARCH_RESULT_LIMIT);
      return response.values;
    },
    [transport],
  );

  // ─── Message sending ─────────────────────────────────────────────────────────

  /** Commit a finished turn as an agent message (nothing to commit while it awaits approval). */
  const commitAgentResponse = (
    rawResponse: string | Record<string, unknown>,
    elapsedMs: number,
    awaitingApproval: boolean,
    turn?: ChatTurnInfo | null,
    turnConfig?: ChatTurnConfig | null,
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
      ...(turn ? { turn } : {}),
      ...(turnConfig ? { turnConfig } : {}),
    };
    // Commit the message and release the streaming hold in the same batch
    setMessages((prev) => [...prev, agentMsg]);
    setHoldStreamingContent(false);
    setStatusMessage(t('agentPlayground.chat.statusReady', { agent: agentName }));
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

  /** The backend refused the message before starting a turn (busy conversation, too many files): nothing ran. */
  const isRejectedBeforeStart = (error: unknown): boolean => {
    const cause = error instanceof Error ? error.cause : undefined;
    return [error, cause].some(
      (e) => e instanceof ChatTransportError && (e.code === 'conversationBusy' || e.code === 'tooManyFiles'),
    );
  };

  const describeSendError = (error: unknown): string => {
    // The streaming hook wraps whatever the transport threw; the original stays in `cause`.
    const cause = error instanceof Error ? error.cause : undefined;
    if (error instanceof ChatTransportError) return t(`appChat.transportErrors.${error.code}`);
    if (cause instanceof ChatTransportError) return t(`appChat.transportErrors.${cause.code}`);
    return error instanceof Error ? error.message : t('agentPlayground.chat.sendMessageFailed');
  };

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
    setStatusMessage(t('agentPlayground.chat.statusAnswering', { agent: agentName }));
    const messageText = inputMessage;
    setInputMessage('');
    // Force scroll to bottom so the user sees the streaming response
    resetScrollLock();
    setTimeout(() => scrollToBottom('instant'), 50);

    try {
      const searchParams = buildSearchParams(filterMetadata, exposedFilterValues);

      // Hold streaming content visible while we commit the final message
      setHoldStreamingContent(true);

      const result = await sendMessage(messageText, {
        conversationId: currentConversationId,
        searchParams,
      });

      if (!isAlive()) {
        onDetachedTurnFinished?.();
        return;
      }

      commitAgentResponse(result.response, result.elapsedMs, result.pendingApproval !== null, result.turn, result.turnConfig);

      if (result.conversationId && !currentConversationId) {
        createdBySendRef.current = result.conversationId;
        setCurrentConversationId(result.conversationId);
        onConversationCreated?.(result.conversationId);
      }
      if (agentMedia && result.sessionId && !currentSessionId) {
        setCurrentSessionId(result.sessionId);
      }

      await refreshFileList(result.conversationId || currentConversationId);
      onMessageSent?.();

      // Focus goes back to the composer once it is enabled again (see the effect below), if it was lost.
      setFocusAfterErrorTick((tick) => tick + 1);
    } catch (error) {
      if (!isAlive()) return;
      setHoldStreamingContent(false);
      setStatusMessage(t('agentPlayground.chat.statusFailed'));
      if (isRejectedBeforeStart(error)) {
        // The turn was rejected before it started: take the message back so it can be resent as it was
        // (attached files stay attached).
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
        // The composer is locked while a turn is in flight, so it is still empty here.
        setInputMessage(messageText);
      }
      // The turn failed after the backend had created the conversation (e.g. the agent ran out of steps): it
      // is kept server-side, so adopt it. The next message then continues it instead of starting another.
      if (error instanceof StreamingChatError && error.conversationId && !currentConversationId) {
        createdBySendRef.current = error.conversationId;
        setCurrentConversationId(error.conversationId);
        onConversationCreated?.(error.conversationId);
        onMessageSent?.();
      }
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        type: 'error',
        content: describeSendError(error),
        timestamp: new Date(),
        elapsedMs: error instanceof StreamingChatError ? error.elapsedMs : responseElapsedMs,
      };
      setMessages((prev) => [...prev, errorMsg]);
      // The composer was disabled during the turn, so focus fell to <body>: ask for it back (see the effect below).
      setFocusAfterErrorTick((tick) => tick + 1);
    }
  };

  // After a turn ends, return focus to the composer once it is enabled again, but only when focus is
  // lost (on <body>, or the Stop button that just disappeared): never steal it from a control the user
  // has moved to meanwhile (a selector chip, the side panel...).
  useEffect(() => {
    if (focusAfterErrorTick === 0) return;
    // Some engines keep the just-disabled composer as the active element instead of falling back to <body>;
    // the send and stop buttons count as part of the composer.
    if (composerFocusLost()) textareaRef.current?.focus();
  }, [focusAfterErrorTick]);

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
    const ok = await confirm({
      title: t('agentPlayground.chat.resetConfirmTitle'),
      message: t('agentPlayground.chat.resetConfirmMessage'),
      confirmLabel: t('agentPlayground.chat.reset'),
      cancelLabel: t('cancel'),
      variant: 'warning',
    });
    if (!ok) return;
    setResetFailed(false);
    try {
      await transport.resetConversation(currentConversationId);
      setMessages([]);
      setPersistentFiles([]);
      setPlaygroundMedia([]);
      setMediaConversationId(null);
      setCurrentSessionId(null);
      setFilterMetadata(undefined);
      setFiltersKey((prev) => prev + 1);
      setExposedFilterValues({});
      clearToolHistory();
      setStatusMessage(t('agentPlayground.chat.statusReset'));
      onConversationReset?.();
    } catch (error) {
      console.error('Error resetting conversation:', error);
      setResetFailed(true);
    }
  };

  const bubbleMaxWidth = wide ? 'max-w-[94%]' : 'max-w-[82%]';
  const messageMaxWidth = wide ? 'max-w-none' : 'max-w-[760px]';

  const resetButton = (
    <ButtonApp
      label={t('agentPlayground.chat.reset')}
      variant="secondary"
      size="compact"
      onClick={handleResetConversation}
      icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
    />
  );

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
        const convResponse = await transport.createConversation();
        if (!isAlive()) return;
        targetConversationId = convResponse.conversationId;
        setCurrentConversationId(targetConversationId);
        if (agentMedia && convResponse.sessionId) {
          setCurrentSessionId(convResponse.sessionId);
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
        await transport.uploadFile(targetConversationId, file);
      } catch (error) {
        console.error(`Error uploading file ${file.name}:`, error);
      }
    }

    try {
      const response = await transport.listFiles(targetConversationId);
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
      const filesResponse = await transport.listFiles(convId);
      setPersistentFiles(filesResponse.files || []);
    } catch {
      // Non-critical
    }
  };

  // ─── File helpers ─────────────────────────────────────────────────────────────

  const resolveFileUrl = useCallback(
    (fileId: string): Promise<string> =>
      transport.getFileDownloadUrl(currentConversationId, fileId),
    [transport, currentConversationId]
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
      await transport.removeFile(currentConversationId, fileId);
      const response = await transport.listFiles(currentConversationId);
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
        const convResponse = await transport.createConversation();
        convId = convResponse.conversationId;
        setCurrentConversationId(convId);
        setCurrentSessionId(convResponse.sessionId ?? null);
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
    if (!currentSessionId || !transport.media) return;
    const mediaApi = transport.media;

    const fetchMedia = async () => {
      const media = await mediaApi.list(currentSessionId);
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
    if (!currentSessionId || !transport.media) return;
    try {
      await transport.media.remove(currentSessionId);
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
    // Enter that confirms an IME composition (CJK, etc.) must not send the message.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
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
    !isStreaming && !hasMediaProcessing && !approvalBlocksInput && !sendBlockedReason
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
    const mediaApi = transport.media;
    if (!currentSessionId || !mediaApi) return {};
    return readyVideoMedias.reduce<Record<number, string>>((map, media) => {
      map[media.media_id] = mediaApi.streamUrl(media.media_id, currentSessionId);
      return map;
    }, {});
  }, [readyMediaIdsKey, currentSessionId, transport]);

  // ─── Render ───────────────────────────────────────────────────────────────────

  return (
    <div
      className="flex flex-col gap-4"
      onKeyDown={(event) => {
        // Esc stops a running turn. Layers that use Esc themselves (selector popover, modals) prevent default.
        if (event.key === 'Escape' && isStreaming && !event.defaultPrevented) abortStream();
      }}
    >
      {/* One polite status region for the whole chat: says once that a turn started / finished / failed.
          Never carries streamed text. */}
      <div role="status" className="sr-only">{statusMessage}</div>
      {/* Chat Interface + right column (info / filters) */}
      <div className={`grid grid-cols-1 items-start gap-[22px] ${wide ? 'xl:grid-cols-[minmax(0,1fr)_280px]' : 'xl:grid-cols-[minmax(0,1fr)_360px]'}`}>
        {/* Chat card */}
        <div className={`min-w-0 bg-canvas dark:bg-canvas-dark flex flex-col ${cardHeightClassName} sm:min-h-[480px] overflow-hidden`}>
          {/* Toolbar — optional start controls (e.g. conversations) + reset at the right */}
          {resetButtonTarget && createPortal(resetButton, resetButtonTarget)}
          {(toolbarStart || !resetButtonTarget) && (
            <div className="flex flex-wrap items-center gap-2 px-6 pt-3 pb-1">
              {toolbarStart}
              {!resetButtonTarget && <div className="ml-auto">{resetButton}</div>}
            </div>
          )}

          {resetFailed && (
            <div className="px-6 pb-2">
              <Alert
                type="error"
                message={t('agentPlayground.chat.resetFailed')}
                onDismiss={() => setResetFailed(false)}
                dismissAriaLabel={t('alert.dismissNamed', { name: t('agentPlayground.chat.reset') })}
              />
            </div>
          )}

          {/* Messages container. Focusable so a keyboard user can scroll it; it is not a live region (the
              status region above announces turns, tokens are never read out as they arrive). On narrow
              screens it has a bounded height of its own instead of sharing a fixed-height card. */}
          <div
            ref={messagesContainerRef}
            role="region"
            aria-label={t('agentPlayground.chat.messagesRegion')}
            tabIndex={0}
            className="flex-1 min-h-[16rem] max-h-[60vh] sm:min-h-0 sm:max-h-none overflow-y-auto overscroll-contain px-6 py-[26px] space-y-[22px]
                       bg-canvas dark:bg-canvas-dark
                       scroll-smooth focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:focus-visible:ring-focus-dark"
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
                        className={`flex justify-end ${messageMaxWidth} mx-auto animate-slide-in-right gap-4`}
                      >
                        <div aria-hidden="true">
                          <UserAvatar name={user?.name} email={user?.email} src={avatarUrl} size={38} className="mt-0.5" />
                        </div>
                        <div className={`${bubbleMaxWidth} min-w-0`}>
                          <div className="bg-bronze-bg dark:bg-bronze-bg-dark border border-bronze-border dark:border-bronze-border-dark rounded-md px-4 py-[13px] text-sm leading-relaxed text-fg dark:text-fg-dark">
                            <span className="sr-only">{t('agentPlayground.chat.speakerYou')}</span>
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
                            <span className="text-[11.5px] text-fg-secondary dark:text-fg-secondary-dark">
                              {formatClockTime(message.timestamp, i18n.language)}
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
                        className={`flex justify-start ${messageMaxWidth} mx-auto animate-slide-in-left`}
                      >
                        <div className={`${bubbleMaxWidth} min-w-0`}>
                          <div role="alert" className="bg-error-bg dark:bg-error-bg-dark border border-error-border dark:border-error-border-dark text-error dark:text-error-dark rounded-md px-4 py-[13px]">
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
                            <span className="text-[11.5px] text-fg-secondary dark:text-fg-secondary-dark">
                              {formatClockTime(message.timestamp, i18n.language)}
                            </span>
                            {message.elapsedMs !== undefined && (
                              <span className="ml-2 inline-flex items-center gap-1 text-[11.5px] tabular-nums text-fg-secondary dark:text-fg-secondary-dark">
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
                      className={`flex justify-start ${messageMaxWidth} mx-auto ${wasStreamed ? '' : 'animate-slide-in-left'}`}
                    >
                      <div className={`flex items-start gap-4 ${bubbleMaxWidth} min-w-0`}>
                        <div aria-hidden="true">
                          <BackgroundImage icon={Bot} size={38} iconSize={18} variant="vacio" className="mt-0.5 border border-accent dark:border-accent-dark" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="bg-surface dark:bg-surface-dark border border-line dark:border-line-dark rounded-md px-4 py-[13px] text-sm leading-relaxed text-fg dark:text-fg-dark">
                            <span className="sr-only">{t('agentPlayground.chat.speakerAssistant', { agent: agentName })}</span>
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
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                            <span className="text-[11.5px] text-fg-secondary dark:text-fg-secondary-dark">
                              {formatClockTime(message.timestamp, i18n.language)}
                            </span>
                            {message.elapsedMs !== undefined && (
                              <span className="inline-flex items-center gap-1 text-[11.5px] tabular-nums text-fg-secondary dark:text-fg-secondary-dark">
                                <Timer className="h-3 w-3" aria-hidden="true" />
                                {formatDuration(message.elapsedMs)}
                              </span>
                            )}
                            {renderMessageMeta?.(message)}
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
                {approvals && pendingApproval && !isStreaming && (
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
          <div className="px-4 pb-4 pt-3 border-t border-line dark:border-line-dark">
            {/* Orchestrator-level exposed chat filters — independent of the legacy
                "Filter by Metadata" panel above, since orchestrators typically have
                no own silo/metadataFields at all. Self-contained: owns its own
                collapse state, active-filter chips, and container. Placed directly
                above the composer (mirrors MarketplaceChatPage) so it stays visible
                without scrolling and reads as "what will scope my next message". */}
            {chatFilters.length > 0 && (
              <div className="mb-3">
                <OrchestratorFilterDropdowns
                  filters={chatFilters}
                  selected={exposedFilterValues}
                  onChange={setExposedFilterValues}
                  onSearchValues={searchChatFilterValues}
                  disabled={isStreaming}
                />
              </div>
            )}
            <div className="flex items-end gap-2 bg-surface dark:bg-surface-dark border-[1.5px] border-line dark:border-line-dark rounded-xl py-2 pr-2 pl-2.5 shadow-sm focus-within:border-accent dark:focus-within:border-accent-dark focus-within:ring-2 focus-within:ring-focus dark:focus-within:ring-focus-dark transition-colors duration-150">
              {/* File attach button */}
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={handleFileUpload}
                  className="hidden"
                  aria-hidden="true"
                  tabIndex={-1}
                  id="file-upload"
                  accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.doc,.docx"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isStreaming}
                  className="w-9 h-9 flex items-center justify-center shrink-0 rounded-lg
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark
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
              {agentMedia && (
              <button
                type="button"
                onClick={handleMediaButtonClick}
                disabled={isStreaming}
                className="w-[38px] h-[38px] flex items-center justify-center rounded-lg shrink-0
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark
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
              )}

              {/* Textarea */}
              <textarea
                ref={textareaRef}
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                aria-label={t('agentPlayground.chat.messagePlaceholder', { agent: agentName })}
                aria-describedby={sendBlockedReason ? sendBlockedReasonId : undefined}
                placeholder={approvalBlocksInput
                  ? t('agentPlayground.chat.answerApprovalToContinue')
                  : t('agentPlayground.chat.messagePlaceholder', { agent: agentName })}
                disabled={isStreaming || approvalBlocksInput}
                className="flex-1 py-[9px] bg-transparent border-none outline-none resize-none
                           text-[14.5px] text-fg dark:text-fg-dark
                           placeholder:text-fg-secondary dark:placeholder:text-fg-secondary-dark
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
                  ref={stopButtonRef}
                  onClick={abortStream}
                  className="w-[38px] h-[38px] flex items-center justify-center rounded-lg shrink-0
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark
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
                  ref={sendButtonRef}
                  onClick={handleSendMessage}
                  disabled={!canSend}
                  aria-describedby={sendBlockedReason ? sendBlockedReasonId : undefined}
                  className="w-[38px] h-[38px] flex items-center justify-center rounded-lg shrink-0
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark
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
            {/* Persistent polite region: present even when empty so a change of reason is announced. */}
            <p
              id={sendBlockedReasonId}
              role="status"
              className={sendBlockedReason ? 'text-[12px] text-bronze dark:text-bronze-dark mt-[9px] text-center' : 'sr-only'}
            >
              {sendBlockedReason ?? ''}
            </p>
            {!sendBlockedReason && (
              <p className="text-[11.5px] text-fg-secondary dark:text-fg-secondary-dark mt-[9px] text-center">
                {t('agentPlayground.chat.sendKeyboardHint')}
              </p>
            )}
          </div>
        </div>

        {/* Right column: Información (attached files + tool activity) / Filtros de metadatos */}
        <aside
          aria-label={t('agentPlayground.chat.sidePanel')}
          className="flex min-w-0 flex-col gap-3.5"
        >
          {hasMetadataFilters && (
            <SegmentedTabs
              ariaLabel={t('agentPlayground.chat.sidePanel')}
              tabs={[
                { id: 'info', label: t('agentPlayground.chat.infoTab') },
                { id: 'filters', label: t('agentPlayground.chat.filtersTab') },
              ]}
              activeTab={sidePanelTab}
              onChange={setSidePanelTab}
              className="flex-none"
            />
          )}

          <div className={`flex flex-col gap-3.5 ${sidePanelTab === 'info' || !hasMetadataFilters ? '' : 'hidden'}`}>
            {/* Attached Files Panel */}
            <AttachedFilesPanel
              variant="section"
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

          {/* Metadata filters — kept mounted (hidden) so their values survive tab switches */}
          {hasMetadataFilters && (
            <section
              id={filterPanelId}
              aria-label={t('agentPlayground.chat.filterByMetadata')}
              className={`rounded-lg border border-line p-3.5 dark:border-line-dark ${sidePanelTab === 'filters' ? '' : 'hidden'}`}
            >
              <p className="mb-3 text-[12.5px] leading-normal text-fg-secondary dark:text-fg-secondary-dark">
                {t('agentPlayground.chat.filtersHelp')}
              </p>
              <SearchFilters
                key={filtersKey}
                layout="stacked"
                metadataFields={metadataFields}
                dbType={vectorDbType?.toUpperCase()}
                disabled={isStreaming}
                onFilterMetadataChange={handleFilterMetadataChange}
              />
            </section>
          )}
        </aside>
      </div>

      {/* Media Upload Modal */}
      {agentMedia && agentId !== undefined && mediaConversationId && currentSessionId && (
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
