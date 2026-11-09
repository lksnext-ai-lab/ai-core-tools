import { useState, useEffect, useCallback } from 'react';
import { Crown, Check, X, Ban, Trash2, RefreshCcw, UserPlus, Link, UserCheck, Eye, Pencil } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { adminService, OwnedAppsError } from '../../services/admin';
import type { User, UserListResponse } from '../../services/admin';
import ActionDropdown from '../../components/ui/ActionDropdown';
import Alert from '../../components/ui/Alert';
import { Badge } from '../../components/ui/Badge';
import { ButtonApp } from '../../components/ui/ButtonApp';
import FormField from '../../components/ui/FormField';
import Table from '../../components/ui/Table';
import CreateLocalUserModal from '../../components/ui/CreateLocalUserModal';
import OneTimeLinkModal from '../../components/ui/OneTimeLinkModal';
import DeleteUserDialog from '../../components/admin/DeleteUserDialog';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useUser } from '../../contexts/UserContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { useDeploymentMode } from '../../contexts/DeploymentModeContext';
import { errorMessage } from '../../constants/messages';
import { LoadingState } from '../../components/ui/LoadingState';
import Title from '../../components/ui/Title';


interface ResetLinkState {
  readonly token: string;
  readonly expiresAt: string;
}

function UsersPage() {
  const { t, i18n } = useTranslation('common');
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const { authMode, isLoading: modeLoading } = useDeploymentMode();
  const { user: currentUser } = useUser();

  // Guard against flicker during the /internal/config fetch.
  const isLocalMode = !modeLoading && authMode === 'local';

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalUsers, setTotalUsers] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [deletingUser, setDeletingUser] = useState<number | null>(null);
  const [activatingUser, setActivatingUser] = useState<number | null>(null);
  const [resettingQuota, setResettingQuota] = useState<number | null>(null);
  const [issuingResetLink, setIssuingResetLink] = useState<number | null>(null);
  const [settingRole, setSettingRole] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [resetLinkState, setResetLinkState] = useState<ResetLinkState | null>(null);
  const [deleteDialogUser, setDeleteDialogUser] = useState<User | null>(null);

  const perPage = 10;

  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response: UserListResponse = await adminService.getUsers(currentPage, perPage, searchQuery || undefined);
      setUsers(response.users);
      setTotalPages(response.total_pages);
      setTotalUsers(response.total);
    } catch (err) {
      console.error('Failed to load users:', err);
      setError(t('userManagement.loadFailed', { error: errorMessage(err, t('userManagement.unknownError')) }));
    } finally {
      setLoading(false);
    }
  }, [currentPage, perPage, searchQuery, t]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  async function handleDeleteUser(userId: number) {
    const target = users.find((u) => u.user_id === userId);
    if (!target) return;

    if (target.owned_apps_count > 0) {
      setDeleteDialogUser(target);
      return;
    }

    const ok = await confirm({
      title: t('userManagement.deleteTitle'),
      message: t('userManagement.deleteMessage', { name: target.name || target.email }),
      variant: 'danger',
      confirmLabel: t('userManagement.delete'),
    });
    if (!ok) return;

    setDeletingUser(userId);
    try {
      await adminService.deleteUser(userId);
      void mutate(
        () => Promise.resolve({ message: t('userManagement.userDeleted') }),
        {
          loading: t('userManagement.deletingUser'),
          success: t('userManagement.userDeleted'),
          error: (err) => errorMessage(err, t('userManagement.deleteFailed')),
        },
      );
      await loadUsers();
    } catch (err: unknown) {
      // Stale-count race: user acquired an app between list load and delete attempt.
      if (err instanceof OwnedAppsError) {
        setDeleteDialogUser(target);
        return;
      }
      void mutate(
        () => Promise.reject(err),
        {
          loading: t('userManagement.deletingUser'),
          success: t('userManagement.userDeleted'),
          error: (e) => errorMessage(e, t('userManagement.deleteFailed')),
        },
      );
    } finally {
      setDeletingUser(null);
    }
  }

  async function handleActivateUser(userId: number) {
    setActivatingUser(userId);
    const result = await mutate(
      () => adminService.activateUser(userId),
      {
        loading: t('userManagement.activatingUser'),
        success: t('userManagement.userActivated'),
        error: (err) => errorMessage(err, t('userManagement.activateFailed')),
      },
    );
    setActivatingUser(null);
    if (result === undefined) return;

    await loadUsers();
  }

  async function handleDeactivateUser(userId: number, userName: string) {
    const ok = await confirm({
      title: t('userManagement.deactivateTitle'),
      message: t('userManagement.deactivateMessage', { name: userName }),
      variant: 'warning',
      confirmLabel: t('userManagement.deactivate'),
    });
    if (!ok) return;

    setActivatingUser(userId);
    const result = await mutate(
      () => adminService.deactivateUser(userId),
      {
        loading: t('userManagement.deactivatingUser'),
        success: t('userManagement.userDeactivated'),
        error: (err) => errorMessage(err, t('userManagement.deactivateFailed')),
      },
    );
    setActivatingUser(null);
    if (result === undefined) return;

    await loadUsers();
  }

  async function handleResetQuota(userId: number, userLabel: string) {
    const ok = await confirm({
      title: t('userManagement.resetQuotaTitle'),
      message: t('userManagement.resetQuotaMessage', { name: userLabel }),
      variant: 'warning',
      confirmLabel: t('userManagement.resetQuota'),
    });
    if (!ok) return;

    setResettingQuota(userId);
    await mutate(
      () => adminService.resetUserMarketplaceQuota(userId),
      {
        loading: t('userManagement.resettingQuota'),
        success: t('userManagement.resetQuotaSuccess', { name: userLabel }),
        error: (err) => errorMessage(err, t('userManagement.resetQuotaFailed')),
      },
    );
    setResettingQuota(null);
  }

  async function handleIssueResetLink(userId: number) {
    setIssuingResetLink(userId);
    try {
      const result = await adminService.issueResetLink(userId);
      setResetLinkState({ token: result.set_password_token, expiresAt: result.expires_at });
    } catch (err) {
      setError(t('userManagement.resetLinkFailed', { error: errorMessage(err, t('userManagement.unknownError')) }));
    } finally {
      setIssuingResetLink(null);
    }
  }

  async function handleSetPlatformRole(userId: number, role: 'viewer' | 'editor' | 'admin', userName: string) {
    const labels = {
      viewer: t('userManagement.roleViewer'),
      editor: t('userManagement.roleEditor'),
      admin: t('userManagement.roleAdmin'),
    };

    const target = users.find((u) => u.user_id === userId);
    const ownedApps = target?.owned_apps_count ?? 0;
    const isDowngradeWithApps = role === 'viewer' && ownedApps > 0;

    const ok = await confirm({
      title: t('userManagement.setRoleTitle', { role: labels[role] }),
      message: isDowngradeWithApps
        ? t('userManagement.roleDowngradeWithApps', {
            name: userName,
            count: ownedApps,
            appLabel: t(ownedApps === 1 ? 'userManagement.appSingular' : 'userManagement.appPlural'),
          })
        : t('userManagement.changeRoleMessage', { name: userName, role: labels[role] }),
      variant: isDowngradeWithApps ? 'warning' : undefined,
      confirmLabel: t('userManagement.confirm'),
    });
    if (!ok) return;

    setSettingRole(userId);
    const result = await mutate(
      () => adminService.setPlatformRole(userId, role),
      {
        loading: t('userManagement.updatingRole'),
        success: t('userManagement.roleUpdated'),
        error: (err) => errorMessage(err, t('userManagement.updateRoleFailed')),
      },
    );
    setSettingRole(null);
    if (result === undefined) return;

    await loadUsers();
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setCurrentPage(1);
  }

  if (loading && users.length === 0) {
    return (
      <div className="space-y-6">
              {/* Page Header */}
              <div className="flex items-center justify-between">
                <Title variant='titPrincipal' titulo={t('userManagement.title')} subtitulo={t('userManagement.subtitle')}></Title>
              </div>
      
              <LoadingState variant="page" message={t('userManagement.loading')} />
            </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      <div className="flex items-center justify-between">
        <Title variant='titPrincipal' titulo={t('userManagement.title')} subtitulo={t('userManagement.subtitle')}></Title>

        {isLocalMode && (
          <ButtonApp
            label={t('userManagement.createUser')}
            variant="primary"
            size="medium"
            onClick={() => setShowCreateModal(true)}
            icon={<UserPlus className="w-4 h-4" aria-hidden="true" />}
          />
        )}
      </div>

      <div>
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="flex-1">
            <FormField
              label={t('userManagement.searchUsers')}
              labelClassName="sr-only"
              id="user-search"
              type="text"
              placeholder={t('userManagement.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <ButtonApp
            type="submit"
            label={t('userManagement.search')}
            variant="primary"
            size="small"
          />
        </form>
      </div>

      <div>
        <div className="py-4">
          <h2 className="font-display text-lg font-normal text-fg dark:text-fg-dark flex items-center">
            {t('userManagement.totalUsers', { count: totalUsers })}
          </h2>
        </div>

        <Table
          data={users}
          stickyEdgeColumns
          keyExtractor={(user) => user.user_id}
          columns={[
            {
              header: t('userManagement.user'),
              render: (user) => (
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-fg dark:text-fg-dark">
                      {user.name || t('userManagement.noName')}
                    </span>
                    {user.is_omniadmin && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
                        <Crown className="w-3 h-3 mr-1" aria-hidden="true" /> {t('userManagement.omniadmin')}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{user.email}</div>
                </div>
              ),
            },
            {
              header: t('userManagement.role'),
              render: (user) => user.platform_role === 'admin' ? (
                <Badge label={t('userManagement.roleAdmin')} variant="success" icon={<Crown className="w-3 h-3" aria-hidden="true" />} />
              ) : user.platform_role === 'editor' ? (
                <Badge label={t('userManagement.roleEditor')} variant="info" icon={<Pencil className="w-3 h-3" aria-hidden="true" />} />
              ) : (
                <Badge label={t('userManagement.roleViewer')} variant="warning" icon={<Eye className="w-3 h-3" aria-hidden="true" />} />
              ),
            },
            {
              header: t('userManagement.status'),
              render: (user) => user.is_active ? (
                <Badge label={t('userManagement.active')} variant="success" icon={<Check className="w-3 h-3" aria-hidden="true" />} />
              ) : (
                <Badge label={t('userManagement.inactive')} variant="default" icon={<X className="w-3 h-3" aria-hidden="true" />} />
              ),
            },
            {
              header: t('userManagement.apps'),
              accessor: 'owned_apps_count',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: t('userManagement.apiKeys'),
              accessor: 'api_keys_count',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: t('userManagement.created'),
              render: (user) => new Date(user.created_at).toLocaleDateString(i18n.language),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: t('userManagement.actions'),
              sticky: 'right' as const,
              render: (user) => user.is_omniadmin ? (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark italic">{t('userManagement.protectedAccount')}</span>
              ) : user.email === currentUser?.email ? (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark italic">{t('userManagement.yourAccount')}</span>
              ) : (
                <ActionDropdown
                  triggerAriaLabel={t('userManagement.actionsFor', { name: user.name || user.email })}
                  actions={[
                    ...(user.platform_role !== 'viewer' ? [{
                      label: settingRole === user.user_id ? t('userManagement.setting') : t('userManagement.setAsViewer'),
                      onClick: () => { void handleSetPlatformRole(user.user_id, 'viewer', user.name || user.email); },
                      icon: <Eye className="w-4 h-4" />,
                      variant: 'default' as const,
                      disabled: settingRole === user.user_id,
                    }] : []),
                    ...(user.platform_role !== 'editor' ? [{
                      label: settingRole === user.user_id ? t('userManagement.setting') : t('userManagement.setAsEditor'),
                      onClick: () => { void handleSetPlatformRole(user.user_id, 'editor', user.name || user.email); },
                      icon: <Pencil className="w-4 h-4" />,
                      variant: 'default' as const,
                      disabled: settingRole === user.user_id,
                    }] : []),
                    ...(user.platform_role !== 'admin' ? [{
                      label: settingRole === user.user_id ? t('userManagement.setting') : t('userManagement.setAsAdmin'),
                      onClick: () => { void handleSetPlatformRole(user.user_id, 'admin', user.name || user.email); },
                      icon: <UserCheck className="w-4 h-4" />,
                      variant: 'default' as const,
                      disabled: settingRole === user.user_id,
                    }] : []),
                    ...(user.is_active ? [{
                      label: activatingUser === user.user_id ? t('userManagement.deactivating') : t('userManagement.deactivate'),
                      onClick: () => { void handleDeactivateUser(user.user_id, user.name || user.email); },
                      icon: <Ban className="w-4 h-4" />,
                      variant: 'warning' as const,
                      disabled: activatingUser === user.user_id,
                    }] : [{
                      label: activatingUser === user.user_id ? t('userManagement.activating') : t('userManagement.activate'),
                      onClick: () => { void handleActivateUser(user.user_id); },
                      icon: <Check className="w-4 h-4" />,
                      variant: 'success' as const,
                      disabled: activatingUser === user.user_id,
                    }]),
                    {
                      label: resettingQuota === user.user_id ? t('userManagement.resetting') : t('userManagement.resetQuota'),
                      onClick: () => { void handleResetQuota(user.user_id, user.name || user.email); },
                      icon: <RefreshCcw className="w-4 h-4" />,
                      variant: 'warning' as const,
                      disabled: resettingQuota === user.user_id,
                    },
                    ...(isLocalMode ? [{
                      label: issuingResetLink === user.user_id ? t('userManagement.generating') : t('userManagement.resetPasswordLink'),
                      onClick: () => { void handleIssueResetLink(user.user_id); },
                      icon: <Link className="w-4 h-4" />,
                      variant: 'default' as const,
                      disabled: issuingResetLink === user.user_id,
                    }] : []),
                    {
                      label: deletingUser === user.user_id ? t('userManagement.deleting') : t('userManagement.delete'),
                      onClick: () => { void handleDeleteUser(user.user_id); },
                      icon: <Trash2 className="w-4 h-4" />,
                      variant: 'danger' as const,
                      disabled: deletingUser === user.user_id,
                    },
                  ]}
                  size="sm"
                />
              ),
              className: 'px-6 py-4 whitespace-nowrap text-sm font-medium',
            },
          ]}
          rowClassName=""
          emptyMessage={t('userManagement.noUsersFound')}
          emptySubMessage={searchQuery ? t('userManagement.adjustSearch') : t('userManagement.noUsersYet')}
        />

        {totalPages > 1 && (
          <div className="px-6 py-4 border-t border-gray-200 dark:border-slate-700">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-700 dark:text-slate-400">
                {t('userManagement.showingPage', { currentPage, totalPages })}
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => setCurrentPage(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1 text-sm border border-gray-300 dark:border-slate-600 rounded-md hover:bg-gray-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {t('userManagement.previous')}
                </button>
                <button
                  onClick={() => setCurrentPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 text-sm border border-gray-300 dark:border-slate-600 rounded-md hover:bg-gray-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {t('userManagement.next')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {isLocalMode && (
        <CreateLocalUserModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onCreated={loadUsers}
        />
      )}

      {resetLinkState && (
        <OneTimeLinkModal
          isOpen={true}
          onClose={() => setResetLinkState(null)}
          token={resetLinkState.token}
          expiresAt={resetLinkState.expiresAt}
          title={t('userManagement.passwordResetLinkTitle')}
        />
      )}

      {deleteDialogUser && (
        <DeleteUserDialog
          isOpen={true}
          targetUser={deleteDialogUser}
          onClose={() => setDeleteDialogUser(null)}
          onDeleted={() => {
            setDeleteDialogUser(null);
            void loadUsers();
          }}
        />
      )}
    </div>
  );
}

export default UsersPage;
