import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Ban, ChevronDown, ChevronUp, Clock, Pencil, Terminal, Trash2 } from 'lucide-react';
import type { ToolExecutionRecord } from '../../hooks/useStreamingChat';
import { formatDuration } from '../../utils/duration';

function isCodeTool(toolName: string): boolean {
  return toolName === 'code_interpreter' || toolName.endsWith('_repl');
}

/** Try to pretty-print a JSON string; return raw string if it's not valid JSON. */
function prettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function formatToolName(toolName: string): string {
  return toolName.replaceAll('_', ' ');
}

function getHistoryGroupKey(record: ToolExecutionRecord): string {
  if (!record.subagentName) return 'main';
  return `subagent:${record.subagentId ?? 'unknown'}:${record.subagentName}:${record.parentToolName ?? ''}`;
}

interface ToolHistoryGroup {
  key: string;
  label?: string;
  records: ToolExecutionRecord[];
}

function groupHistoryRecords(history: ToolExecutionRecord[]): ToolHistoryGroup[] {
  const groups: ToolHistoryGroup[] = [];

  history.forEach((record) => {
    const key = getHistoryGroupKey(record);
    const lastGroup = groups[groups.length - 1];

    if (lastGroup?.key === key) {
      lastGroup.records.push(record);
      return;
    }

    groups.push({
      key,
      label: record.subagentName,
      records: [record],
    });
  });

  return groups;
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
    <div className="mb-3 last:mb-0">
      <span className="mb-1.5 mt-0.5 block text-[11px] font-semibold uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark">
        {label}
      </span>
      <pre
        ref={scrollRef}
        className="m-0 max-h-56 overflow-y-auto rounded-lg border border-[#33302a] bg-[#1c1b18]
                   px-3.5 py-3 font-mono text-[12px] leading-[1.6] text-[#f2efe9]
                   whitespace-pre-wrap break-all"
      >
        {text}{' '}
        {showCursor && (
          <span className="ml-0.5 inline-block h-3 w-0.5 animate-pulse bg-[#b9b3a4] align-middle" />
        )}
      </pre>
    </div>
  );
}

