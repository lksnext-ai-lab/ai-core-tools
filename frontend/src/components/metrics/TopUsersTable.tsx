import type { UserBreakdown } from '../../types/metrics';

interface Props {
  users: UserBreakdown[];
}

export function TopUsersTable({ users }: Props) {
  if (!users || users.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center rounded-xl border border-gray-200 bg-white text-sm text-gray-400">
        No user data available.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">Top Users</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
            <th className="pb-2 font-medium">User</th>
            <th className="pb-2 font-medium text-right">Executions</th>
            <th className="pb-2 font-medium text-right">Total Tokens</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {users.map((u, idx) => (
            <tr key={u.user_id ?? idx} className="hover:bg-gray-50">
              <td className="py-2 text-gray-700">
                {u.user_name ?? <span className="italic text-gray-400">(deleted)</span>}
              </td>
              <td className="py-2 text-right tabular-nums text-gray-700">
                {u.executions.toLocaleString()}
              </td>
              <td className="py-2 text-right tabular-nums text-gray-700">
                {u.total_tokens.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
