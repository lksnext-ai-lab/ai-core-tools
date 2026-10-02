export type StreamEventType =
  | 'token'
  | 'tool_start'
  | 'tool_end'
  | 'thinking'
  | 'code_output'
  | 'metadata'
  | 'error'
  | 'done'
  | 'hitl_interrupt';

export interface StreamEvent {
  type: StreamEventType;
  data: Record<string, unknown>;
}

export interface TokenEventData {
  content: string;
}

export interface ToolStartEventData {
  tool_name: string;
  tool_call_id?: string;
  tool_input?: string;
  parent_tool_name?: string;
  subagent_name?: string;
  subagent_id?: number;
}

export interface ToolEndEventData {
  tool_name: string;
  tool_call_id?: string;
  tool_output?: string;
  parent_tool_name?: string;
  subagent_name?: string;
  subagent_id?: number;
}

export interface ThinkingEventData {
  message: string;
}

export interface MetadataEventData {
  conversation_id?: number;
  agent_id?: number;
}

export interface ErrorEventData {
  message: string;
}

export interface DoneEventData {
  response: string | Record<string, unknown>;
  files?: Array<{
    file_id: string;
    filename: string;
    file_type: string;
  }>;
}

export interface ActiveTool {
  name: string;
  toolCallId?: string;
  displayName: string;
  input?: string;
  parentToolName?: string;
  subagentName?: string;
  subagentId?: number;
  status: 'running' | 'complete';
  startedAt: number;
}

export interface StreamingState {
  isStreaming: boolean;
  content: string;
  activeTools: ActiveTool[];
  thinkingMessage: string | null;
  conversationId: number | null;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Human-in-the-loop (LangChain HumanInTheLoopMiddleware interrupt format)
// ---------------------------------------------------------------------------

export type HitlDecisionType = 'approve' | 'edit' | 'reject';

export interface HitlActionRequest {
  name: string;
  args: Record<string, unknown>;
  description?: string;
}

export interface HitlReviewConfig {
  action_name: string;
  allowed_decisions: HitlDecisionType[];
}

/** Payload of the `hitl_interrupt` event and of `pending_approval` in conversation history. */
export interface HitlPendingApproval {
  action_requests: HitlActionRequest[];
  review_configs: HitlReviewConfig[];
}

/** One decision per action request, in the same order. */
export interface HitlDecision {
  type: HitlDecisionType;
  edited_action?: { name: string; args: Record<string, unknown> };
  message?: string;
}
