import { useState, useRef, useCallback } from 'react';
import { apiService } from '../services/api';
import type { StreamEvent, ActiveTool } from '../types/streaming';
import { getStreamingMessage } from '../i18n/streaming';

interface StreamResult {
  response: string | Record<string, unknown>;
  conversationId: number | null;
  files: Array<{ file_id: string; filename: string; file_type: string }>;
}

interface UseStreamingChatReturn {
  /** Accumulated token content while streaming */
  streamingContent: string;
  /** Currently active tools being used by the agent */
  activeTools: ActiveTool[];
  /** Human-readable status message (e.g. "Searching knowledge base...") */
  thinkingMessage: string | null;
  /** Whether a stream is currently in progress */
  isStreaming: boolean;
  /** Error message if stream failed */
  streamError: string | null;
  /** Send a message and stream the response */
  sendMessage: (
    message: string,
    options?: {
      files?: File[];
      conversationId?: number | null;
      searchParams?: any;
    }
  ) => Promise<StreamResult>;
  /** Abort the current stream */
  abortStream: () => void;
}

/** Module-level helpers — defined outside the hook to avoid deep function nesting */
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
      t.name === toolName && t.status === 'running' ? { ...t, status: 'complete' as const } : t
    );
}

export function useStreamingChat(
  appId: number,
  agentId: number,
): UseStreamingChatReturn {
  const [streamingContent, setStreamingContent] = useState('');
  const [activeTools, setActiveTools] = useState<ActiveTool[]>([]);
  const [thinkingMessage, setThinkingMessage] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  // Ref to accumulate content without re-renders on every token
  const contentRef = useRef('');
  // Throttle: flush visible content at most once per animation frame (~16ms)
  const flushRequestedRef = useRef(false);
  const rafIdRef = useRef<number | null>(null);

  const abortStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const sendMessage = useCallback(
    async (
      message: string,
      options?: {
        files?: File[];
        conversationId?: number | null;
        searchParams?: any;
      }
    ): Promise<StreamResult> => {
      // Reset state
      setStreamingContent('');
      setActiveTools([]);
      setThinkingMessage(getStreamingMessage('thinking'));
      setIsStreaming(true);
      setStreamError(null);
      contentRef.current = '';
      flushRequestedRef.current = false;
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;

      /** Schedule a throttled UI update — batches rapid tokens into one render per frame */
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
        await apiService.chatWithAgentStream(appId, agentId, message, {
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
                // Clear thinking message once tokens start flowing
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
          setStreamError(null); // User-initiated abort is not an error
        } else {
          const errMsg = err instanceof Error ? err.message : 'Streaming failed';
          setStreamError(errMsg);
          throw err;
        }
      } finally {
        // Cancel pending throttle and flush all remaining content immediately
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
        files: finalFiles,
      };
    },
    [appId, agentId]
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
