import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t, i18n } = useTranslation('common');
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
      setError(errorMessage(err, t('systemStatsPage.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Title variant='titPrincipal' titulo={t('systemStatsPage.title')} subtitulo={t('systemStatsPage.subtitle')}></Title>
        </div>
        <LoadingState variant="page" message={t('systemStatsPage.loading')} />
      </div>
    )
  }

  if (error || !stats) {
    return <ErrorState error={error ?? t('systemStatsPage.loadFailed')} onRetry={loadStats} />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Title variant='titPrincipal' titulo={t('systemStatsPage.title')} subtitulo={t('systemStatsPage.subtitle')}></Title>

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
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">{t('systemStatsPage.total')}</p>
              </div>
            )}
          </div>
          {/* Title + Subtitle */}
          <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">{t('systemStatsPage.users')}</h3>
          <p className="text-fg-secondary dark:text-fg-secondary-dark text-xs mb-4 flex-1">{t('systemStatsPage.activeInactiveUsers', { active: stats.active_users, inactive: stats.inactive_users })}</p>
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
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">{t('systemStatsPage.total')}</p>
              </div>
            )}
          </div>
          {/* Title + Subtitle */}
          <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">{t('systemStatsPage.apps')}</h3>
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
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">{t('systemStatsPage.total')}</p>
              </div>
            )}
          </div>
          {/* Title + Subtitle */}
          <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">{t('systemStatsPage.agents')}</h3>
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
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">{t('systemStatsPage.total')}</p>
              </div>
            )}
          </div>
          {/* Title + Subtitle */}
          <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">{t('systemStatsPage.apiKeys')}</h3>
        </CardApp>
      </div>

      {/* Detailed Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* User Status Breakdown */}
        <CardApp className="p-6">
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">{t('systemStatsPage.userStatus')}</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('systemStatsPage.activeUsers')}</span>
              <span className="text-sm font-medium text-green-600">{stats.active_users}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('systemStatsPage.inactiveUsers')}</span>
              <span className="text-sm font-medium text-red-600">{stats.inactive_users}</span>
            </div>
            <div className="pt-2 border-t border-gray-200">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-fg dark:text-fg-dark">{t('systemStatsPage.totalUsers')}</span>
                <span className="text-sm font-medium text-fg dark:text-fg-dark">{stats.total_users}</span>
              </div>
            </div>
            <div className="pt-2">
              <div className="flex justify-between items-center text-xs text-fg-secondary dark:text-fg-secondary-dark">
                <span>{t('systemStatsPage.activeRate')}</span>
                <span>{stats.total_users > 0 ? Math.round((stats.active_users / stats.total_users) * 100) : 0}%</span>
              </div>
            </div>
          </div>
        </CardApp>

        {/* API Keys Breakdown */}
        <CardApp className="p-6">
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">{t('systemStatsPage.apiKeysStatus')}</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('systemStatsPage.activeKeys')}</span>
              <span className="text-sm font-medium text-green-600">{stats.active_api_keys}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('systemStatsPage.inactiveKeys')}</span>
              <span className="text-sm font-medium text-red-600">{stats.inactive_api_keys}</span>
            </div>
            <div className="pt-2 border-t border-gray-200">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-fg dark:text-fg-dark">{t('systemStatsPage.total')}</span>
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
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">{t('systemStatsPage.userActivity')}</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('systemStatsPage.usersWithApps')}</span>
              <span className="text-sm font-medium text-blue-600">{stats.users_with_apps}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('systemStatsPage.recentUsers30Days')}</span>
              <span className="text-sm font-medium text-green-600">{stats.recent_users.length}</span>
            </div>
            <div className="pt-2 border-t border-gray-200">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-fg dark:text-fg-dark">{t('systemStatsPage.activeUsers')}</span>
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
          <h3 className="font-display text-lg font-normal text-fg dark:text-fg-dark flex items-center">{t('systemStatsPage.recentUsers')}</h3>
          <p className="text-sm text-gray-500 mt-1text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">{t('systemStatsPage.recentUsersDescription')}</p>
        </div>
        
        <Table
          data={stats.recent_users}
          keyExtractor={(user) => user.user_id}
          columns={[
            {
              header: t('systemStatsPage.user'),
              render: (user) => (
                <div className="text-sm font-medium text-fg dark:text-fg-dark">
                  {user.name || t('systemStatsPage.noName')}
                </div>
              ),
            },
            {
              header: t('systemStatsPage.email'),
              accessor: 'email',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: t('systemStatsPage.joined'),
              render: (user) => new Date(user.created_at).toLocaleDateString(i18n.language),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
          ]}
          rowClassName=""
          emptyMessage={t('systemStatsPage.noRecentUsers')}
        />
      </div>
    </div>
  );
}

export default StatsPage; 