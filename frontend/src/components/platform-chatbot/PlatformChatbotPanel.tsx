import React, { useRef, useState, useEffect, useMemo } from 'react';
import { X, RotateCcw, Send } from 'lucide-react';
import { usePlatformChatbot } from '../../contexts/PlatformChatbotContext';
import { apiService } from '../../services/api';
import MessageContent from '../playground/MessageContent';
import StreamingMessage from '../playground/StreamingMessage';
import type { StreamEvent } from '../../types/streaming';

interface PlatformChatbotPanelProps {
  agentName: string | null;
  onClose: () => void;
  onNewConversation: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * LLMs often emit literal newlines/tabs inside JSON strings instead of \n/\t,
 * which breaks JSON.parse. Walk the text and escape bare control characters
 * that appear inside string values.
 */
function sanitizeJsonControlChars(text: string): string {
  let inString = false;
  let escaped = false;
  let out = '';
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (escaped) {
      out += ch;
      escaped = false;
      continue;
    }
    if (ch === '\\' && inString) { escaped = true; out += ch; continue; }
    if (ch === '"') { inString = !inString; out += ch; continue; }
    if (inString) {
      if (ch === '\n') { out += '\\n'; continue; }
      if (ch === '\r') { out += '\\r'; continue; }
      if (ch === '\t') { out += '\\t'; continue; }
    }
    out += ch;
  }
  return out;
}

function unescapeJsonString(s: string): string {
  return s
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\r/g, '\r')
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\');
}

function parseAgentResponse(text: string): { content: string; follow_ups: string[] } {
  const idx = text.search(/\{\s*"/);
  if (idx === -1) return { content: text, follow_ups: [] };

  const jsonPart = text.slice(idx);

  // First attempt: JSON.parse with sanitization (handles literal newlines in strings)
  try {
    const parsed = JSON.parse(sanitizeJsonControlChars(jsonPart));
    if (parsed && typeof parsed.content === 'string') {
      return {
        content: parsed.content,
        follow_ups: Array.isArray(parsed.follow_ups)
          ? parsed.follow_ups.filter((s: unknown) => typeof s === 'string')
          : [],
      };
    }
  } catch { /* fall through to regex */ }

  // Regex fallback: extract content and follow_ups without JSON.parse.
  // Pattern matches a JSON string value, handling escape sequences correctly.
  const contentMatch = jsonPart.match(/"content"\s*:\s*"((?:[^"\\]|\\[\s\S])*)"/);
  if (!contentMatch) return { content: text, follow_ups: [] };

  const follow_ups: string[] = [];
  const fuMatch = jsonPart.match(/"follow_ups"\s*:\s*\[([\s\S]*?)\]/);
  if (fuMatch) {
    const fuItems = [...fuMatch[1].matchAll(/"((?:[^"\\]|\\[\s\S])*)"/g)];
    follow_ups.push(...fuItems.map(m => unescapeJsonString(m[1])));
  }

  return { content: unescapeJsonString(contentMatch[1]), follow_ups };
}

// ---------------------------------------------------------------------------

