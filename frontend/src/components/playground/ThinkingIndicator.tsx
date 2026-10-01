import React from 'react';
import type { ActiveTool } from '../../types/streaming';
import ActiveToolBar from './ActiveToolBar';

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
          <ActiveToolBar activeTools={activeTools} className="mt-2 ml-1" />
        )}
      </div>
    </div>
  );
};

export default ThinkingIndicator;
