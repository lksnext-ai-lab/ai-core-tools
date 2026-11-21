import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Mail, Handshake, Crown, BarChart2, LogOut } from 'lucide-react';
import { useUser } from '../contexts/UserContext';
import { useConfirm } from '../contexts/ConfirmContext';
import { apiService } from '../services/api';
import Alert from '../components/ui/Alert';
import type { MarketplaceQuotaUsage } from '../types/marketplace';
import { LoadingState } from '../components/ui/LoadingState';
import { Spinner } from '../components/ui/Spinner';
import Title from '../components/ui/Title';
import CardApp from '../components/ui/CardApp';
import ButtonApp from '../components/ui/ButtonApp';
import BackgroundImage from '../components/ui/BackgroundImage';
import { Badge, StatusBadge, type BadgeVariant } from '../components/ui/Badge';
import UserAvatar from '../components/ui/UserAvatar';
import ImageUploadControl from '../components/ui/ImageUploadControl';

interface App {
  app_id: number;
  name: string;
  role: string;
  owner_name?: string;
  owner_email?: string;
}

interface PendingInvitation {
  id: number;
  app_id: number;
  app_name: string;
  inviter_email: string;
  role: string;
  invited_at: string;
}

const ROLE_BADGE_VARIANTS: Record<string, BadgeVariant> = {
  administrator: 'secondary',
  editor: 'info',
  viewer: 'default',
};

const LIST_CLASSES = 'divide-y divide-line dark:divide-line-dark';
const LIST_ITEM_CLASSES = 'py-3 first:pt-0 last:pb-0';

interface EmptyListProps {
  readonly icon: typeof Mail;
  readonly message: string;
}

function EmptyList({ icon, message }: EmptyListProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center">
      <BackgroundImage icon={icon} size={64} iconSize={32} />
      <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{message}</p>
    </div>
  );
}