const PlatformChatbotPanel: React.FC<PlatformChatbotPanelProps> = ({
  agentName,
  onClose,
  onNewConversation,
}) => {
  const { messages, addMessage, sessionId } = usePlatformChatbot();
  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const displayStreamingContent = useMemo(() => {
    // Case 1: closing quote already received — extract complete content value
    const complete = streamingContent.match(/"content"\s*:\s*"((?:[^"\\]|\\.)*)"/);
    if (complete) return unescapeJsonString(complete[1]);

    // Case 2: still streaming the content value — show what's arrived so far
    const partial = streamingContent.match(/"content"\s*:\s*"([\s\S]*)/);
    if (partial) return unescapeJsonString(partial[1]);

    // Case 3: JSON response but content key not yet arrived — show nothing
    if (streamingContent.trimStart().startsWith('{')) return '';

    // Case 4: plain text response — show as-is
    return streamingContent;
  }, [streamingContent]);

  // Abort any in-flight stream on unmount
  useEffect(() => {
    return () => { abortControllerRef.current?.abort(); };
  }, []);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleSend = async (overrideText?: string) => {
    const text = (overrideText ?? inputText).trim();
    if (!text || isSending) return;

    // Append user message
    addMessage({ role: 'user', content: text, timestamp: Date.now() });
    if (!overrideText) setInputText('');
    setIsSending(true);
    setStreamingContent('');
    setIsStreaming(true);

    abortControllerRef.current = new AbortController();
    let accumulated = '';

    try {
      await apiService.streamPlatformChatbotMessage(text, sessionId, {
        signal: abortControllerRef.current.signal,
        onEvent: (event: StreamEvent) => {
          if (event.type === 'token') {
            const token = (event.data as { content?: string }).content || '';
            accumulated += token;
            setStreamingContent(accumulated);
          } else if (event.type === 'done') {
            const rawResponse = event.data.response;
            let content: string;
            let follow_ups: string[] = [];

            if (rawResponse && typeof rawResponse === 'object' && !Array.isArray(rawResponse)) {
              // Backend already parsed the JSON (e.g. when OutputParser is active)
              const r = rawResponse as Record<string, unknown>;
              content = typeof r.content === 'string' ? r.content : JSON.stringify(r, null, 2);
              follow_ups = Array.isArray(r.follow_ups)
                ? r.follow_ups.filter((s): s is string => typeof s === 'string')
                : [];
            } else {
              const finalText = (typeof rawResponse === 'string' ? rawResponse : null) || accumulated;
              ({ content, follow_ups } = parseAgentResponse(finalText));
            }

            setStreamingContent('');
            addMessage({ role: 'assistant', content, follow_ups, timestamp: Date.now() });
          } else if (event.type === 'error') {
            const errMsg = (event.data as { message?: string }).message || 'Something went wrong.';
            setStreamingContent('');
            addMessage({
              role: 'assistant',
              content: `Sorry, something went wrong. ${errMsg}`,
              timestamp: Date.now(),
            });
          }
        },
      });
    } catch (err: unknown) {
      setStreamingContent('');
      // Don't add error message if the request was aborted intentionally
      if (err instanceof Error && err.name !== 'AbortError') {
        addMessage({
          role: 'assistant',
          content: 'Sorry, something went wrong. Please try again.',
          timestamp: Date.now(),
        });
      }
    } finally {
      setIsSending(false);
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewConversation = () => {
    // Abort any in-progress stream
    abortControllerRef.current?.abort();
    setStreamingContent('');
    setIsStreaming(false);
    setIsSending(false);
    onNewConversation();
  };

  return (
    <div className="fixed bottom-20 right-4 z-50 w-96 h-[600px] flex flex-col rounded-xl shadow-2xl border bg-white dark:bg-zinc-900 overflow-hidden transition-all duration-300">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/50">
        <span className="font-semibold text-sm truncate">
          {agentName || 'AI Assistant'}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleNewConversation}
            className="text-xs px-2 py-1 rounded border hover:bg-muted transition-colors"
            title="New conversation"
          >
            <RotateCcw size={12} className="inline mr-1" />
            New
          </button>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-muted transition-colors"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !isStreaming && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Hi! How can I help you today?
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-foreground'
              }`}
            >
              {msg.role === 'assistant' ? (
                <MessageContent content={msg.content} />
              ) : (
                <span className="whitespace-pre-wrap">{msg.content}</span>
              )}
            </div>
            {msg.role === 'assistant' && msg.follow_ups && msg.follow_ups.length > 0 && (
              <div className="flex flex-col items-start gap-1 mt-1 max-w-[85%]">
                {msg.follow_ups.map((fu, fi) => (
                  <button
                    key={fi}
                    onClick={() => handleSend(fu)}
                    disabled={isSending}
                    className="text-xs px-3 py-1.5 rounded-full border border-primary/40 text-primary hover:bg-primary/10 transition-colors text-left disabled:opacity-40"
                  >
                    {fu}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {isStreaming && (
          <StreamingMessage
            content={displayStreamingContent}
            isStreaming={true}
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="flex gap-2 p-3 border-t">
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          rows={1}
          disabled={isSending}
          className="flex-1 resize-none rounded-md border bg-white dark:bg-zinc-800 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
          style={{ minHeight: '38px', maxHeight: '120px' }}
        />
        <button
          onClick={() => handleSend()}
          disabled={isSending || !inputText.trim()}
          className="shrink-0 p-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 transition-opacity"
          aria-label="Send"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
};

export default PlatformChatbotPanel;
