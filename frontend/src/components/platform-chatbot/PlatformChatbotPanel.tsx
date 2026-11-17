import React, { useRef, useState, useEffect, useMemo } from 'react';
import { ArrowRight, Bot, MessageCircle, RotateCcw, X } from 'lucide-react';
import { usePlatformChatbot } from '../../contexts/PlatformChatbotContext';
import { apiService } from '../../services/api';
import MessageContent from '../playground/MessageContent';
import StreamingMessage from '../playground/StreamingMessage';
import BackgroundImage from '../ui/BackgroundImage';
import ButtonApp from '../ui/ButtonApp';
import { FormTextArea } from '../ui/FormField';
import type { StreamEvent } from '../../types/streaming';
import { useTranslation } from 'react-i18next';

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

function localizeAuthenticationError(
  content: string,
  prefix: string,
  authenticationFailed: string,
): string {
  if (!/authentication failed|error de autenticación/i.test(content)) return content;

  const detail = content
    .replace(/(?:sorry,\s*something went wrong\.?|lo sentimos,\s*se ha producido un error\.?)\s*/i, '')
    .replace(/authentication failed|error de autenticación/gi, authenticationFailed);
  return `${prefix} ${detail}`.trim();
}

// ---------------------------------------------------------------------------

const PlatformChatbotPanel: React.FC<PlatformChatbotPanelProps> = ({
  agentName,
  onClose,
  onNewConversation,
}) => {
  const { t } = useTranslation('common');
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
            const errMsg = (event.data as { message?: string }).message || t('errors.generic');
            const translatedErrMsg = errMsg.replace(
              /authentication failed/gi,
              t('errors.authenticationFailed'),
            );
            setStreamingContent('');
            addMessage({
              role: 'assistant',
              content: `${t('errors.chatbotPrefix')} ${translatedErrMsg}`,
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
          content: t('errors.chatbotTryAgain'),
          timestamp: Date.now(),
        });
      }
    } finally {
      setIsSending(false);
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
    if (!(e.target instanceof HTMLTextAreaElement)) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
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
    <div
      role="dialog"
      aria-label={agentName || t('platformChatbot.defaultAgentName')}
      className="fixed bottom-20 right-4 z-50 flex h-[600px] max-h-[calc(100vh-6rem)] w-96 max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-md border border-line bg-surface shadow-[0_14px_40px_rgba(0,0,0,0.12)] dark:border-line-dark dark:bg-surface-dark"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-line bg-surface-tint px-4 py-3 dark:border-line-dark dark:bg-surface-tint-dark">
        <div className="flex min-w-0 items-center gap-2.5">
          <BackgroundImage icon={Bot} size={34} iconSize={17} />
          <span className="truncate font-display text-sm font-medium text-fg dark:text-fg-dark">
            {agentName || t('platformChatbot.defaultAgentName')}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <ButtonApp
            label={t('platformChatbot.new')}
            ariaLabel={t('platformChatbot.newConversation')}
            variant="muted"
            size="compact"
            icon={<RotateCcw size={12} aria-hidden="true" />}
            onClick={handleNewConversation}
          />
          <button
            type="button"
            onClick={onClose}
            aria-label={t('platformChatbot.close')}
            title={t('platformChatbot.close')}
            className="flex items-center rounded p-1 text-fg-tertiary transition-colors hover:text-fg focus:outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:focus-visible:outline-accent-dark"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && !isStreaming && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <BackgroundImage icon={MessageCircle} size={64} iconSize={32} />
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
              {t('platformChatbot.greeting')}
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-md border px-3 py-2 text-sm leading-relaxed text-fg dark:text-fg-dark ${
                msg.role === 'user'
                  ? 'border-bronze-border bg-bronze-bg dark:border-bronze-border-dark dark:bg-bronze-bg-dark'
                  : 'border-line bg-surface dark:border-line-dark dark:bg-surface-dark'
              }`}
            >
              {msg.role === 'assistant' ? (
                <MessageContent
                  content={localizeAuthenticationError(
                    msg.content,
                    t('errors.chatbotPrefix'),
                    t('errors.authenticationFailed'),
                  )}
                />
              ) : (
                <span className="whitespace-pre-wrap">{msg.content}</span>
              )}
            </div>
            {msg.role === 'assistant' && msg.follow_ups && msg.follow_ups.length > 0 && (
              <div className="mt-1 flex max-w-[85%] flex-col items-start gap-1">
                {msg.follow_ups.map((fu, fi) => (
                  <ButtonApp
                    key={fi}
                    label={fu}
                    variant="muted"
                    size="compact"
                    disabled={isSending}
                    className="text-left"
                    onClick={() => void handleSend(fu)}
                  />
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
      <div
        onKeyDown={handleKeyDown}
        className="flex items-end gap-2 border-t border-line p-3 dark:border-line-dark"
      >
        <FormTextArea
          id="platform-chatbot-input"
          label={t('platformChatbot.inputPlaceholder')}
          labelClassName="sr-only"
          className="flex-1"
          textareaClassName="block resize-none max-h-[120px]"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={t('platformChatbot.inputPlaceholder')}
          rows={1}
          disabled={isSending}
        />
        <button
          type="button"
          onClick={() => void handleSend()}
          disabled={isSending || !inputText.trim()}
          className="w-[38px] h-[38px] flex items-center justify-center rounded-lg shrink-0
                     bg-ink dark:bg-ink-dark text-ink-on dark:text-ink-on-dark
                     hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
                     transition-opacity duration-150"
          aria-label={t('agentPlayground.chat.sendMessage')}
          title={t('agentPlayground.chat.sendMessage')}
        >
          <ArrowRight className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
};

export default PlatformChatbotPanel;
