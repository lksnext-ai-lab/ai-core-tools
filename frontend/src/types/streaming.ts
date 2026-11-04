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
// Human-in-the-loop approvals
// ---------------------------------------------------------------------------

export type HitlDecisionType = 'approve' | 'edit' | 'reject';

export type HitlApprovalStatus =
  | 'pending' | 'deciding' | 'expiring' | 'approved' | 'edited' | 'rejected' | 'expired' | 'cancelled';

/** One tool call waiting for a decision; `action_id` is the tool call id. */
export interface HitlAction {
  readonly action_id: string;
  readonly name: string;
  readonly args: Record<string, unknown>;
  readonly description?: string | null;
  readonly allowed_decisions: readonly HitlDecisionType[];
}

/** Payload of the `hitl_interrupt` event and of `pending_approval` in conversation history. */
export interface HitlPendingApproval {
  readonly approval_id: string;
  readonly status: HitlApprovalStatus;
  /** ISO timestamp; unanswered approvals are rejected after it. */
  readonly expires_at: string;
  readonly actions: readonly HitlAction[];
}

/** A decision on one action, addressed by its `action_id`. */
export interface HitlDecision {
  readonly action_id: string;
  readonly type: HitlDecisionType;
  /** Replacement arguments (`edit` only). */
  readonly args?: Record<string, unknown>;
  /** Reason shown to the agent (`reject` only). */
  readonly message?: string;
}

/** Answer to an approval, sent instead of a chat message. */
export interface HitlResume {
  readonly approvalId: string;
  readonly decisions: readonly HitlDecision[];
}

/** Result of cancelling an approval (the agent's answer, or a new approval). */
export interface HitlCancelResult {
  readonly status: 'completed' | 'requires_approval';
  readonly response: string | Record<string, unknown>;
  readonly conversation_id: number | null;
  readonly pending_approval: HitlPendingApproval | null;
}
