import { useCallback, useEffect, useRef, useState } from 'react';
import type { StreamEvent, ActiveTool } from '../types/streaming';
import { getStreamingMessage } from '../i18n/streaming';

function isCodeTool(toolName: string): boolean {
  return toolName === 'code_interpreter' || toolName.endsWith('_repl');
}

export interface ToolOutputLine {
  readonly stream: 'stdout' | 'stderr';
  readonly line: string;
}

export interface ToolExecutionRecord {
  readonly id: string;
  readonly toolCallId?: string;
  readonly toolName: string;
  readonly displayName: string;
  readonly parentToolName?: string;
  readonly subagentName?: string;
  readonly subagentId?: number;
  readonly startedAt: number;
  readonly endedAt?: number;
  readonly status: 'running' | 'complete';
  readonly outputLines: ToolOutputLine[];
  readonly toolInput?: string;     // serialised args from tool_start
  readonly toolOutput?: string;    // result from tool_end
}

function buildToolRecordId(toolName: string, toolCallId?: string): string {
  return toolCallId || `${toolName}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function buildToolDisplayName(toolName: string, subagentName?: string): string {
  const formattedToolName = toolName.replaceAll('_', ' ');
  return subagentName ? `${subagentName} / ${formattedToolName}` : formattedToolName;
}

interface StreamResult {
  response: string | Record<string, unknown>;
  conversationId: number | null;
  files: Array<{ file_id: string; filename: string; file_type: string }>;
}

export interface StreamFnOptions {
  readonly files?: File[];
  readonly searchParams?: any;
  readonly conversationId?: number | null;
  readonly onEvent: (event: StreamEvent) => void;
  readonly signal?: AbortSignal;
}

export type StreamFn = (message: string, options: StreamFnOptions) => Promise<void>;

interface SendOptions {
  readonly files?: File[];
  readonly conversationId?: number | null;
  readonly searchParams?: any;
}

interface UseStreamingChatReturn {
  readonly streamingContent: string;
  readonly activeTools: ActiveTool[];
  readonly thinkingMessage: string | null;
  readonly isStreaming: boolean;
  readonly streamError: string | null;
  readonly codeOutputLines: string[];
  readonly isCodeRunning: boolean;
  readonly toolExecutionHistory: ToolExecutionRecord[];
  readonly clearToolHistory: () => void;
  readonly sendMessage: (message: string, options?: SendOptions) => Promise<StreamResult>;
  readonly abortStream: () => void;
}

function buildActiveTool(
  toolName: string,
  toolCallId?: string,
  subagentName?: string,
  subagentId?: number,
  parentToolName?: string,
): ActiveTool {
  return {
    name: toolName,
    toolCallId,
    displayName: toolName.replaceAll('_', ' '),
    parentToolName,
    subagentName,
    subagentId,
    status: 'running' as const,
    startedAt: Date.now(),
  };
}

function markToolComplete(toolName: string, toolCallId?: string) {
  return (prev: ActiveTool[]): ActiveTool[] =>
    prev.map((t) =>
      t.status === 'running' &&
      (
        (toolCallId && t.toolCallId === toolCallId) ||
        (!toolCallId && t.name === toolName)
      )
        ? { ...t, status: 'complete' as const }
        : t,
    );
}

function completeMatchingToolRecords(
  prev: ToolExecutionRecord[],
  toolName: string,
  toolCallId?: string,
  toolOutput?: string,
): ToolExecutionRecord[] {
  const endedAt = Date.now();
  let changed = false;

  const updated = prev.map((record) => {
    const matches =
      record.status === 'running' &&
      (
        (toolCallId && record.toolCallId === toolCallId) ||
        (!toolCallId && record.toolName === toolName)
      );

    if (!matches) return record;
    changed = true;
    return { ...record, status: 'complete' as const, endedAt, toolOutput };
  });

  return changed ? updated : prev;
}

function completeOpenTools(prev: ToolExecutionRecord[], fallbackOutput?: string): ToolExecutionRecord[] {
  const endedAt = Date.now();
  let changed = false;

  const updated = prev.map((record) => {
    if (record.status !== 'running') return record;
    changed = true;
    return {
      ...record,
      status: 'complete' as const,
      endedAt,
      toolOutput: record.toolOutput ?? fallbackOutput,
    };
  });

  return changed ? updated : prev;
}

/**
 * Reusable streaming-chat hook that drives the playground/marketplace UX.
 * Pass a `streamFn` that performs the SSE POST and pipes events through
 * `options.onEvent`. The hook owns all transport-agnostic state (tokens,
 * tools, thinking status, abort handling) and exposes a `sendMessage`
 * promise that resolves with the final response payload.
 */
export function useStreamingChat(streamFn: StreamFn): UseStreamingChatReturn {
  const [streamingContent, setStreamingContent] = useState('');
  const [activeTools, setActiveTools] = useState<ActiveTool[]>([]);
  const [thinkingMessage, setThinkingMessage] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [codeOutputLines, setCodeOutputLines] = useState<string[]>([]);
  const [isCodeRunning, setIsCodeRunning] = useState(false);
  const [toolExecutionHistory, setToolExecutionHistory] = useState<ToolExecutionRecord[]>([]);

  const clearToolHistory = useCallback(() => setToolExecutionHistory([]), []);

  const streamFnRef = useRef(streamFn);
  useEffect(() => {
    streamFnRef.current = streamFn;
  }, [streamFn]);

  const abortControllerRef = useRef<AbortController | null>(null);
  const contentRef = useRef('');
  const flushRequestedRef = useRef(false);
  const rafIdRef = useRef<number | null>(null);

  const abortStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const sendMessage = useCallback(
    async (message: string, options?: SendOptions): Promise<StreamResult> => {
      setStreamingContent('');
      setActiveTools([]);
      setThinkingMessage(getStreamingMessage('thinking'));
      setIsStreaming(true);
      setStreamError(null);
      setCodeOutputLines([]);
      setIsCodeRunning(false);
      contentRef.current = '';
      flushRequestedRef.current = false;
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;

      const scheduleFlush = () => {
        if (!flushRequestedRef.current) {
          flushRequestedRef.current = true;
          rafIdRef.current = requestAnimationFrame(() => {
            flushRequestedRef.current = false;
            setStreamingContent(contentRef.current);
          });
        }
      };

      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      let conversationId: number | null = options?.conversationId ?? null;
      let finalResponse: string | Record<string, unknown> = '';
      let finalFiles: Array<{ file_id: string; filename: string; file_type: string }> = [];

      try {
        await streamFnRef.current(message, {
          files: options?.files,
          searchParams: options?.searchParams,
          conversationId: options?.conversationId,
          signal: abortController.signal,
          onEvent: (event: StreamEvent) => {
            switch (event.type) {
              case 'token': {
                const content = (event.data as { content?: string }).content || '';
                contentRef.current += content;
                scheduleFlush();
                setThinkingMessage(null);
                break;
              }

              case 'tool_start': {
                const toolName = (event.data as { tool_name?: string }).tool_name || 'unknown';
                const toolCallId = (event.data as { tool_call_id?: string }).tool_call_id || undefined;
                const parentToolName = (event.data as { parent_tool_name?: string }).parent_tool_name || undefined;
                const subagentName = (event.data as { subagent_name?: string }).subagent_name || undefined;
                const subagentId = (event.data as { subagent_id?: number }).subagent_id || undefined;
                const thinkingMsg =
                  (event.data as { message?: string }).message ||
                  getStreamingMessage('using_tool', { name: toolName });
                setThinkingMessage(thinkingMsg);
                setActiveTools((prev) => {
                  if (!toolCallId) {
                    return [...prev, buildActiveTool(toolName, toolCallId, subagentName, subagentId, parentToolName)];
                  }

                  const existingIdx = prev.findIndex(
                    (tool) => tool.toolCallId === toolCallId && tool.status === 'running',
                  );
                  if (existingIdx !== -1) {
                    const updated = [...prev];
                    updated[existingIdx] = {
                      ...updated[existingIdx],
                      parentToolName: updated[existingIdx].parentToolName ?? parentToolName,
                      subagentName: updated[existingIdx].subagentName ?? subagentName,
                      subagentId: updated[existingIdx].subagentId ?? subagentId,
                    };
                    return updated;
                  }

                  return [
                    ...prev,
                    buildActiveTool(toolName, toolCallId, subagentName, subagentId, parentToolName),
                  ];
                });
                if (isCodeTool(toolName)) {
                  setCodeOutputLines([]);
                  setIsCodeRunning(true);
                }
                const toolInput = (event.data as { tool_input?: string }).tool_input ?? undefined;
                const newRecord: ToolExecutionRecord = {
                  id: buildToolRecordId(toolName, toolCallId),
                  toolCallId,
                  toolName,
                  displayName: buildToolDisplayName(toolName, subagentName),
                  parentToolName,
                  subagentName,
                  subagentId,
                  startedAt: Date.now(),
                  status: 'running',
                  outputLines: [],
                  toolInput,
                };
                setToolExecutionHistory((prev) => {
                  if (!toolCallId) return [...prev, newRecord];

                  const existingIdx = prev.findIndex(
                    (record) => record.toolCallId === toolCallId && record.status === 'running',
                  );
                  if (existingIdx === -1) return [...prev, newRecord];

                  const updated = [...prev];
                  updated[existingIdx] = {
                    ...updated[existingIdx],
                    toolName,
                    displayName: buildToolDisplayName(toolName, subagentName),
                    parentToolName: updated[existingIdx].parentToolName ?? parentToolName,
                    subagentName: updated[existingIdx].subagentName ?? subagentName,
                    subagentId: updated[existingIdx].subagentId ?? subagentId,
                    toolInput: updated[existingIdx].toolInput ?? toolInput,
                  };
                  return updated;
                });
                break;
              }

              case 'tool_end': {
                const toolName = (event.data as { tool_name?: string }).tool_name || '';
                const toolCallId = (event.data as { tool_call_id?: string }).tool_call_id || undefined;
                const toolOutput = (event.data as { tool_output?: string }).tool_output ?? undefined;
                setActiveTools(markToolComplete(toolName, toolCallId));
                if (isCodeTool(toolName)) {
                  setIsCodeRunning(false);
                }
                setToolExecutionHistory((prev) =>
                  completeMatchingToolRecords(prev, toolName, toolCallId, toolOutput),
                );
                break;
              }

              case 'thinking': {
                const msg = (event.data as { message?: string }).message;
                if (msg) setThinkingMessage(msg);
                break;
              }

              case 'code_output': {
                const line = (event.data as { line?: string }).line ?? '';
                const toolName = (event.data as { tool_name?: string }).tool_name || undefined;
                const subagentName = (event.data as { subagent_name?: string }).subagent_name || undefined;
                const stream = (event.data as { stream?: 'stdout' | 'stderr' }).stream === 'stderr'
                  ? 'stderr'
                  : 'stdout';
                if (line) {
                  setCodeOutputLines((prev) => [...prev, line]);
                  setToolExecutionHistory((prev) => {
                    const lastRunningIdx = [...prev].map((r, i) => ({ r, i })).reverse()
                      .find(({ r }) =>
                        isCodeTool(r.toolName) &&
                        r.status === 'running' &&
                        (!toolName || r.toolName === toolName),
                      )?.i ?? -1;
                    if (lastRunningIdx === -1) return prev;
                    const updated = [...prev];
                    updated[lastRunningIdx] = {
                      ...updated[lastRunningIdx],
                      displayName: buildToolDisplayName(updated[lastRunningIdx].toolName, subagentName ?? updated[lastRunningIdx].subagentName),
                      subagentName: updated[lastRunningIdx].subagentName ?? subagentName,
                      outputLines: [...updated[lastRunningIdx].outputLines, { stream, line }],
                    };
                    return updated;
                  });
                }
                break;
              }

              case 'metadata': {
                const metaConvId = (event.data as { conversation_id?: number }).conversation_id;
                if (metaConvId) {
                  conversationId = metaConvId;
                }
                break;
              }

              case 'done': {
                const doneData = event.data as {
                  response?: string | Record<string, unknown>;
                  files?: Array<{ file_id: string; filename: string; file_type: string }>;
                  conversation_id?: number;
                };
                finalResponse = doneData.response ?? contentRef.current;
                finalFiles = doneData.files ?? [];
                if (doneData.conversation_id) {
                  conversationId = doneData.conversation_id;
                }
                setActiveTools((prev) =>
                  prev.map((tool) => tool.status === 'running' ? { ...tool, status: 'complete' as const } : tool),
                );
                setToolExecutionHistory((prev) => completeOpenTools(prev));
                setIsCodeRunning(false);
                break;
              }

              case 'error': {
                const errMsg = (event.data as { message?: string }).message || 'Stream error';
                setStreamError(errMsg);
                setActiveTools((prev) =>
                  prev.map((tool) => tool.status === 'running' ? { ...tool, status: 'complete' as const } : tool),
                );
                setToolExecutionHistory((prev) => completeOpenTools(prev, `[Stream error] ${errMsg}`));
                setIsCodeRunning(false);
                break;
              }
            }
          },
        });
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          setStreamError(null);
        } else {
          const errMsg = err instanceof Error ? err.message : 'Streaming failed';
          setStreamError(errMsg);
          throw err;
        }
      } finally {
        if (rafIdRef.current) {
          cancelAnimationFrame(rafIdRef.current);
          rafIdRef.current = null;
        }
        flushRequestedRef.current = false;
        setStreamingContent(contentRef.current);
        setIsStreaming(false);
        setThinkingMessage(null);
        setActiveTools((prev) =>
          prev.map((tool) => tool.status === 'running' ? { ...tool, status: 'complete' as const } : tool),
        );
        setToolExecutionHistory((prev) => completeOpenTools(prev));
        setIsCodeRunning(false);
        abortControllerRef.current = null;
      }

      return {
        response: finalResponse || contentRef.current,
        conversationId,
        files: finalFiles,
      };
    },
    [],
  );

  return {
    streamingContent,
    activeTools,
    thinkingMessage,
    isStreaming,
    streamError,
    codeOutputLines,
    isCodeRunning,
    toolExecutionHistory,
    clearToolHistory,
    sendMessage,
    abortStream,
  };
}
