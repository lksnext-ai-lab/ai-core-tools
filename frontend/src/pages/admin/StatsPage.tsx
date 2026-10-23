import { useState, useEffect, useCallback } from 'react';
import { Users, AppWindow, Bot, KeyRound } from 'lucide-react';
import { adminService } from '../../services/admin';
import type { SystemStats } from '../../services/admin';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { errorMessage } from '../../constants/messages';
import { Title } from '../../components/ui/Title';
import Table from '../../components/ui/Table';
import CardApp from '../../components/ui/CardApp';
import { BackgroundImage } from '../..';

function StatsPage() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await adminService.getSystemStats();
      setStats(data);
    } catch (err) {
      setError(errorMessage(err, 'Unable to load system statistics'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Title variant='titPrincipal' titulo='System Statistics' subtitulo='Overview of system usage and activity'></Title>
        </div>
        <LoadingState variant="page" message="Loading statistics..." />
      </div>
    )
  }

  if (error || !stats) {
    return <ErrorState error={error ?? 'Unable to load system statistics'} onRetry={loadStats} />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Title variant='titPrincipal' titulo='System Statistics' subtitulo='Overview of system usage and activity'></Title>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Total Users */}
        <CardApp variant="white">
          {/* Icon + Count */}
          <div className="flex items-start justify-between mb-4">
            <BackgroundImage icon={Users} size={44}
                  variant="marron" className="rounded-xl transition-all duration-200"
            />
            {stats.total_users !== null && (
              <div className="text-right">
                <p className="text-2xl font-bold text-ink dark:dark:text-ink-dark">
                  {stats.total_users}
                </p>
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">total</p>
              </div>
            )}
          </div>
          {/* Title + Subtitle */}
          <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">Users</h3>
          <p className="text-fg-secondary dark:text-fg-secondary-dark text-xs mb-4 flex-1">{stats.active_users} active · {stats.inactive_users} inactive</p>
        </CardApp>

        {/* Total Apps */}
        <CardApp variant="white">
          {/* Icon + Count */}
          <div className="flex items-start justify-between mb-4">
            <BackgroundImage icon={AppWindow} size={44}
                  variant="marron" className="rounded-xl transition-all duration-200"
            />
            {stats.total_apps !== null && (
              <div className="text-right">
                <p className="text-2xl font-bold text-ink dark:dark:text-ink-dark">
                  {stats.total_apps}
                </p>
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">total</p>
              </div>
            )}
          </div>
          {/* Title + Subtitle */}
          <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">Apps</h3>
        </CardApp>

        {/* Total Agents */}
        <CardApp variant="white">
          {/* Icon + Count */}
          <div className="flex items-start justify-between mb-4">
            <BackgroundImage icon={Bot} size={44}
                  variant="marron" className="rounded-xl transition-all duration-200"
            />
            {stats.total_agents !== null && (
              <div className="text-right">
                <p className="text-2xl font-bold text-ink dark:dark:text-ink-dark">
                  {stats.total_agents}
                </p>
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">total</p>
              </div>
            )}
          </div>
          {/* Title + Subtitle */}
          <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">Agents</h3>
        </CardApp>

        {/* API Keys */}
        <CardApp variant="white">
          {/* Icon + Count */}
          <div className="flex items-start justify-between mb-4">
            <BackgroundImage icon={KeyRound} size={44}
                  variant="marron" className="rounded-xl transition-all duration-200"
            />
            {stats.total_api_keys !== null && (
              <div className="text-right">
                <p className="text-2xl font-bold text-ink dark:dark:text-ink-dark">
                  {stats.total_api_keys}
                </p>
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">total</p>
              </div>
            )}
          </div>
          {/* Title + Subtitle */}
          <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">API Keys</h3>
        </CardApp>
      </div>

      {/* Detailed Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* User Status Breakdown */}
        <CardApp className="p-6">
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">User Status</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Active Users</span>
              <span className="text-sm font-medium text-green-600">{stats.active_users}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Inactive Users</span>
              <span className="text-sm font-medium text-red-600">{stats.inactive_users}</span>
            </div>
            <div className="pt-2 border-t border-gray-200">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-fg dark:text-fg-dark">Total Users</span>
                <span className="text-sm font-medium text-fg dark:text-fg-dark">{stats.total_users}</span>
              </div>
            </div>
            <div className="pt-2">
              <div className="flex justify-between items-center text-xs text-fg-secondary dark:text-fg-secondary-dark">
                <span>Active Rate</span>
                <span>{stats.total_users > 0 ? Math.round((stats.active_users / stats.total_users) * 100) : 0}%</span>
              </div>
            </div>
          </div>
        </CardApp>

        {/* API Keys Breakdown */}
        <CardApp className="p-6">
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">API Keys Status</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Active Keys</span>
              <span className="text-sm font-medium text-green-600">{stats.active_api_keys}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Inactive Keys</span>
              <span className="text-sm font-medium text-red-600">{stats.inactive_api_keys}</span>
            </div>
            <div className="pt-2 border-t border-gray-200">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-fg dark:text-fg-dark">Total</span>
                <span className="text-sm font-medium text-fg dark:text-fg-dark">{stats.total_api_keys}</span>
              </div>
            </div>
          </div>
        </CardApp>
      </div>

      {/* Additional Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* User Activity */}
        <CardApp className="p-6">
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">User Activity</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Users with Apps</span>
              <span className="text-sm font-medium text-blue-600">{stats.users_with_apps}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Recent Users (30 days)</span>
              <span className="text-sm font-medium text-green-600">{stats.recent_users.length}</span>
            </div>
            <div className="pt-2 border-t border-gray-200">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-fg dark:text-fg-dark">Active Users</span>
                <span className="text-sm font-medium text-fg dark:text-fg-dark">
                  {Math.round((stats.users_with_apps / stats.total_users) * 100)}%
                </span>
              </div>
            </div>
          </div>
        </CardApp>
      </div>

      {/* Recent Users */}
      <div className="">
        <div className="py-4 ">
          <h3 className="font-display text-lg font-normal text-fg dark:text-fg-dark flex items-center">Recent Users</h3>
          <p className="text-sm text-gray-500 mt-1text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">Users who joined in the last 30 days</p>
        </div>
        
        <Table
          data={stats.recent_users}
          keyExtractor={(user) => user.user_id}
          columns={[
            {
              header: 'User',
              render: (user) => (
                <div className="text-sm font-medium text-fg dark:text-fg-dark">
                  {user.name || 'No name'}
                </div>
              ),
            },
            {
              header: 'Email',
              accessor: 'email',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: 'Joined',
              render: (user) => new Date(user.created_at).toLocaleDateString(),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
          ]}
          rowClassName=""
          emptyMessage="No recent users"
        />
      </div>
    </div>
  );
}

export default StatsPage; 