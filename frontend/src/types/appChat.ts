/**
 * Types of the per-App Chat (`/internal/apps/{app_id}/chat`).
 * Aligned field by field with `backend/schemas/internal_chat_schemas.py`; datetimes arrive as ISO strings.
 */

export type ChatSiloSourceType = 'repository' | 'domain' | 'sharepoint' | 'silo';

/** `sandbox_output` is a turn warning whose `id` is a COUNT (files the code created that could not be delivered). */
export type ChatWarningKind = 'ai_service' | 'silo' | 'skill' | 'mcp_config' | 'sandbox_output';

/** What the user picks for one turn. */
export interface ChatSelection {
  readonly ai_service_id: number;
  readonly silo_id?: number | null;
  readonly skill_ids: readonly number[];
  readonly mcp_config_ids: readonly number[];
}

/** A stored default / conversation selection entry that is no longer valid and was dropped. */
export interface ChatSelectionWarning {
  readonly kind: ChatWarningKind;
  readonly id: number;
}

/** A skill / MCP config as it was used by a turn; `deleted` when it no longer exists. */
export interface ChatTurnRef {
  readonly id: number;
  readonly name: string;
  readonly deleted: boolean;
}

/** Effective configuration of one assistant message. */
export interface ChatTurnInfo {
  readonly turn_index: number;
  readonly ai_service_id?: number | null;
  readonly ai_service_name: string;
  readonly ai_service_deleted: boolean;
  readonly silo_id?: number | null;
  readonly silo_name?: string | null;
  readonly silo_deleted: boolean;
  readonly skills: readonly ChatTurnRef[];
  readonly mcp_configs: readonly ChatTurnRef[];
  readonly created_at: string;
  /** Resources skipped for this turn. Only filled in the payload of the turn that just completed, never in history. */
  readonly warnings: readonly ChatSelectionWarning[];
}

/** Item of the `turn_config` summary of the SSE `metadata` event (`ResolvedChatConfig.to_client_summary`). */
export interface ChatTurnConfigRef {
  readonly id: number;
  /** Null for a silo without a name (`ResolvedChatConfig.silo_name` is `str | None`). */
  readonly name: string | null;
}

/** Skill / MCP entry of `turn_config`: names are always set. */
export interface ChatTurnConfigNamedRef extends ChatTurnConfigRef {
  readonly name: string;
}

/** `turn_config` of the SSE `metadata` event and of the synchronous message response `metadata`. */
export interface ChatTurnConfig {
  readonly ai_service: ChatTurnConfigNamedRef;
  readonly silo: ChatTurnConfigRef | null;
  readonly skills: readonly ChatTurnConfigNamedRef[];
  readonly mcp_configs: readonly ChatTurnConfigNamedRef[];
  readonly warnings: readonly ChatSelectionWarning[];
  /** Whether the turn could run code; absent on older backends. No UI for it. */
  readonly code_interpreter?: boolean;
}

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

export interface ChatAIServiceOption {
  readonly service_id: number;
  readonly name: string;
  readonly provider?: string | null;
  readonly model_name?: string | null;
  readonly is_system: boolean;
  readonly lifecycle_status: string;
  readonly end_of_service_at?: string | null;
  readonly deprecation_notice?: string | null;
}

export type ChatSiloDisabledReason = 'embedding_service_retired';

export interface ChatSiloOption {
  readonly silo_id: number;
  readonly name?: string | null;
  readonly source_type: ChatSiloSourceType;
  readonly source_name?: string | null;
  readonly disabled_reason?: ChatSiloDisabledReason | null;
}

export interface ChatSkillOption {
  readonly skill_id: number;
  readonly name: string;
  readonly description?: string | null;
  readonly is_system: boolean;
}

export interface ChatMcpConfigOption {
  readonly config_id: number;
  readonly name: string;
}

/** Whether files attached in the Chat are indexed (needs the App's default embedding service). Absent on older backends = enabled. */
export type ChatAttachmentIndexingReason = 'no_default_embedding_service' | 'embedding_service_retired';

