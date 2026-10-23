import { useState, useEffect, useCallback } from 'react';
import { Crown, Check, X, Ban, Trash2, RefreshCcw, UserPlus, Link, UserCheck, Eye, Pencil } from 'lucide-react';
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
      setError(`Failed to load users: ${errorMessage(err, 'Unknown error')}`);
    } finally {
      setLoading(false);
    }
  }, [currentPage, perPage, searchQuery]);

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
      title: 'Delete user?',
      message: `Delete ${target.name || target.email}? This action cannot be undone.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    setDeletingUser(userId);
    try {
      await adminService.deleteUser(userId);
      void mutate(
        () => Promise.resolve({ message: 'User deleted' }),
        {
          loading: 'Deleting user…',
          success: 'User deleted',
          error: (err) => errorMessage(err, 'Failed to delete user'),
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
          loading: 'Deleting user…',
          success: 'User deleted',
          error: (e) => errorMessage(e, 'Failed to delete user'),
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
        loading: 'Activating user…',
        success: (data) => data?.message ?? 'User activated',
        error: (err) => errorMessage(err, 'Failed to activate user'),
      },
    );
    setActivatingUser(null);
    if (result === undefined) return;

    await loadUsers();
  }

  async function handleDeactivateUser(userId: number, userName: string) {
    const ok = await confirm({
      title: 'Deactivate user?',
      message: `Deactivate ${userName}? They will not be able to access the system until reactivated.`,
      variant: 'warning',
      confirmLabel: 'Deactivate',
    });
    if (!ok) return;

    setActivatingUser(userId);
    const result = await mutate(
      () => adminService.deactivateUser(userId),
      {
        loading: 'Deactivating user…',
        success: (data) => data?.message ?? 'User deactivated',
        error: (err) => errorMessage(err, 'Failed to deactivate user'),
      },
    );
    setActivatingUser(null);
    if (result === undefined) return;

    await loadUsers();
  }

  async function handleResetQuota(userId: number, userLabel: string) {
    const ok = await confirm({
      title: 'Reset marketplace quota?',
      message: `Reset the marketplace call quota for ${userLabel}? Their current-month counter will be set to 0, allowing them to make up to the full quota again.`,
      variant: 'warning',
      confirmLabel: 'Reset quota',
    });
    if (!ok) return;

    setResettingQuota(userId);
    await mutate(
      () => adminService.resetUserMarketplaceQuota(userId),
      {
        loading: 'Resetting quota…',
        success: (data) => data?.message ?? `Marketplace quota reset for ${userLabel}`,
        error: (err) => errorMessage(err, 'Failed to reset marketplace quota'),
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
      setError(`Failed to issue reset link: ${errorMessage(err, 'Unknown error')}`);
    } finally {
      setIssuingResetLink(null);
    }
  }

  async function handleSetPlatformRole(userId: number, role: 'viewer' | 'editor' | 'admin', userName: string) {
    const labels: Record<string, string> = { viewer: 'Viewer', editor: 'Editor', admin: 'Admin' };

    const target = users.find((u) => u.user_id === userId);
    const ownedApps = target?.owned_apps_count ?? 0;
    const isDowngradeWithApps = role === 'viewer' && ownedApps > 0;

    const ok = await confirm({
      title: `Set role to ${labels[role]}?`,
      message: isDowngradeWithApps
        ? `${userName} owns ${ownedApps} app${ownedApps !== 1 ? 's' : ''}. As a viewer they will no longer be able to modify them, but will retain ownership. Are you sure you want to downgrade their role to Viewer?`
        : `Change ${userName}'s platform role to ${labels[role]}?`,
      variant: isDowngradeWithApps ? 'warning' : undefined,
      confirmLabel: 'Confirm',
    });
    if (!ok) return;

    setSettingRole(userId);
    const result = await mutate(
      () => adminService.setPlatformRole(userId, role),
      {
        loading: 'Updating role…',
        success: (data) => data?.message ?? 'Role updated',
        error: (err) => errorMessage(err, 'Failed to update role'),
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
                <Title variant='titPrincipal' titulo='Users' subtitulo='Manage all users in the system'></Title>
              </div>
      
              <LoadingState variant="page" message="Loading users..." />
            </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      <div className="flex items-center justify-between">
        <Title variant='titPrincipal' titulo='Users' subtitulo='Manage all users in the system'></Title>

        {isLocalMode && (
          <ButtonApp
            label="Create user"
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
              label="Search users"
              labelClassName="sr-only"
              id="user-search"
              type="text"
              placeholder="Search by name or email..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <ButtonApp
            type="submit"
            label="Search"
            variant="primary"
            size="small"
          />
        </form>
      </div>

      <div>
        <div className="py-4">
          <h2 className="font-display text-lg font-normal text-fg dark:text-fg-dark flex items-center">
            Users ({totalUsers} total)
          </h2>
        </div>

        <Table
          data={users}
          keyExtractor={(user) => user.user_id}
          columns={[
            {
              header: 'User',
              render: (user) => (
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-fg dark:text-fg-dark">
                      {user.name || 'No name'}
                    </span>
                    {user.is_omniadmin && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
                        <Crown className="w-3 h-3 mr-1" aria-hidden="true" /> Omniadmin
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{user.email}</div>
                </div>
              ),
            },
            {
              header: 'Role',
              render: (user) => user.platform_role === 'admin' ? (
                <Badge label="Admin" variant="success" icon={<Crown className="w-3 h-3" aria-hidden="true" />} />
              ) : user.platform_role === 'editor' ? (
                <Badge label="Editor" variant="info" icon={<Pencil className="w-3 h-3" aria-hidden="true" />} />
              ) : (
                <Badge label="Viewer" variant="warning" icon={<Eye className="w-3 h-3" aria-hidden="true" />} />
              ),
            },
            {
              header: 'Status',
              render: (user) => user.is_active ? (
                <Badge label="Active" variant="success" icon={<Check className="w-3 h-3" aria-hidden="true" />} />
              ) : (
                <Badge label="Inactive" variant="default" icon={<X className="w-3 h-3" aria-hidden="true" />} />
              ),
            },
            {
              header: 'Apps',
              accessor: 'owned_apps_count',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: 'API Keys',
              accessor: 'api_keys_count',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: 'Created',
              render: (user) => new Date(user.created_at).toLocaleDateString(),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: 'Actions',
              render: (user) => user.is_omniadmin ? (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark italic">Protected account</span>
              ) : user.email === currentUser?.email ? (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark italic">Your account</span>
              ) : (
                <ActionDropdown
                  triggerAriaLabel={`Actions for ${user.name || user.email}`}
                  actions={[
                    ...(user.platform_role !== 'viewer' ? [{
                      label: settingRole === user.user_id ? 'Setting...' : 'Set as Viewer',
                      onClick: () => { void handleSetPlatformRole(user.user_id, 'viewer', user.name || user.email); },
                      icon: <Eye className="w-4 h-4" />,
                      variant: 'default' as const,
                      disabled: settingRole === user.user_id,
                    }] : []),
                    ...(user.platform_role !== 'editor' ? [{
                      label: settingRole === user.user_id ? 'Setting...' : 'Set as Editor',
                      onClick: () => { void handleSetPlatformRole(user.user_id, 'editor', user.name || user.email); },
                      icon: <Pencil className="w-4 h-4" />,
                      variant: 'default' as const,
                      disabled: settingRole === user.user_id,
                    }] : []),
                    ...(user.platform_role !== 'admin' ? [{
                      label: settingRole === user.user_id ? 'Setting...' : 'Set as Admin',
                      onClick: () => { void handleSetPlatformRole(user.user_id, 'admin', user.name || user.email); },
                      icon: <UserCheck className="w-4 h-4" />,
                      variant: 'default' as const,
                      disabled: settingRole === user.user_id,
                    }] : []),
                    ...(user.is_active ? [{
                      label: activatingUser === user.user_id ? 'Deactivating...' : 'Deactivate',
                      onClick: () => { void handleDeactivateUser(user.user_id, user.name || user.email); },
                      icon: <Ban className="w-4 h-4" />,
                      variant: 'warning' as const,
                      disabled: activatingUser === user.user_id,
                    }] : [{
                      label: activatingUser === user.user_id ? 'Activating...' : 'Activate',
                      onClick: () => { void handleActivateUser(user.user_id); },
                      icon: <Check className="w-4 h-4" />,
                      variant: 'success' as const,
                      disabled: activatingUser === user.user_id,
                    }]),
                    {
                      label: resettingQuota === user.user_id ? 'Resetting...' : 'Reset Quota',
                      onClick: () => { void handleResetQuota(user.user_id, user.name || user.email); },
                      icon: <RefreshCcw className="w-4 h-4" />,
                      variant: 'warning' as const,
                      disabled: resettingQuota === user.user_id,
                    },
                    ...(isLocalMode ? [{
                      label: issuingResetLink === user.user_id ? 'Generating...' : 'Reset password link',
                      onClick: () => { void handleIssueResetLink(user.user_id); },
                      icon: <Link className="w-4 h-4" />,
                      variant: 'default' as const,
                      disabled: issuingResetLink === user.user_id,
                    }] : []),
                    {
                      label: deletingUser === user.user_id ? 'Deleting...' : 'Delete',
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
          emptyMessage="No users found"
          emptySubMessage={searchQuery ? 'Try adjusting your search terms.' : 'There are no users in the system yet.'}
        />

        {totalPages > 1 && (
          <div className="px-6 py-4 border-t border-gray-200 dark:border-slate-700">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-700 dark:text-slate-400">
                Showing page {currentPage} of {totalPages}
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => setCurrentPage(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1 text-sm border border-gray-300 dark:border-slate-600 rounded-md hover:bg-gray-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <button
                  onClick={() => setCurrentPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 text-sm border border-gray-300 dark:border-slate-600 rounded-md hover:bg-gray-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
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
          title="Password reset link"
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
