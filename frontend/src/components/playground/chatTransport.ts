import { apiService } from '../../services/api';
import type { StreamFnOptions } from '../../hooks/useStreamingChat';
import type { HitlPendingApproval, StreamEvent } from '../../types/streaming';
import type { ChatFilterField } from './OrchestratorFilterDropdowns';
import type {
  ChatSelection,
  ChatSelectionWarning,
  ChatTurnConfig,
  ChatTurnInfo,
} from '../../types/appChat';

/** One message of a loaded history. `turn` is only present for Chat assistant messages. */
export interface TransportHistoryMessage {
  readonly role: string;
  readonly content: string;
  readonly turn?: ChatTurnInfo | null;
}

export interface TransportHistory {
  readonly messages: readonly TransportHistoryMessage[];
  /** Playground only (media is session-scoped). */
  readonly sessionId?: string | null;
  readonly pendingApproval?: HitlPendingApproval | null;
}

/** An attached file, in the shape `ChatInterface` keeps. */
export interface TransportFile {
  readonly file_id: string;
  readonly filename: string;
  readonly file_type?: string;
  readonly processing_status?: string;
  readonly file_size_display?: string;
  readonly has_extractable_content?: boolean;
  readonly content_preview?: string;
}

export interface TransportMedia {
  media_id: number;
  name: string;
  status: string;
  source_type: string;
  media_type: string;
  error_message?: string | null;
}

/** Which agent-bound features of `ChatInterface` the transport supports; the rest is hidden, not deleted. */
export interface ChatTransportCapabilities {
  /** Session-scoped playground media: attach-media button, media rows, status polling, players, upload modal. */
  readonly agentMedia: boolean;
  /** Orchestrator-level exposed metadata filters above the composer. */
  readonly exposedFilters: boolean;
  /** Human approvals: approval card, resume/cancel, expiry watch, restoring a pending approval from history. */
  readonly approvals: boolean;
}

/** A message of the view model; `turn` / `turnConfig` are only set by the App Chat. */
export interface ChatMessageModel {
  id: string;
  type: 'user' | 'agent' | 'error';
  content: string;
  timestamp: Date;
  files?: string[];
  elapsedMs?: number;
  /** Effective configuration of this assistant message (history, or the `done` event). */
  turn?: ChatTurnInfo | null;
  /** Summary sent by the `metadata` event of the turn that produced this message. */
  turnConfig?: ChatTurnConfig | null;
}

/**
 * Everything `ChatInterface` needs from the backend. Implementations must be referentially stable
 * (memoize them in the caller): a new instance reloads the history and files.
 */
export interface ChatTransport {
  readonly capabilities: ChatTransportCapabilities;
  /** Send one turn (or, playground only, resume an approval) and pipe SSE events to `options.onEvent`. */
  streamMessage(message: string, options: StreamFnOptions): Promise<void>;
  /** History of a conversation; without id, the playground's default conversation (the Chat has none). */
  loadHistory(conversationId: number | null): Promise<TransportHistory>;
  /** Create a conversation (used when a file is attached before the first message). */
  createConversation(): Promise<{ conversationId: number; sessionId?: string | null }>;
  resetConversation(conversationId: number | null): Promise<void>;
  listFiles(conversationId: number | null): Promise<{ files: readonly TransportFile[] }>;
  uploadFile(conversationId: number, file: File): Promise<void>;
  removeFile(conversationId: number | null, fileId: string): Promise<void>;
  /** Resolve a fresh download URL. Never cache: Chat links expire after 5 minutes. */
  getFileDownloadUrl(conversationId: number | null, fileId: string): Promise<string>;
  /** Present iff `capabilities.agentMedia`. */
  readonly media?: {
    list(sessionId: string): Promise<unknown>;
    remove(sessionId: string): Promise<void>;
    streamUrl(mediaId: number, sessionId: string): string;
  };
  /** Present iff `capabilities.exposedFilters`. */
  readonly filters?: {
    list(): Promise<{ filters?: ChatFilterField[] }>;
    searchValues(fieldName: string, query: string, limit: number): Promise<{ values: string[] }>;
  };
}

// ---------------------------------------------------------------------------
// Agent playground
// ---------------------------------------------------------------------------

