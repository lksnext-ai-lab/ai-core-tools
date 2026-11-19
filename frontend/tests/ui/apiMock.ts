import { vi, type Mock } from 'vitest';
import type { StreamEvent } from '../../src/types/streaming';
import type {
  ChatConversationDetail,
  ChatOptions,
  ChatSelection,
  ChatStreamRequest,
  ChatTurnConfig,
  ChatTurnInfo,
} from '../../src/types/appChat';

// The module is mocked (see setup.ts), so the real `ApiError` must be loaded around the mock, not through it.
const { ApiError } = await vi.importActual<typeof import('../../src/services/api')>('../../src/services/api');

type AnyMock = Mock<(...args: never[]) => unknown>;

const methods = new Map<string, AnyMock>();

/**
 * Stand-in for `apiService`: every method is a `vi.fn()` created on first use. A method nobody configured
 * throws, so a test can never reach the network (or silently depend on an unmocked call).
 */
export const apiMock = new Proxy({} as Record<string, AnyMock>, {
  get(_target, name) {
    if (typeof name !== 'string' || name === 'then') return undefined;
    let fn = methods.get(name);
    if (!fn) {
      fn = vi.fn((..._args: never[]) => {
        throw new Error(`Unmocked apiService.${name} call`);
      }) as AnyMock;
      methods.set(name, fn);
    }
    return fn;
  },
});

export function resetApiMock(): void {
  methods.clear();
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

export const SELECTION: ChatSelection = { ai_service_id: 1, silo_id: null, skill_ids: [], mcp_config_ids: [] };

export function makeOptions(overrides: Partial<ChatOptions> = {}): ChatOptions {
  return {
    ai_services: [
      { service_id: 1, name: 'Alpha', provider: 'OpenAI', model_name: 'gpt-a', is_system: false, lifecycle_status: 'active' },
      { service_id: 2, name: 'Beta', provider: 'Anthropic', model_name: 'claude-b', is_system: false, lifecycle_status: 'active' },
    ],
    silos: [{ silo_id: 10, name: 'Handbook', source_type: 'repository' }],
    skills: [
      { skill_id: 20, name: 'Summarize', is_system: false },
      { skill_id: 21, name: 'Translate', is_system: true },
    ],
    mcp_configs: [{ config_id: 30, name: 'Tickets' }],
    default_selection: { ...SELECTION },
    default_warnings: [],
    has_usable_model: true,
    ...overrides,
  };
}

export function makeDetail(id: number, overrides: Partial<ChatConversationDetail> = {}): ChatConversationDetail {
  return {
    conversation_id: id,
    title: `Conversation ${id}`,
    created_at: '2026-01-01T10:00:00Z',
    updated_at: '2026-01-01T10:00:00Z',
    last_message: null,
    message_count: 0,
    messages: [],
    current_selection: { ...SELECTION },
    warnings: [],
    pending_approval: null,
    ...overrides,
  };
}

export function makeTurn(overrides: Partial<ChatTurnInfo> = {}): ChatTurnInfo {
  return {
    turn_index: 0,
    ai_service_id: 1,
    ai_service_name: 'Alpha',
    ai_service_deleted: false,
    silo_id: null,
    silo_name: null,
    silo_deleted: false,
    skills: [],
    mcp_configs: [],
    created_at: '2026-01-01T10:00:00Z',
    warnings: [],
    ...overrides,
  };
}

export function makeTurnConfig(overrides: Partial<ChatTurnConfig> = {}): ChatTurnConfig {
  return {
    ai_service: { id: 1, name: 'Alpha' },
    silo: null,
    skills: [],
    mcp_configs: [],
    warnings: [],
    ...overrides,
  };
}

export function apiError(status: number, errorCode?: string): Error {
  return new ApiError(`HTTP ${status}`, status, undefined, errorCode);
}

// ---------------------------------------------------------------------------
// Streaming
// ---------------------------------------------------------------------------

/** One in-flight Chat turn: the test decides when each SSE event arrives and how the request ends. */
export interface FakeTurn {
  readonly appId: number;
  readonly request: ChatStreamRequest;
  readonly signal?: AbortSignal;
  emit(event: StreamEvent): void;
  metadata(conversationId: number, turnConfig?: ChatTurnConfig): void;
  token(content: string): void;
  /** Sends `done` and ends the request. */
  done(conversationId: number, response: string, turn?: ChatTurnInfo | null): void;
  /** Ends the request successfully without `done` (stream closed). */
  close(): void;
  /** Rejects the request, like an HTTP error raised before the stream starts. */
  fail(error: Error): void;
}

export interface FakeStream {
  readonly turns: FakeTurn[];
}

/** Routes `apiService.streamAppChatMessage` to turns the test drives step by step. */
export function installFakeChatStream(): FakeStream {
  const turns: FakeTurn[] = [];
  apiMock.streamAppChatMessage.mockImplementation(((
    appId: number,
    request: ChatStreamRequest,
    options: { onEvent: (event: StreamEvent) => void; signal?: AbortSignal },
  ) =>
    new Promise<void>((resolve, reject) => {
      const emit = (event: StreamEvent) => options.onEvent(event);
      turns.push({
        appId,
        request,
        signal: options.signal,
        emit,
        metadata: (conversationId, turnConfig) =>
          emit({
            type: 'metadata',
            data: { conversation_id: conversationId, ...(turnConfig ? { turn_config: turnConfig } : {}) },
          }),
        token: (content) => emit({ type: 'token', data: { content } }),
        done: (conversationId, response, turn = makeTurn()) => {
          emit({ type: 'done', data: { response, conversation_id: conversationId, turn } });
          resolve();
        },
        close: () => resolve(),
        fail: (error) => reject(error),
      });
    })) as never);
  return { turns };
}

export interface ChatApiSetup {
  options?: ChatOptions;
  /** Conversations that can be opened by id (404 otherwise). */
  conversations?: Record<number, ChatConversationDetail>;
  role?: string;
}

/** Default behaviour of the App Chat endpoints the page uses. Individual tests override what they need. */
export function setupChatApi(setup: ChatApiSetup = {}): FakeStream {
  const conversations = setup.conversations ?? {};
  apiMock.getApp.mockResolvedValue({ app_id: 7, name: 'Demo', user_role: setup.role ?? 'owner' } as never);
  apiMock.getAppChatOptions.mockImplementation((async () => structuredClone(setup.options ?? makeOptions())) as never);
  apiMock.getAppChatConversation.mockImplementation((async (_appId: number, id: number) => {
    const detail = conversations[id];
    if (!detail) throw apiError(404);
    return structuredClone(detail);
  }) as never);
  apiMock.listAppChatConversations.mockImplementation((async () => ({
    conversations: Object.values(conversations).map((c) => ({
      conversation_id: c.conversation_id,
      title: c.title,
      created_at: c.created_at,
      updated_at: c.updated_at,
      last_message: c.last_message,
      message_count: c.message_count,
    })),
    total: Object.keys(conversations).length,
  })) as never);
  apiMock.listAppChatFiles.mockResolvedValue({ files: [], total_size_bytes: 0, total_size_display: '0 B' } as never);
  return installFakeChatStream();
}