const ProfilePage: React.FC = () => {
  const { t, i18n } = useTranslation('common');
  const confirm = useConfirm();
  const { user, loading: userLoading, avatarUrl, setUser } = useUser();
  const [collaborations, setCollaborations] = useState<App[]>([]);
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [quotaUsage, setQuotaUsage] = useState<MarketplaceQuotaUsage | null>(null);

  useEffect(() => {
    if (user) {
      void loadData();
    }
  }, [user]);

  async function loadData() {
    try {
      setLoading(true);
      const [appsData, invitationsData] = await Promise.all([
        apiService.getApps(),
        apiService.getPendingInvitations()
      ]);

      // Filter apps where user is not owner
      const collabs = appsData.filter((app: any) => app.role !== 'owner');
      setCollaborations(collabs);
      setInvitations(invitationsData);
    } catch (err) {
      console.error(err);
      // Don't show error if it's just empty data or minor issue
    } finally {
      setLoading(false);
    }

    try {
      const quotaData = await apiService.getMarketplaceQuotaUsage();
      setQuotaUsage(quotaData);
    } catch (err) {
      // Quota fetch is non-critical; silently ignore
      console.error('Failed to fetch marketplace quota usage', err);
    }
  }

  async function handleRespond(invitationId: number, action: 'accept' | 'decline') {
    try {
      await apiService.respondToInvitation(invitationId, action);
      setSuccess(t(`collaborationPage.pendingInvitations.${action}Success`));
      void loadData();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.error(err);
      setError(t(`collaborationPage.pendingInvitations.${action}Failed`));
      setTimeout(() => setError(null), 3000);
    }
  }

  async function handleLeaveApp(appId: number, appName: string) {
    // Same wording as the apps list, including what happens to the member's Chat data.
    const confirmed = await confirm({
      title: t('appsPage.confirmLeaveTitle'),
      message: t('appsPage.confirmLeaveMessage', { name: appName }),
      confirmLabel: t('appsPage.actions.leaveApp'),
      cancelLabel: t('cancel'),
      variant: 'warning',
    });
    if (!confirmed) return;
    try {
      await apiService.leaveApp(appId);
      setSuccess(t('appsPage.appLeftSuccessfully', { name: appName }));
      void loadData();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.error(err);
      setError(t('appsPage.appLeaveFailed', { name: appName }));
      setTimeout(() => setError(null), 3000);
    }
  }

  function showError(message: string) {
    setError(message);
    setTimeout(() => setError(null), 3000);
  }

  function showSuccess(message: string) {
    setSuccess(message);
    setTimeout(() => setSuccess(null), 3000);
  }

  async function uploadAvatar(file: File) {
    if (!user) return;
    const { image_updated_at } = await apiService.uploadMyAvatar(file);
    setUser({ ...user, avatar_updated_at: image_updated_at });
  }

  async function removeAvatar() {
    if (!user) return;
    await apiService.deleteMyAvatar();
    setUser({ ...user, avatar_updated_at: null });
  }

  const getRoleLabel = (role: string) => t(`collaborationPage.roles.${role.toLowerCase()}`, {
    defaultValue: role.charAt(0).toUpperCase() + role.slice(1),
  });

  const getRoleBadgeVariant = (role: string): BadgeVariant => ROLE_BADGE_VARIANTS[role.toLowerCase()] ?? 'default';

  const renderQuotaContent = () => {
    if (!quotaUsage) {
      return (
        <div className="flex items-center gap-2 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
          <Spinner size="sm" tone="muted" />
          <span>{t('profilePage.usage.loading')}</span>
        </div>
      );
    }
    if (quotaUsage.is_exempt) {
      return <Badge variant="info" label={t('profilePage.usage.exempt')} />;
    }
    if (quotaUsage.quota === 0) {
      return (
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          <span className="font-medium text-fg dark:text-fg-dark">{quotaUsage.call_count}</span> / {t('profilePage.usage.unlimited')}
        </p>
      );
    }
    const atLimit = quotaUsage.call_count >= quotaUsage.quota;
    const percentage = Math.min(100, (quotaUsage.call_count / quotaUsage.quota) * 100);
    return (
      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className={`text-sm font-medium ${atLimit ? 'text-error dark:text-error-dark' : 'text-fg dark:text-fg-dark'}`}>
            {quotaUsage.call_count} / {quotaUsage.quota}
          </p>
          {atLimit && <Badge variant="error" label={t('profilePage.usage.limitReached')} />}
        </div>
        <div
          role="progressbar"
          aria-label={t('profilePage.usage.title')}
          aria-valuemin={0}
          aria-valuemax={quotaUsage.quota}
          aria-valuenow={Math.min(quotaUsage.call_count, quotaUsage.quota)}
          className="h-2 overflow-hidden rounded-full bg-surface-hover dark:bg-surface-hover-dark"
        >
          <div
            className={`h-2 rounded-full transition-all ${atLimit ? 'bg-error dark:bg-error-dark' : 'bg-ink dark:bg-ink-dark'}`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    );
  };

  if (userLoading) {
    return (
      <LoadingState variant="page" />
    );
  }

  if (!user) {
    return (
      <Alert type="error" message={t('profilePage.userNotFound')} />
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {success && <Alert type="success" message={success} onDismiss={() => setSuccess(null)} />}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      <Title variant="titSecundario" titulo={t('profilePage.title')} subtitulo={t('profilePage.subtitle')} />

      {/* Profile Header */}
      <CardApp className="p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-4">
            <UserAvatar name={user.name} email={user.email} src={avatarUrl} size={64} />
            <div className="min-w-0">
              <h2 className="truncate font-display text-xl font-medium text-fg dark:text-fg-dark">{user.name || t('header.userFallback')}</h2>
              <p className="truncate text-sm text-fg-secondary dark:text-fg-secondary-dark">{user.email}</p>
            </div>
          </div>
          <ImageUploadControl
            className="sm:items-end"
            hasImage={Boolean(user.avatar_updated_at)}
            inputLabel={t('profilePage.avatar.inputLabel')}
            onUpload={uploadAvatar}
            onRemove={removeAvatar}
            onSuccess={showSuccess}
            onError={showError}
          />
        </div>

        <dl className="mt-6 grid grid-cols-1 gap-4 border-t border-line pt-6 dark:border-line-dark sm:grid-cols-3">
          <div>
            <dt className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('profilePage.account.userId')}</dt>
            <dd className="mt-1 text-sm font-medium text-fg dark:text-fg-dark">#{user.user_id}</dd>
          </div>
          <div>
            <dt className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('profilePage.account.type')}</dt>
            <dd className="mt-1 text-sm font-medium text-fg dark:text-fg-dark">{t('profilePage.account.standardUser')}</dd>
          </div>
          <div>
            <dt className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('profilePage.account.status')}</dt>
            <dd className="mt-1">
              <StatusBadge status="active" customLabel={t('collaborationPage.status.active')} />
            </dd>
          </div>
        </dl>
      </CardApp>

      {/* Marketplace Call Usage */}
      <CardApp
        className="p-6"
        icon={BarChart2}
        titulo={t('profilePage.usage.title')}
        subtitulo={t('profilePage.usage.subtitle')}
      >
        {renderQuotaContent()}
      </CardApp>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Pending Invitations */}
        <CardApp
          className="p-6"
          icon={Mail}
          titulo={t('profilePage.invitations.title')}
          headerExtra={invitations.length > 0 ? <Badge variant="warning" label={String(invitations.length)} /> : undefined}
        >
          {loading && (
            <LoadingState variant="section" message={t('profilePage.invitations.loading')} />
          )}
          {!loading && invitations.length > 0 && (
            <ul className={LIST_CLASSES}>
              {invitations.map((invitation) => (
                <li key={invitation.id} className={LIST_ITEM_CLASSES}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-medium text-fg dark:text-fg-dark">{invitation.app_name}</h3>
                      <p className="mt-0.5 truncate text-xs text-fg-secondary dark:text-fg-secondary-dark">
                        {t('profilePage.invitations.invitedBy', { email: invitation.inviter_email })}
                      </p>
                    </div>
                    <Badge variant={getRoleBadgeVariant(invitation.role)} label={getRoleLabel(invitation.role)} className="shrink-0" />
                  </div>

                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                      {new Date(invitation.invited_at).toLocaleDateString(i18n.resolvedLanguage)}
                    </span>
                    <div className="flex gap-2">
                      <ButtonApp
                        label={t('collaborationPage.pendingInvitations.decline')}
                        ariaLabel={t('profilePage.invitations.declineAria', { name: invitation.app_name })}
                        variant="secondary"
                        size="small"
                        onClick={() => handleRespond(invitation.id, 'decline')}
                      />
                      <ButtonApp
                        label={t('collaborationPage.pendingInvitations.accept')}
                        ariaLabel={t('profilePage.invitations.acceptAria', { name: invitation.app_name })}
                        variant="primary"
                        size="small"
                        onClick={() => handleRespond(invitation.id, 'accept')}
                      />
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {!loading && invitations.length === 0 && (
            <EmptyList icon={Mail} message={t('profilePage.invitations.empty')} />
          )}
        </CardApp>

        {/* Active Collaborations */}
        <CardApp
          className="p-6"
          icon={Handshake}
          titulo={t('profilePage.collaborations.title')}
          headerExtra={collaborations.length > 0 ? <Badge variant="secondary" label={String(collaborations.length)} /> : undefined}
        >
          {loading && (
            <LoadingState variant="section" message={t('profilePage.collaborations.loading')} />
          )}
          {!loading && collaborations.length > 0 && (
            <ul className={LIST_CLASSES}>
              {collaborations.map((app) => (
                <li key={app.app_id} className={LIST_ITEM_CLASSES}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="truncate text-sm font-medium text-fg dark:text-fg-dark">{app.name}</h3>
                        <Badge variant={getRoleBadgeVariant(app.role)} label={getRoleLabel(app.role)} className="shrink-0" />
                      </div>
                      <p className="mt-1 flex items-center gap-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
                        <Crown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                        <span className="sr-only">{t('collaborationPage.roles.owner')}:</span>
                        <span className="truncate">{app.owner_name || app.owner_email || t('collaborationPage.unknown')}</span>
                      </p>
                    </div>
                    <ButtonApp
                      label={t('appsPage.actions.leaveApp')}
                      ariaLabel={t('profilePage.collaborations.leaveAria', { name: app.name })}
                      variant="danger"
                      size="small"
                      icon={<LogOut className="h-3.5 w-3.5" aria-hidden="true" />}
                      onClick={() => handleLeaveApp(app.app_id, app.name)}
                      className="shrink-0"
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
          {!loading && collaborations.length === 0 && (
            <EmptyList icon={Handshake} message={t('profilePage.collaborations.empty')} />
          )}
        </CardApp>
      </div>
    </div>
  );
};

export default ProfilePage;
