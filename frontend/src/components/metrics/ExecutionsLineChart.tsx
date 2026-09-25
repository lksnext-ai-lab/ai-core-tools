import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { ExecutionBucket, AgentExecutionBucket } from '../../types/metrics';

type Bucket = ExecutionBucket | AgentExecutionBucket;

interface Props {
  series: Bucket[];
  /** When true, the second line is "as_tool" (agent view) instead of "sub" (app view) */
  agentView?: boolean;
}

function formatTs(ts: string): string {
  try {
    const d = new Date(ts);
    const h = d.getUTCHours().toString().padStart(2, '0');
    const m = d.getUTCMinutes().toString().padStart(2, '0');
    if (h === '00' && m === '00') {
      return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
    }
    return `${h}:${m}`;
  } catch {
    return ts;
  }
}

export function ExecutionsLineChart({ series, agentView = false }: Props) {
  if (!series || series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-gray-200 bg-white text-sm text-gray-400">
        No execution data available for this period.
      </div>
    );
  }

  const subKey = agentView ? 'as_tool' : 'sub';
  const subLabel = agentView ? 'As Tool' : 'Sub-calls';

  const data = series.map((b) => {
    const sub = agentView
      ? (b as AgentExecutionBucket).as_tool
      : (b as ExecutionBucket).sub;
    const errors = 'errors' in b ? (b as ExecutionBucket).errors : 0;
    return {
      ts: formatTs(b.ts),
      root: b.root,
      [subKey]: sub ?? 0,
      errors,
    };
  });

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">Executions Over Time</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Line
            type="monotone"
            dataKey="root"
            name="Root calls"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey={subKey}
            name={subLabel}
            stroke="#9ca3af"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
