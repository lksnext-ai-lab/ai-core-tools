import React from 'react';
import type { ActiveTool } from '../../types/streaming';

interface ActiveToolBarProps {
  activeTools: ActiveTool[];
  className?: string;
}

interface ToolGroup {
  key: string;
  label?: string;
  tools: ActiveTool[];
}

function getGroupKey(tool: ActiveTool): string {
  if (!tool.subagentName) return 'main';
  return `subagent:${tool.subagentId ?? 'unknown'}:${tool.subagentName}:${tool.parentToolName ?? ''}`;
}

function groupActiveTools(activeTools: ActiveTool[]): ToolGroup[] {
  const groups: ToolGroup[] = [];
  const groupIndex = new Map<string, number>();

  activeTools.forEach((tool) => {
    const key = getGroupKey(tool);
    const existingIndex = groupIndex.get(key);

    if (existingIndex !== undefined) {
      groups[existingIndex].tools.push(tool);
      return;
    }

    groupIndex.set(key, groups.length);
    groups.push({
      key,
      label: tool.subagentName,
      tools: [tool],
    });
  });

  return groups;
}

function ToolStatusIcon({ status }: Readonly<{ status: ActiveTool['status'] }>) {
  if (status === 'running') {
    return (
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
    );
  }

  return (
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
  );
}

function ToolPill({ tool }: Readonly<{ tool: ActiveTool }>) {
  return (
    <span
      className={`pg-tool-pill animate-fade-in ${
        tool.status === 'complete' ? 'pg-tool-pill--complete' : ''
      }`}
    >
      <ToolStatusIcon status={tool.status} />
      {tool.displayName}
    </span>
  );
}

export default function ActiveToolBar({
  activeTools,
  className = '',
}: Readonly<ActiveToolBarProps>) {
  if (activeTools.length === 0) return null;

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`}>
      {groupActiveTools(activeTools).map((group) => {
        if (!group.label) {
          return group.tools.map((tool) => (
            <ToolPill key={`${tool.name}-${tool.startedAt}`} tool={tool} />
          ));
        }

        return (
          <div key={group.key} className="pg-tool-group animate-fade-in">
            <span className="pg-tool-group-label truncate">{group.label}</span>
            <div className="flex flex-wrap items-center gap-1">
              {group.tools.map((tool) => (
                <ToolPill key={`${tool.name}-${tool.startedAt}`} tool={tool} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
