import { AlertTriangle } from 'lucide-react';
import type { ErrorsResponse } from '../../types/metrics';
import { ChartCard } from './TimeseriesCharts';
import { formatCount, formatDateTime } from './format';

interface Props {
  errors: ErrorsResponse | null;
  /** Show the app next to the agent (system view spans apps). */
  showApp?: boolean;
}

export function ErrorsPanel({ errors, showApp = false }: Props) {
  return (
    <ChartCard title="Errors" subtitle="Failed executions grouped by error type, and the latest failures">
      {!errors && <p className="py-6 text-center text-sm text-gray-400">Loading…</p>}
      {errors && errors.groups.length === 0 && (
        <p className="py-6 text-center text-sm text-gray-400 dark:text-gray-500">No failed executions in this period.</p>
      )}
      {errors && errors.groups.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
          <ul className="space-y-2">
            {errors.groups.map((g) => (
              <li key={g.error_code} className="rounded-lg border border-gray-100 p-3 dark:border-gray-700">
                <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5">
                  <span className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold text-gray-900 dark:text-gray-100">
                    <AlertTriangle className="h-3.5 w-3.5 text-red-600 dark:text-red-400" aria-hidden />
                    {g.error_code}
                  </span>
                  <span className="whitespace-nowrap text-xs tabular-nums text-gray-500 dark:text-gray-400">
                    {formatCount(g.count)} · last {formatDateTime(g.last_seen)}
                  </span>
                </div>
                {g.sample_message && (
                  <p className="mt-1 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">{g.sample_message}</p>
                )}
              </li>
            ))}
          </ul>
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Latest failures</h4>
            <ul className="divide-y divide-gray-100 text-sm dark:divide-gray-700">
              {errors.recent.map((r, i) => (
                <li key={`${r.started_at}-${i}`} className="py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium text-gray-800 dark:text-gray-100">
                      {r.agent_name ?? `Agent #${r.agent_id}`}
                      {showApp && <span className="font-normal text-gray-500 dark:text-gray-400"> · {r.app_name ?? `App #${r.app_id}`}</span>}
                    </span>
                    <span className="whitespace-nowrap text-xs text-gray-500 dark:text-gray-400">{formatDateTime(r.started_at)}</span>
                  </div>
                  <p className="truncate text-xs text-gray-500 dark:text-gray-400" title={r.error_message ?? undefined}>
                    <span className="font-mono">{r.error_code ?? 'UNKNOWN'}</span>
                    {r.error_message ? ` — ${r.error_message}` : ''}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </ChartCard>
  );
}
