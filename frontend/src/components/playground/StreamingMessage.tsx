import React from 'react';
import type { ActiveTool } from '../../types/streaming';
import MessageContent from './MessageContent';

interface StreamingMessageProps {
  /** The accumulated text content so far */
  content: string;
  /** Whether tokens are still arriving */
  isStreaming: boolean;
  /** Active tools (shown as status pills) — rendered ABOVE the message */
  activeTools?: ActiveTool[];
  /** Human-readable thinking status */
  thinkingMessage?: string | null;
}

const StreamingMessage: React.FC<StreamingMessageProps> = ({
  content,
  isStreaming,
  activeTools = [],
  thinkingMessage,
}) => {
  const hasContent = content.length > 0;

  return (
    <div className="flex justify-start animate-slide-in-left">
      <div className="max-w-[90%] lg:max-w-[80%]">
        {/* Tool activity + thinking — always above the response */}
        {(activeTools.length > 0 || (isStreaming && thinkingMessage && !hasContent)) && (
          <div className="mb-2 ml-1 space-y-1.5">
            {/* Tool status pills */}
            {activeTools.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {activeTools.map((tool) => (
                  <span
                    key={`${tool.name}-${tool.startedAt}`}
                    className={`pg-tool-pill animate-fade-in ${
                      tool.status === 'complete' ? 'pg-tool-pill--complete' : ''
                    }`}
                  >
                    {tool.status === 'running' ? (
                      <svg
                        className="w-3 h-3 animate-tool-spin"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        aria-hidden="true"
                      >
                        <circle
                          cx="12"
                          cy="12"
                          r="10"
                          strokeDasharray="31.4 31.4"
                          strokeLinecap="round"
                        />
                      </svg>
                    ) : (
                      <svg
                        className="w-3 h-3"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        aria-hidden="true"
                      >
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                    {tool.displayName}
                  </span>
                ))}
              </div>
            )}

            {/* Thinking status text */}
            {isStreaming && thinkingMessage && !hasContent && (
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="w-1.5 h-1.5 rounded-full bg-indigo-400 dark:bg-indigo-500 animate-typing-dots"
                      style={{ animationDelay: `${i * 0.2}s` }}
                    />
                  ))}
                </div>
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {thinkingMessage}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Message content */}
        {hasContent && (
          <div className="pg-bubble-agent text-gray-800 dark:text-gray-100">
            <div className={isStreaming ? 'pg-cursor' : ''}>
              <MessageContent content={content} />
            </div>
          </div>
        )}

        {/* Typing dots when waiting for first token and no thinking message */}
        {!hasContent && isStreaming && !thinkingMessage && (
          <div className="pg-bubble-agent">
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-typing-dots"
                    style={{ animationDelay: `${i * 0.2}s` }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default StreamingMessage;
