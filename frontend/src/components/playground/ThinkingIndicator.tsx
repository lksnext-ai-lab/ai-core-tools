import React from 'react';
import type { ActiveTool } from '../../types/streaming';

interface ThinkingIndicatorProps {
  /** Current status message (e.g. "Thinking...", "Searching knowledge base...") */
  message?: string | null;
  /** Tools currently being used */
  activeTools?: ActiveTool[];
}

const ThinkingIndicator: React.FC<ThinkingIndicatorProps> = ({
  message = 'Thinking...',
  activeTools = [],
}) => {
  return (
    <div className="flex justify-start animate-slide-in-left">
      <div className="max-w-md">
        {/* Thinking bubble */}
        <div className="pg-bubble-agent flex items-center gap-3">
          {/* Animated dots */}
          <div className="flex items-center gap-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="w-2 h-2 rounded-full bg-indigo-500 dark:bg-indigo-400 animate-typing-dots"
                style={{ animationDelay: `${i * 0.2}s` }}
              />
            ))}
          </div>
          {/* Status message */}
          {message && (
            <span className="text-sm text-gray-600 dark:text-gray-300 animate-fade-in">
              {message}
            </span>
          )}
        </div>

        {/* Active tools */}
        {activeTools.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2 ml-1">
            {activeTools.map((tool) => (
              <span
                key={`${tool.name}-${tool.startedAt}`}
                className={`${
                  tool.status === 'complete'
                    ? 'pg-tool-pill--complete'
                    : 'pg-tool-pill'
                } animate-fade-in`}
              >
                {tool.status === 'running' ? (
                  <svg
                    className="w-3 h-3 animate-tool-spin"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  >
                    <path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4m-3.93 7.07l-2.83-2.83M7.76 7.76L4.93 4.93" />
                  </svg>
                ) : (
                  <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
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
      </div>
    </div>
  );
};

export default ThinkingIndicator;
