import { useState, useEffect, useCallback } from 'react';
import { Crown, Check, X, Ban, Trash2, RefreshCcw, UserPlus, Link, UserCheck, Eye, Pencil } from 'lucide-react';
import { adminService, OwnedAppsError } from '../../services/admin';
import type { User, UserListResponse } from '../../services/admin';
import ActionDropdown from '../../components/ui/ActionDropdown';
import Alert from '../../components/ui/Alert';
import CreateLocalUserModal from '../../components/ui/CreateLocalUserModal';
import OneTimeLinkModal from '../../components/ui/OneTimeLinkModal';
import DeleteUserDialog from '../../components/admin/DeleteUserDialog';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useUser } from '../../contexts/UserContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { useDeploymentMode } from '../../contexts/DeploymentModeContext';
import { errorMessage } from '../../constants/messages';

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
      mutate(
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
      mutate(
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
      <div className="flex items-center justify-center py-12" role="status">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" aria-hidden="true"></div>
        <span className="ml-2">Loading users...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">User Management</h1>
          <p className="text-gray-600 dark:text-slate-400">Manage all users in the system</p>
        </div>

        {isLocalMode && (
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <UserPlus className="w-4 h-4" aria-hidden="true" />
            Create user
          </button>
        )}
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="flex-1">
            <label htmlFor="user-search" className="sr-only">Search users</label>
            <input
              id="user-search"
              type="text"
              placeholder="Search by name or email..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Search
          </button>
        </form>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-lg shadow overflow-visible">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
            Users ({totalUsers} total)
          </h2>
        </div>

        <div className="overflow-x-auto overflow-visible">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-slate-700">
            <thead className="bg-gray-50 dark:bg-slate-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                  User
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                  Role
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                  Apps
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                  API Keys
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-slate-800 divide-y divide-gray-200 dark:divide-slate-700">
              {users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center">
                    <div className="text-gray-500 dark:text-slate-400">
                      <p className="text-lg font-medium">No users found</p>
                      <p className="text-sm mt-1">
                        {searchQuery ? 'Try adjusting your search terms.' : 'There are no users in the system yet.'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.user_id} className="hover:bg-gray-50 dark:hover:bg-slate-700/50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-900 dark:text-slate-100">
                            {user.name || 'No name'}
                          </span>
                          {user.is_omniadmin && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
                              <Crown className="w-3 h-3 mr-1" aria-hidden="true" /> Omniadmin
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-500 dark:text-slate-400">{user.email}</div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {user.platform_role === 'admin' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
                          <Crown className="w-3 h-3 mr-1" aria-hidden="true" /> Admin
                        </span>
                      ) : user.platform_role === 'editor' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                          <Pencil className="w-3 h-3 mr-1" aria-hidden="true" /> Editor
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-300">
                          <Eye className="w-3 h-3 mr-1" aria-hidden="true" /> Viewer
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {user.is_active ? (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300">
                          <Check className="w-3 h-3 mr-1" aria-hidden="true" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300">
                          <X className="w-3 h-3 mr-1" aria-hidden="true" /> Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-slate-100">
                      {user.owned_apps_count}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-slate-100">
                      {user.api_keys_count}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-slate-400">
                      {new Date(user.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      {user.is_omniadmin ? (
                        <span className="text-xs text-gray-500 dark:text-slate-500 italic">Protected account</span>
                      ) : user.email === currentUser?.email ? (
                        <span className="text-xs text-gray-500 dark:text-slate-500 italic">Your account</span>
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
                            ...(user.is_active ? [
                              {
                                label: activatingUser === user.user_id ? 'Deactivating...' : 'Deactivate',
                                onClick: () => { void handleDeactivateUser(user.user_id, user.name || user.email); },
                                icon: <Ban className="w-4 h-4" />,
                                variant: 'warning' as const,
                                disabled: activatingUser === user.user_id,
                              },
                            ] : [
                              {
                                label: activatingUser === user.user_id ? 'Activating...' : 'Activate',
                                onClick: () => { void handleActivateUser(user.user_id); },
                                icon: <Check className="w-4 h-4" />,
                                variant: 'success' as const,
                                disabled: activatingUser === user.user_id,
                              },
                            ]),
                            {
                              label: resettingQuota === user.user_id ? 'Resetting...' : 'Reset Quota',
                              onClick: () => { void handleResetQuota(user.user_id, user.name || user.email); },
                              icon: <RefreshCcw className="w-4 h-4" />,
                              variant: 'warning' as const,
                              disabled: resettingQuota === user.user_id,
                            },
                            ...(isLocalMode ? [
                              {
                                label: issuingResetLink === user.user_id ? 'Generating...' : 'Reset password link',
                                onClick: () => { void handleIssueResetLink(user.user_id); },
                                icon: <Link className="w-4 h-4" />,
                                variant: 'default' as const,
                                disabled: issuingResetLink === user.user_id,
                              },
                            ] : []),
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
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

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
