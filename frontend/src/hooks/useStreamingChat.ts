import { useCallback, useEffect, useRef, useState } from 'react';
import type { StreamEvent, ActiveTool } from '../types/streaming';
import { getStreamingMessage } from '../i18n/streaming';

interface StreamResult {
  response: string | Record<string, unknown>;
  conversationId: number | null;
  sessionId: string | null;
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
  readonly sendMessage: (message: string, options?: SendOptions) => Promise<StreamResult>;
  readonly abortStream: () => void;
}

function buildActiveTool(toolName: string): ActiveTool {
  return {
    name: toolName,
    displayName: toolName.replaceAll('_', ' '),
    status: 'running' as const,
    startedAt: Date.now(),
  };
}

function markToolComplete(toolName: string) {
  return (prev: ActiveTool[]): ActiveTool[] =>
    prev.map((t) =>
      t.name === toolName && t.status === 'running' ? { ...t, status: 'complete' as const } : t,
    );
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
      let sessionId: string | null = null;
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
                const thinkingMsg =
                  (event.data as { message?: string }).message ||
                  getStreamingMessage('using_tool', { name: toolName });
                setThinkingMessage(thinkingMsg);
                setActiveTools((prev) => [...prev, buildActiveTool(toolName)]);
                break;
              }

              case 'tool_end': {
                const toolName = (event.data as { tool_name?: string }).tool_name || '';
                setActiveTools(markToolComplete(toolName));
                break;
              }

              case 'thinking': {
                const msg = (event.data as { message?: string }).message;
                if (msg) setThinkingMessage(msg);
                break;
              }

              case 'metadata': {
                const metaConvId = (event.data as { conversation_id?: number }).conversation_id;
                const metaSessionId = (event.data as { session_id?: string }).session_id;
                if (metaConvId) {
                  conversationId = metaConvId;
                }
                if (metaSessionId) {
                  sessionId = metaSessionId;
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
                break;
              }

              case 'error': {
                const errMsg = (event.data as { message?: string }).message || 'Stream error';
                setStreamError(errMsg);
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
        abortControllerRef.current = null;
      }

      return {
        response: finalResponse || contentRef.current,
        conversationId,
        sessionId,
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
    sendMessage,
    abortStream,
  };
}