export interface ChatAttachmentIndexing {
  readonly enabled: boolean;
  readonly reason: ChatAttachmentIndexingReason | null;
}

/** Whether the Chat can run skill scripts (needs the App's default sandbox service). Absent on older backends = show nothing. */
export type ChatCodeInterpreterReason =
  | 'disabled_in_app_settings'
  | 'sandbox_service_retired'
  | 'sandbox_provider_unavailable';

export interface ChatCodeInterpreter {
  readonly enabled: boolean;
  readonly reason: ChatCodeInterpreterReason | null;
}

export interface ChatOptions {
  readonly ai_services: readonly ChatAIServiceOption[];
  readonly silos: readonly ChatSiloOption[];
  readonly skills: readonly ChatSkillOption[];
  readonly mcp_configs: readonly ChatMcpConfigOption[];
  readonly default_selection?: ChatSelection | null;
  readonly default_warnings: readonly ChatSelectionWarning[];
  readonly has_usable_model: boolean;
  readonly attachment_indexing?: ChatAttachmentIndexing | null;
  readonly code_interpreter?: ChatCodeInterpreter | null;
}

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

export interface ChatConversationCreateRequest {
  readonly title?: string | null;
  readonly selection?: ChatSelection | null;
}

/** One Chat conversation of the caller. `selection` is only filled by the create endpoint. */
export interface ChatConversation {
  readonly conversation_id: number;
  readonly title?: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly last_message?: string | null;
  readonly message_count: number;
  readonly selection?: ChatSelection | null;
}

export interface ChatConversationList {
  readonly conversations: readonly ChatConversation[];
  readonly total: number;
}

/** A history message; assistant messages carry the `turn` snapshot (null when unknown). */
export interface ChatHistoryMessage {
  readonly role: string;
  readonly content: string;
  readonly message_id?: string | null;
  readonly turn?: ChatTurnInfo | null;
}

export interface ChatConversationDetail extends ChatConversation {
  readonly messages: readonly ChatHistoryMessage[];
  readonly current_selection?: ChatSelection | null;
  readonly warnings: readonly ChatSelectionWarning[];
  /** Always null in practice: the Chat rejects every approval pause. */
  readonly pending_approval?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Files (scoped to one conversation)
// ---------------------------------------------------------------------------

export interface ChatFileUploadResult {
  readonly success: boolean;
  readonly file_id: string;
  readonly filename: string;
  readonly file_type?: string | null;
  readonly vectorized: boolean;
  readonly file_size_bytes?: number | null;
  readonly file_size_display?: string | null;
  readonly processing_status?: string | null;
  readonly content_preview?: string | null;
  readonly has_extractable_content?: boolean | null;
  readonly mime_type?: string | null;
}

export interface ChatFileInfo {
  readonly file_id: string;
  readonly filename: string;
  readonly file_type?: string | null;
  readonly content?: string | null;
  readonly file_path?: string | null;
  readonly uploaded_at?: string | null;
  readonly file_size_bytes?: number | null;
  readonly file_size_display?: string | null;
  readonly processing_status?: string | null;
  readonly content_preview?: string | null;
  readonly has_extractable_content?: boolean | null;
  readonly mime_type?: string | null;
  readonly conversation_id?: string | null;
}

export interface ChatFileList {
  readonly files: readonly ChatFileInfo[];
  readonly total_size_bytes: number;
  readonly total_size_display: string;
}

/** Signed link; it expires after 5 minutes, so fetch it on click and never cache it. */
export interface ChatFileDownload {
  readonly download_url: string;
  readonly filename: string;
}

/** `{success, message}` answer of reset / remove-file. */
export interface ChatActionResult {
  readonly success: boolean;
  readonly message: string;
}

/** Fields of a Chat turn (`POST /chat/stream`, multipart). */
export interface ChatStreamRequest {
  readonly message: string;
  readonly selection: ChatSelection;
  readonly conversationId?: number | null;
  readonly files?: readonly File[];
  /** Ids of files already attached to the conversation. */
  readonly fileReferences?: readonly string[];
  readonly searchParams?: unknown;
}