/** Wraps exactly the `api.ts` calls `ChatInterface` made before the transport existed. */
export function createAgentPlaygroundTransport(appId: number, agentId: number): ChatTransport {
  return {
    capabilities: { agentMedia: true, exposedFilters: true, approvals: true },

    streamMessage(message, options) {
      if (options.resume) {
        return apiService.decideApprovalStream(options.resume.approvalId, options.resume.decisions, {
          onEvent: options.onEvent,
          signal: options.signal,
        });
      }
      return apiService.chatWithAgentStream(appId, agentId, message, options);
    },

    async loadHistory(conversationId) {
      if (conversationId) {
        const response = await apiService.getConversationWithHistory(conversationId);
        return {
          messages: response.messages ?? [],
          sessionId: response.session_id,
          pendingApproval: response.pending_approval ?? null,
        };
      }
      const response = await apiService.getConversationHistory(appId, agentId);
      return { messages: response.messages ?? [] };
    },

    async createConversation() {
      const response = await apiService.createConversation(agentId);
      return { conversationId: response.conversation_id, sessionId: response.session_id };
    },

    resetConversation: (conversationId) => apiService.resetAgentConversation(appId, agentId, conversationId),

    listFiles: (conversationId) => apiService.listAttachedFiles(appId, agentId, conversationId),

    async uploadFile(conversationId, file) {
      await apiService.uploadFileForChat(appId, agentId, file, conversationId);
    },

    removeFile: (conversationId, fileId) => apiService.removeAttachedFile(appId, agentId, fileId, conversationId),

    getFileDownloadUrl: (conversationId, fileId) =>
      apiService.getFileDownloadUrl(appId, agentId, fileId, conversationId),

    media: {
      list: (sessionId) => apiService.listPlaygroundMedia(appId, agentId, sessionId),
      remove: async (sessionId) => {
        await apiService.deletePlaygroundMedia(appId, agentId, sessionId);
      },
      streamUrl: (mediaId, sessionId) => apiService.getPlaygroundMediaStreamUrl(appId, agentId, mediaId, sessionId),
    },

    filters: {
      list: () => apiService.getAgentChatFilters(appId, agentId),
      searchValues: (fieldName, query, limit) =>
        apiService.searchAgentChatFilterValues(appId, agentId, fieldName, query, limit),
    },
  };
}

// ---------------------------------------------------------------------------
// App Chat
// ---------------------------------------------------------------------------

export type ChatTransportErrorCode =
  | 'noSelection'
  | 'noConversation'
  /** 403: no access to the App, or the App is frozen (the backend does not tell them apart). */
  | 'forbidden'
  /** 404: the conversation or a selected resource is not available. */
  | 'notFound'
  /** 409 `SERVICE_RETIRED`: the selected model reached end of service. */
  | 'serviceRetired'
  /** 409 `CONVERSATION_BUSY`: the conversation is still answering a previous message. */
  | 'conversationBusy'
  /** 422 `STEP_LIMIT_REACHED` / SSE `step_limit_reached`: the agent ran out of steps; the conversation is kept. */
  | 'stepLimitReached'
  /** 422 `TOO_MANY_FILES`: one message carries more files than the per-message cap. */
  | 'tooManyFiles';

/**
 * Failure raised by the App Chat transport itself (not by the backend). It carries a code, never display
 * text: the UI translates it (`appChat.transportErrors.<code>`).
 */
export class ChatTransportError extends Error {
  readonly code: ChatTransportErrorCode;

  constructor(code: ChatTransportErrorCode) {
    super(code);
    this.name = 'ChatTransportError';
    this.code = code;
  }
}

/** What an App Chat turn reported, for callers that mirror the effective selection (e.g. the page). */
export interface ChatTurnEvent {
  readonly kind: 'metadata' | 'done';
  readonly conversationId?: number;
  readonly turnConfig?: ChatTurnConfig | null;
  readonly turn?: ChatTurnInfo | null;
  readonly warnings: readonly ChatSelectionWarning[];
}

export interface AppChatTransportOptions {
  /** Called for the `metadata` and `done` events of every turn. */
  readonly onTurnEvent?: (event: ChatTurnEvent) => void;
  /** Called when a turn is rejected by the backend with a status the UI explains (403, 404, 409 retired). */
  readonly onTransportError?: (code: ChatTransportErrorCode) => void;
  /**
   * Identifies the UI context a turn belongs to (e.g. the open conversation view). It is read when the turn
   * starts and again for every observer call; if it changed in between, the observers are skipped, so a
   * stream that outlives its view cannot write into the next one.
   */
  readonly getContextToken?: () => unknown;
}

/**
 * Maps the HTTP rejection of a turn (raised by `api.ts` as an `ApiError`, recognised by shape so this module
 * stays free of the class) to a `ChatTransportError`; anything else is returned unchanged.
 */
export function mapTurnError(error: unknown): unknown {
  if (typeof error !== 'object' || error === null || (error as { name?: unknown }).name !== 'ApiError') return error;
  const { status, errorCode } = error as { status?: number; errorCode?: string };
  if (status === 409 && errorCode === 'SERVICE_RETIRED') return new ChatTransportError('serviceRetired');
  if (status === 409 && errorCode === 'CONVERSATION_BUSY') return new ChatTransportError('conversationBusy');
  if (status === 422 && errorCode === 'TOO_MANY_FILES') return new ChatTransportError('tooManyFiles');
  if (status === 422 && errorCode === 'STEP_LIMIT_REACHED') return new ChatTransportError('stepLimitReached');
  if (status === 403) return new ChatTransportError('forbidden');
  if (status === 404) return new ChatTransportError('notFound');
  return error;
}

/** SSE `error` event codes the UI explains (the HTTP equivalents are in `mapTurnError`). */
const STREAM_ERROR_CODES: Readonly<Record<string, ChatTransportErrorCode>> = {
  service_retired: 'serviceRetired',
  conversation_busy: 'conversationBusy',
  step_limit_reached: 'stepLimitReached',
};

