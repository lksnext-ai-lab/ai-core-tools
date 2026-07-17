import { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Terminal } from 'lucide-react';

interface CodeExecutionPanelProps {
  lines: string[];
  isRunning: boolean;
}

const CodeExecutionPanel: React.FC<CodeExecutionPanelProps> = ({ lines, isRunning }) => {
  const [expanded, setExpanded] = useState(true);
  const scrollRef = useRef<HTMLPreElement>(null);

  // Expand when execution starts; collapse when it finishes.
  useEffect(() => {
    if (isRunning) {
      setExpanded(true);
    } else if (lines.length > 0) {
      setExpanded(false);
    }
  }, [isRunning]);

  // Auto-scroll to bottom while running.
  useEffect(() => {
    if (isRunning && expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines, isRunning, expanded]);

  if (lines.length === 0) return null;

  return (
    <div className="my-2 rounded-lg border border-neutral-700 bg-neutral-900 text-xs font-mono overflow-hidden">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-neutral-300 hover:bg-neutral-800 transition-colors"
      >
        <Terminal className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
        <span className="flex-1 text-left text-[11px] font-semibold tracking-wide uppercase text-neutral-400">
          Code output
        </span>
        {isRunning ? (
          <span className="flex items-center gap-1 rounded-full bg-blue-900/50 px-2 py-0.5 text-blue-300 text-[10px]">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
            running
          </span>
        ) : (
          <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-neutral-400 text-[10px]">
            {lines.length} {lines.length === 1 ? 'line' : 'lines'}
          </span>
        )}
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-neutral-500" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-neutral-500" />
        )}
      </button>

      {/* Scrollable output */}
      {expanded && (
        <pre
          ref={scrollRef}
          className="max-h-48 overflow-y-auto px-3 py-2 text-neutral-200 leading-5 whitespace-pre-wrap break-all"
        >
          {lines.map((line, i) => (
            <span key={i} className="block">
              {line}
            </span>
          ))}
          {isRunning && (
            <span className="inline-block h-3.5 w-1.5 animate-pulse bg-neutral-400 align-middle" />
          )}
        </pre>
      )}
    </div>
  );
};

export default CodeExecutionPanel;
