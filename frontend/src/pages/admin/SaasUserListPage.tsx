import React, { useCallback, useEffect, useState } from 'react';
import { apiService } from '../../services/api';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';

interface SaasUser {
  readonly user_id: number;
  readonly email: string;
  readonly name: string | null;
  readonly is_active: boolean;
  readonly tier: string | null;
  readonly billing_status: string | null;
  readonly call_count: number;
  readonly call_limit: number;
  readonly owned_apps_count: number;
}

const TIERS = ['free', 'starter', 'pro'] as const;

const SaasUserListPage: React.FC = () => {
  const mutate = useApiMutation();
  const [users, setUsers] = useState<SaasUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overridingUserId, setOverridingUserId] = useState<number | null>(null);

  const fetchUsers = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = (await apiService.getAdminSaasUsers()) as SaasUser[];
      setUsers(data);
    } catch (err) {
      setError(errorMessage(err, 'Failed to load users'));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleTierOverride = async (userId: number, tier: string) => {
    setOverridingUserId(userId);
    const result = await mutate(
      () => apiService.overrideUserTier(userId, tier),
      {
        loading: 'Updating tier…',
        success: 'Tier updated',
        error: (err) => errorMessage(err, 'Failed to override tier'),
      },
    );
    setOverridingUserId(null);
    if (result === undefined) return;
    await fetchUsers();
  };

  if (isLoading) return <LoadingState message="Loading users..." />;
  if (error) return <ErrorState error={error} onRetry={fetchUsers} />;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">SaaS Users</h1>
        <p className="text-gray-600">Manage tiers and quotas for SaaS-mode users</p>
      </div>

      <div className="bg-white rounded-lg shadow overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Email
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Tier
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Billing
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                LLM usage
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Apps
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Override tier
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {users.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">
                  No SaaS users found.
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr key={user.user_id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{user.email}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm capitalize text-gray-700">
                    {user.tier || 'free'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm capitalize text-gray-700">
                    {user.billing_status || 'none'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-700">
                    {user.call_count} / {user.call_limit}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-700">
                    {user.owned_apps_count}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <select
                      className="border border-gray-300 rounded-md px-2 py-1 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
                      defaultValue={user.tier || 'free'}
                      disabled={overridingUserId === user.user_id}
                      onChange={(e) => handleTierOverride(user.user_id, e.target.value)}
                    >
                      {TIERS.map((tier) => (
                        <option key={tier} value={tier}>
                          {tier}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SaasUserListPage;
