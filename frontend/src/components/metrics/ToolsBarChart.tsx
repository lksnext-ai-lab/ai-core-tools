import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { ToolBreakdown } from '../../types/metrics';

interface Props {
  tools: ToolBreakdown[];
}

export function ToolsBarChart({ tools }: Props) {
  if (!tools || tools.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-gray-200 bg-white text-sm text-gray-400">
        No tool usage data available for this period.
      </div>
    );
  }

  const data = tools.map((t) => ({
    name: t.tool_name,
    calls: t.calls,
  }));

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">Top Tools by Calls</h3>
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 36)}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, left: 8, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={120} />
          <Tooltip />
          <Bar dataKey="calls" name="Calls" fill="#3b82f6" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
