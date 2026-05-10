import { useEffect, useRef, useState } from 'react';
import { Activity, ChevronRight, ChevronLeft, ChevronDown, Terminal, Trash2, Wrench } from 'lucide-react';
import type { ToolExecutionRecord } from '../../hooks/useStreamingChat';

function isCodeTool(toolName: string): boolean {
  return toolName === 'code_interpreter' || toolName.endsWith('_repl');
}

function formatDuration(startedAt: number, endedAt?: number): string {
  const ms = (endedAt ?? Date.now()) - startedAt;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Try to pretty-print a JSON string; return raw string if it's not valid JSON. */
function prettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

/** Label + dark code block used for input/output/stdout sections. */
function CodeBlock({
  label,
  text,
  scrollRef,
  showCursor,
}: Readonly<{
  label: string;
  text: string;
  scrollRef?: React.RefObject<HTMLPreElement | null>;
  showCursor?: boolean;
}>) {
  return (
    <div className="mx-2 mb-2">
      <span className="block text-[9px] font-semibold uppercase tracking-wider text-neutral-400 mb-0.5 px-0.5">
        {label}
      </span>
      <pre
        ref={scrollRef}
        className="max-h-36 overflow-y-auto rounded bg-neutral-900 dark:bg-neutral-950
                   px-2.5 py-1.5 text-[10px] leading-[1.5] text-neutral-200
                   whitespace-pre-wrap break-all font-mono"
      >
        {text}
        {showCursor && (
          <span className="inline-block h-3 w-0.5 bg-neutral-400 animate-pulse align-middle ml-0.5" />
        )}
      </pre>
    </div>
  );
}

function ToolEntryRow({ record }: Readonly<{ record: ToolExecutionRecord }>) {
  const [expanded, setExpanded] = useState(record.status === 'running');
  const previousStatusRef = useRef(record.status);
  const stdoutScrollRef = useRef<HTMLPreElement>(null);
  const isCode = isCodeTool(record.toolName);

  const hasInput = Boolean(record.toolInput);
  const hasOutput = Boolean(record.toolOutput);
  const stdoutLines = record.outputLines
    .filter((entry) => entry.stream === 'stdout')
    .map((entry) => entry.line);
  const stderrLines = record.outputLines
    .filter((entry) => entry.stream === 'stderr')
    .map((entry) => entry.line);
  const hasStdout = stdoutLines.length > 0;
  const hasStderr = stderrLines.length > 0;
  const canExpand = hasInput || hasOutput || hasStdout || hasStderr;

  useEffect(() => {
    const previousStatus = previousStatusRef.current;
    if (record.status === 'running') {
      setExpanded(true);
    } else if (previousStatus === 'running') {
      setExpanded(false);
    }
    previousStatusRef.current = record.status;
  }, [record.status]);

  // Auto-scroll stdout to bottom while running
  useEffect(() => {
    if (record.status === 'running' && expanded && stdoutScrollRef.current) {
      stdoutScrollRef.current.scrollTop = stdoutScrollRef.current.scrollHeight;
    }
  }, [record.outputLines.length, record.status, expanded]);

  // Format the input: Python code for code tools, pretty JSON for others
  const inputDisplay = record.toolInput
    ? isCode ? record.toolInput : prettyJson(record.toolInput)
    : null;

  // Format the output: try pretty JSON first, then raw
  const outputDisplay = record.toolOutput ? prettyJson(record.toolOutput) : null;

  return (
    <div className="border-b border-neutral-100 dark:border-neutral-700/60 last:border-0">
      {/* Row header */}
      <button
        type="button"
        onClick={() => canExpand && setExpanded((v) => !v)}
        className={`w-full flex items-center gap-2 px-3 py-2 text-left transition-colors
          ${canExpand ? 'hover:bg-neutral-50 dark:hover:bg-neutral-800/40 cursor-pointer' : 'cursor-default'}`}
      >
        {isCode ? (
          <Terminal className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
        ) : (
          <Wrench className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
        )}
        <span className="flex-1 text-[11px] font-medium text-neutral-700 dark:text-neutral-300 truncate">
          {record.displayName}
        </span>
        {record.status === 'running' ? (
          <span className="flex items-center gap-1 text-[10px] text-blue-500 shrink-0">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
            running
          </span>
        ) : (
          <span className="text-[10px] text-neutral-400 shrink-0 tabular-nums">
            {formatDuration(record.startedAt, record.endedAt)}
          </span>
        )}
        {canExpand && (
          expanded
            ? <ChevronDown className="h-3 w-3 text-neutral-400 shrink-0" />
            : <ChevronRight className="h-3 w-3 text-neutral-400 shrink-0" />
        )}
      </button>

      {/* Expanded content */}
      {canExpand && expanded && (
        <div className="pb-1">
          {/* Input */}
          {inputDisplay && (
            <CodeBlock
              label={isCode ? 'code' : 'input'}
              text={inputDisplay}
            />
          )}

          {/* Stdout (code tools only) */}
          {hasStdout && (
            <CodeBlock
              label="stdout"
              text={stdoutLines.join('\n')}
              scrollRef={stdoutScrollRef}
              showCursor={record.status === 'running'}
            />
          )}

          {hasStderr && (
            <CodeBlock
              label="stderr"
              text={stderrLines.join('\n')}
              scrollRef={hasStdout ? undefined : stdoutScrollRef}
              showCursor={record.status === 'running' && !hasStdout}
            />
          )}

          {/* Output / result */}
          {outputDisplay && (
            <CodeBlock label="output" text={outputDisplay} />
          )}

          {/* Running: show placeholder when no output yet */}
          {record.status === 'running' && !hasStdout && !outputDisplay && (
            <div className="mx-2 mb-2 text-[10px] text-neutral-400 italic px-0.5">
              waiting for result…
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface ToolHistoryPanelProps {
  history: ToolExecutionRecord[];
  onClear: () => void;
}

export default function ToolHistoryPanel({ history, onClear }: Readonly<ToolHistoryPanelProps>) {
  const [panelOpen, setPanelOpen] = useState(true);
  const runningCount = history.filter((r) => r.status === 'running').length;
  const anyRunning = runningCount > 0;

  // Auto-open when a tool starts running
  useEffect(() => {
    if (anyRunning) setPanelOpen(true);
  }, [anyRunning]);

  if (history.length === 0) return null;

  return (
    <div className={`shrink-0 transition-all duration-200 ${panelOpen ? 'w-72' : 'w-9'}`}>
      <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden h-full">
        {/* Header */}
        <div className="flex items-center gap-1 px-1.5 py-2 border-b border-neutral-100 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/60">
          <button
            type="button"
            onClick={() => setPanelOpen((v) => !v)}
            className="p-1 rounded hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors text-neutral-500"
            aria-label={panelOpen ? 'Collapse tool history panel' : 'Expand tool history panel'}
          >
            {panelOpen
              ? <ChevronRight className="h-3.5 w-3.5" />
              : <ChevronLeft className="h-3.5 w-3.5" />
            }
          </button>

          {panelOpen && (
            <>
              <Activity className="h-3.5 w-3.5 text-neutral-400 shrink-0" />
              <span className="flex-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400 select-none">
                Tool activity
              </span>
              {anyRunning ? (
                <span className="flex items-center gap-1 rounded-full bg-blue-100 dark:bg-blue-900/30 px-1.5 py-0.5 text-[10px] text-blue-600 dark:text-blue-400 shrink-0">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse inline-block" />
                  {runningCount}
                </span>
              ) : (
                <>
                  <span className="text-[10px] text-neutral-400 shrink-0 mr-0.5">{history.length}</span>
                  <button
                    type="button"
                    onClick={onClear}
                    className="p-1 rounded hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors text-neutral-400 hover:text-red-500"
                    aria-label="Clear tool history"
                    title="Clear history"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </>
              )}
            </>
          )}

          {!panelOpen && anyRunning && (
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse shrink-0" />
          )}
        </div>

        {/* Entries */}
        {panelOpen && (
          <div className="max-h-[calc(100vh-24rem)] overflow-y-auto">
            {history.map((record) => (
              <ToolEntryRow key={record.id} record={record} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
