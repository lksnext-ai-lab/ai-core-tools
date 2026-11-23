import React, { useCallback, useEffect, useState } from 'react';
import { apiService } from '../../services/api';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import { Title } from '../../components/ui/Title';
import { useTranslation } from 'react-i18next';
import { Users } from 'lucide-react';
import Table, { type TableColumn } from '../../components/ui/Table';
import BackgroundImage from '../../components/ui/BackgroundImage';
import { FormSelect } from '../../components/ui/FormField';

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
  const { t } = useTranslation('common');
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
      setError(errorMessage(err, t('saasUserListPage.loadFailed')));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchUsers();
  }, [fetchUsers]);

  const handleTierOverride = async (userId: number, tier: string) => {
    setOverridingUserId(userId);
    const result = await mutate(
      () => apiService.overrideUserTier(userId, tier),
      {
        loading: t('saasUserListPage.notifications.updatingTier'),
        success: t('saasUserListPage.notifications.tierUpdated'),
        error: (err) => errorMessage(err, t('saasUserListPage.notifications.overrideFailed')),
      },
    );
    setOverridingUserId(null);
    if (result === undefined) return;
    await fetchUsers();
  };

  const tierLabel = (tier: string | null) => {
    const value = tier || 'free';
    return t(`saasUserListPage.tiers.${value}`, { defaultValue: value });
  };
  const billingStatusLabel = (status: string | null) => {
    const value = status || 'none';
    return t(`saasUserListPage.billingStatuses.${value}`, { defaultValue: value });
  };

  const columns: TableColumn<SaasUser>[] = [
    {
      header: t('saasUserListPage.columns.email'),
      accessor: 'email',
      className: 'px-6 py-4 whitespace-nowrap text-sm font-medium text-fg dark:text-fg-dark',
    },
    {
      header: t('saasUserListPage.columns.tier'),
      render: (user) => tierLabel(user.tier),
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('saasUserListPage.columns.billing'),
      render: (user) => billingStatusLabel(user.billing_status),
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('saasUserListPage.columns.llmUsage'),
      render: (user) => `${user.call_count} / ${user.call_limit}`,
      headerClassName: 'text-right',
      className: 'px-6 py-4 whitespace-nowrap text-right text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('saasUserListPage.columns.apps'),
      accessor: 'owned_apps_count',
      headerClassName: 'text-right',
      className: 'px-6 py-4 whitespace-nowrap text-right text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('saasUserListPage.columns.overrideTier'),
      sticky: 'right',
      className: 'px-4 py-4 min-w-40',
      render: (user) => (
        <FormSelect
          id={`saas-user-tier-${user.user_id}`}
          label={t('saasUserListPage.actions.overrideTierForUser', { email: user.email })}
          labelClassName="sr-only"
          value={user.tier || 'free'}
          disabled={overridingUserId === user.user_id}
          onChange={(event) => {
            void handleTierOverride(user.user_id, event.target.value);
          }}
          options={TIERS.map((tier) => ({ value: tier, label: tierLabel(tier) }))}
        />
      ),
    },
  ];

  if (isLoading) return <LoadingState message={t('saasUserListPage.loading')} />;
  if (error) return <ErrorState error={error} onRetry={fetchUsers} />;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <Title
        titulo={t('saasUserListPage.title')}
        subtitulo={t('saasUserListPage.subtitle')}
      />
      <Table
        columns={columns}
        data={users}
        keyExtractor={(user) => user.user_id}
        stickyEdgeColumns
        emptyIcon={<BackgroundImage icon={Users} size={64} iconSize={32} />}
        emptyMessage={t('saasUserListPage.empty')}
      />
    </div>
  );
};

export default SaasUserListPage;
