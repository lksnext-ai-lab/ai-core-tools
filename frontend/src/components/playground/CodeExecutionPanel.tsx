import { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Terminal } from 'lucide-react';
import { Badge } from '../ui/Badge';

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
          <Badge
            label="running"
            variant="info"
            icon={<span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-info dark:bg-info-dark" />}
          />
        ) : (
          <Badge
            label={`${lines.length} ${lines.length === 1 ? 'line' : 'lines'}`}
            variant="default"
          />
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