function ToolEntryRow({
  record,
  hideSubagentName = false,
}: Readonly<{
  record: ToolExecutionRecord;
  hideSubagentName?: boolean;
}>) {
  const { t } = useTranslation('common');
  const [expanded, setExpanded] = useState(record.status === 'running' || record.status === 'awaiting_approval');
  const previousStatusRef = useRef(record.status);
  const stdoutScrollRef = useRef<HTMLPreElement>(null);
  const isCode = isCodeTool(record.toolName);
  const displayName = hideSubagentName && record.subagentName
    ? formatToolName(record.toolName)
    : record.displayName;

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
    if (record.status === 'running' || record.status === 'awaiting_approval') {
      setExpanded(true);
    } else if (previousStatus === 'running' || previousStatus === 'awaiting_approval') {
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

  const elapsed = record.status === 'complete'
    ? formatDuration((record.endedAt ?? Date.now()) - record.startedAt, {
        showMillisecondsBelowSecond: true,
      })
    : null;

  return (
    <div className="border-t border-line dark:border-line-dark">
      {/* Row header */}
      <button
        type="button"
        onClick={() => canExpand && setExpanded((v) => !v)}
        aria-expanded={canExpand ? expanded : undefined}
        className={`flex w-full items-center justify-between gap-2.5 py-2.5 text-left
          ${canExpand ? 'cursor-pointer' : 'cursor-default'}`}
      >
        <span className="min-w-0">
          <span className="flex items-center gap-1.5 text-[13px] font-medium text-fg dark:text-fg-dark">
            {isCode && <Terminal className="h-3.5 w-3.5 shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />}
            <span className="truncate">{displayName}</span>
          </span>
          <span className="flex flex-wrap items-center gap-x-1 text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark">
            {elapsed && <span className="tabular-nums">{elapsed} ·</span>}
            {record.status === 'complete' && (
              <span className="text-success-strong dark:text-success-strong-dark">{t('toolHistory.completed')}</span>
            )}
            {record.status === 'running' && (
              <span className="inline-flex items-center gap-1 text-info dark:text-info-dark">
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                {t('toolHistory.running')}
              </span>
            )}
            {record.status === 'awaiting_approval' && (
              <span className="inline-flex items-center gap-1 text-bronze dark:text-bronze-dark">
                <Clock className="h-3 w-3" aria-hidden="true" />
                {t('toolHistory.awaitingApproval')}
              </span>
            )}
            {(record.status === 'rejected' || record.status === 'expired' || record.status === 'cancelled') && (
              <span className="inline-flex items-center gap-1 text-error dark:text-error-dark">
                <Ban className="h-3 w-3" aria-hidden="true" />
                {record.status === 'rejected'
                  ? t('toolHistory.rejected')
                  : t('toolHistory.notRun', { status: t(`toolHistory.status.${record.status}`) })}
              </span>
            )}
            {record.edited && (
              <span className="inline-flex items-center gap-0.5">
                · <Pencil className="h-2.5 w-2.5" aria-hidden="true" />
                {t('toolHistory.edited')}
              </span>
            )}
          </span>
        </span>
        {canExpand && (
          expanded
            ? <ChevronUp className="h-4 w-4 shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
            : <ChevronDown className="h-4 w-4 shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
        )}
      </button>

      {/* Expanded content */}
      {canExpand && expanded && (
        <div className="pb-3">
          {/* Input */}
          {inputDisplay && (
            <CodeBlock
              label={isCode ? t('toolHistory.labels.code') : t('toolHistory.labels.input')}
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
            <CodeBlock
              label={record.status === 'rejected' ? t('toolHistory.labels.reason') : t('toolHistory.labels.output')}
              text={outputDisplay}
            />
          )}

          {/* Running: show placeholder when no output yet */}
          {record.status === 'running' && !hasStdout && !outputDisplay && (
            <div className="text-[12px] italic text-fg-tertiary dark:text-fg-tertiary-dark">
              {t('toolHistory.waitingForResult')}
            </div>
          )}

          {record.status === 'awaiting_approval' && (
            <div className="text-[12px] italic text-fg-tertiary dark:text-fg-tertiary-dark">
              {t('toolHistory.waitingForApproval')}
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
  const { t } = useTranslation('common');
  const [panelOpen, setPanelOpen] = useState(true);
  const runningCount = history.filter((r) => r.status === 'running').length;
  const anyRunning = runningCount > 0;

  // Auto-open when a tool starts running
  useEffect(() => {
    if (anyRunning) setPanelOpen(true);
  }, [anyRunning]);

  if (history.length === 0) return null;
  const groupedHistory = groupHistoryRecords(history);

  return (
    <section
      aria-label={t('toolHistory.title')}
      className="rounded-lg border border-line p-3.5 dark:border-line-dark"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <h2 className="m-0 font-display text-[15px] font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">
          {t('toolHistory.title')}{' '}
          <span className="font-sans text-[12px] tracking-normal text-fg-tertiary dark:text-fg-tertiary-dark">
            {history.length}
          </span>
        </h2>
        <span className="flex flex-none items-center gap-1">
          {anyRunning ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-info-bg px-2 py-0.5 text-[11px] text-info dark:bg-info-bg-dark dark:text-info-dark">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              {runningCount}
            </span>
          ) : (
            <button
              type="button"
              onClick={onClear}
              className="rounded p-1 text-fg-tertiary transition-colors hover:text-error dark:text-fg-tertiary-dark dark:hover:text-error-dark"
              aria-label={t('toolHistory.clearHistory')}
              title={t('toolHistory.clearHistory')}
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setPanelOpen((v) => !v)}
            aria-expanded={panelOpen}
            className="rounded p-1 text-fg-secondary transition-colors hover:text-fg dark:text-fg-secondary-dark dark:hover:text-fg-dark"
            aria-label={panelOpen
              ? t('toolHistory.collapsePanel')
              : t('toolHistory.expandPanel')}
          >
            {panelOpen
              ? <ChevronUp className="h-4 w-4" aria-hidden="true" />
              : <ChevronDown className="h-4 w-4" aria-hidden="true" />}
          </button>
        </span>
      </div>

      {/* Entries */}
      {panelOpen && (
        <div className="mt-2.5">
          {groupedHistory.map((group) => {
            if (!group.label) {
              return group.records.map((record) => (
                <ToolEntryRow key={record.id} record={record} />
              ));
            }

            return (
              <div
                key={`${group.key}-${group.records[0]?.id}`}
                className="my-1.5 overflow-hidden rounded-md border border-line dark:border-line-dark"
              >
                <div className="flex items-center gap-1.5 bg-surface-hover px-2.5 py-1.5 dark:bg-surface-hover-dark">
                  <span className="min-w-0 flex-1 truncate text-[11px] font-semibold uppercase tracking-[0.05em] text-fg-secondary dark:text-fg-secondary-dark">
                    {group.label}
                  </span>
                  <span className="text-[11px] text-fg-tertiary dark:text-fg-tertiary-dark">
                    {group.records.length}
                  </span>
                </div>
                <div className="px-2.5">
                  {group.records.map((record) => (
                    <ToolEntryRow
                      key={record.id}
                      record={record}
                      hideSubagentName
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
