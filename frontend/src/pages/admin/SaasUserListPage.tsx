import React, { useEffect, useState } from 'react';
import { apiService } from '../../services/api';

interface SaasUser {
  user_id: number;
  email: string;
  name: string | null;
  is_active: boolean;
  tier: string | null;
  billing_status: string | null;
  call_count: number;
  call_limit: number;
  owned_apps_count: number;
}

const TIERS = ['free', 'starter', 'pro'];

const SaasUserListPage: React.FC = () => {
  const [users, setUsers] = useState<SaasUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overridingUserId, setOverridingUserId] = useState<number | null>(null);

  const fetchUsers = async () => {
    setIsLoading(true);
    try {
      const data = await apiService.getAdminSaasUsers();
      setUsers(data as SaasUser[]);
    } catch (err: any) {
      setError(err?.message || 'Failed to load users');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const handleTierOverride = async (userId: number, tier: string) => {
    setOverridingUserId(userId);
    try {
      await apiService.overrideUserTier(userId, tier);
      await fetchUsers();
    } catch (err: any) {
      alert(err?.message || 'Failed to override tier');
    } finally {
      setOverridingUserId(null);
    }
  };

  if (isLoading) return <div className="p-8 text-gray-500">Loading users...</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;

  return (
    <div className="max-w-6xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">SaaS Users</h1>
      <div className="bg-white shadow rounded-lg overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th className="px-4 py-3 text-left">Email</th>
              <th className="px-4 py-3 text-left">Tier</th>
              <th className="px-4 py-3 text-left">Billing</th>
              <th className="px-4 py-3 text-right">LLM usage</th>
              <th className="px-4 py-3 text-right">Apps</th>
              <th className="px-4 py-3 text-left">Override tier</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map(user => (
              <tr key={user.user_id} className="hover:bg-gray-50">
                <td className="px-4 py-3">{user.email}</td>
                <td className="px-4 py-3 capitalize">{user.tier || 'free'}</td>
                <td className="px-4 py-3 capitalize">{user.billing_status || 'none'}</td>
                <td className="px-4 py-3 text-right">{user.call_count} / {user.call_limit}</td>
                <td className="px-4 py-3 text-right">{user.owned_apps_count}</td>
                <td className="px-4 py-3">
                  <select
                    className="border rounded px-2 py-1 text-sm"
                    defaultValue={user.tier || 'free'}
                    disabled={overridingUserId === user.user_id}
                    onChange={e => handleTierOverride(user.user_id, e.target.value)}
                  >
                    {TIERS.map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SaasUserListPage;
