import React from 'react';
import type { ActiveTool } from '../../types/streaming';
import ActiveToolBar from './ActiveToolBar';
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
              <ActiveToolBar activeTools={activeTools} />
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
