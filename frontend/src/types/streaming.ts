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