function observeTurnEvents(
  onEvent: (event: StreamEvent) => void,
  onTurnEvent?: (event: ChatTurnEvent) => void,
): (event: StreamEvent) => void {
  if (!onTurnEvent) return onEvent;
  // A failing observer must never abort the SSE parse loop: log it and keep streaming.
  const notify = (turnEvent: ChatTurnEvent): void => {
    try {
      onTurnEvent(turnEvent);
    } catch (error) {
      console.error('onTurnEvent handler failed:', error);
    }
  };
  return (event) => {
    onEvent(event);
    if (event.type === 'metadata') {
      const turnConfig = (event.data.turn_config as ChatTurnConfig | undefined) ?? null;
      notify({
        kind: 'metadata',
        conversationId: event.data.conversation_id as number | undefined,
        turnConfig,
        warnings: turnConfig?.warnings ?? [],
      });
    } else if (event.type === 'done') {
      const turn = (event.data.turn as ChatTurnInfo | null | undefined) ?? null;
      notify({
        kind: 'done',
        conversationId: event.data.conversation_id as number | undefined,
        turn,
        warnings: turn?.warnings ?? [],
      });
    }
  };
}

/**
 * Transport of the per-App Chat. `getSelection` is read when a message is sent (and when a conversation is
 * created for an early file upload), so every turn carries the selection in force at that moment.
 *
 * Decisions:
 * - A file attached before the first message creates the conversation first (as the playground does), with the
 *   current selection; the conversation id is then sent with the turn.
 * - There is no agent id or session id on the client: media, exposed filters and approvals are off.
 * - A turn without a selection cannot be sent: it throws `ChatTransportError('noSelection')` before any HTTP call.
 */
export function createAppChatTransport(
  appId: number,
  getSelection: () => ChatSelection | null,
  options: AppChatTransportOptions = {},
): ChatTransport {
  return {
    capabilities: { agentMedia: false, exposedFilters: false, approvals: false },

    async streamMessage(message, streamOptions) {
      const selection = getSelection();
      if (!selection) {
        throw new ChatTransportError('noSelection');
      }
      const token = options.getContextToken?.();
      const isCurrent = () => options.getContextToken?.() === token;
      const onTurnEvent = options.onTurnEvent
        ? (event: ChatTurnEvent) => {
            if (isCurrent()) options.onTurnEvent?.(event);
          }
        : undefined;
      // The backend reports some failures as an SSE `error` event with a code, after the stream started.
      let streamErrorCode: ChatTransportErrorCode | null = null;
      const observed = observeTurnEvents(streamOptions.onEvent, onTurnEvent);
      const onEvent = (event: StreamEvent): void => {
        if (event.type === 'error') {
          const code = (event.data as { code?: unknown }).code;
          if (typeof code === 'string' && code in STREAM_ERROR_CODES) streamErrorCode = STREAM_ERROR_CODES[code];
        }
        observed(event);
      };
      try {
        await apiService.streamAppChatMessage(
          appId,
          {
            message,
            selection,
            conversationId: streamOptions.conversationId,
            files: streamOptions.files,
            searchParams: streamOptions.searchParams,
          },
          { onEvent, signal: streamOptions.signal },
        );
        // A coded SSE error becomes the same coded error as its HTTP twin, so the UI translates it.
        if (streamErrorCode) throw new ChatTransportError(streamErrorCode);
      } catch (error) {
        const mapped = mapTurnError(error);
        if (mapped instanceof ChatTransportError && isCurrent()) options.onTransportError?.(mapped.code);
        throw mapped;
      }
    },

    async loadHistory(conversationId) {
      if (!conversationId) return { messages: [] };
      const detail = await apiService.getAppChatConversation(appId, conversationId);
      return { messages: detail.messages };
    },

    async createConversation() {
      const selection = getSelection();
      const conversation = await apiService.createAppChatConversation(appId, selection ? { selection } : {});
      return { conversationId: conversation.conversation_id };
    },

    async resetConversation(conversationId) {
      if (!conversationId) return;
      await apiService.resetAppChatConversation(appId, conversationId);
    },

    async listFiles(conversationId) {
      if (!conversationId) return { files: [] };
      const response = await apiService.listAppChatFiles(appId, conversationId);
      return {
        files: response.files.map((file) => ({
          file_id: file.file_id,
          filename: file.filename,
          file_type: file.file_type ?? undefined,
          processing_status: file.processing_status ?? undefined,
          file_size_display: file.file_size_display ?? undefined,
          has_extractable_content: file.has_extractable_content ?? undefined,
          content_preview: file.content_preview ?? undefined,
        })),
      };
    },

    async uploadFile(conversationId, file) {
      await apiService.uploadAppChatFile(appId, conversationId, file);
    },

    async removeFile(conversationId, fileId) {
      if (!conversationId) return;
      await apiService.removeAppChatFile(appId, conversationId, fileId);
    },

    async getFileDownloadUrl(conversationId, fileId) {
      if (!conversationId) throw new ChatTransportError('noConversation');
      const download = await apiService.getAppChatFileDownload(appId, conversationId, fileId);
      return download.download_url;
    },
  };
}
