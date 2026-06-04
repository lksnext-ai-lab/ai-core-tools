import { useState, useEffect } from 'react';
import { Crown, Check, X, Ban, Trash2, RefreshCcw, UserCheck, Eye, Pencil } from 'lucide-react';
import { adminService } from '../../services/admin';
import type { User, UserListResponse } from '../../services/admin';
import ActionDropdown from '../../components/ui/ActionDropdown';
import Alert from '../../components/ui/Alert';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useUser } from '../../contexts/UserContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';

function UsersPage() {
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const { user: currentUser } = useUser();

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalUsers, setTotalUsers] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [deletingUser, setDeletingUser] = useState<number | null>(null);
  const [activatingUser, setActivatingUser] = useState<number | null>(null);
  const [resettingQuota, setResettingQuota] = useState<number | null>(null);
  const [settingRole, setSettingRole] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const perPage = 10;

  useEffect(() => {
    loadUsers();
  }, [currentPage, searchQuery]);

  async function loadUsers() {
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
  }

  async function handleDeleteUser(userId: number) {
    const target = users.find((u) => u.user_id === userId);
    const ok = await confirm({
      title: 'Delete user?',
      message: target
        ? `Delete ${target.name || target.email}? This will also delete all their apps and data. This action cannot be undone.`
        : 'Delete this user? This action cannot be undone.',
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    setDeletingUser(userId);
    const result = await mutate(
      () => adminService.deleteUser(userId),
      {
        loading: 'Deleting user…',
        success: 'User deleted',
        error: (err) => errorMessage(err, 'Failed to delete user'),
      },
    );
    setDeletingUser(null);
    if (result === undefined) return;

    await loadUsers();
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
    setCurrentPage(1); // Reset to first page when searching
  }

  if (loading && users.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2">Loading users...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
          <p className="text-gray-600">Manage all users in the system</p>
        </div>
      </div>

      {/* Search */}
      <div className="bg-white rounded-lg shadow p-6">
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="flex-1">
            <input
              type="text"
              placeholder="Search by name or email..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Search
          </button>
        </form>
      </div>

      {/* Users Table */}
      <div className="bg-white rounded-lg shadow overflow-visible">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            Users ({totalUsers} total)
          </h2>
        </div>

        <div className="overflow-x-auto overflow-visible">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  User
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Role
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Apps
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  API Keys
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center">
                    <div className="text-gray-500">
                      <p className="text-lg font-medium">No users found</p>
                      <p className="text-sm mt-1">
                        {searchQuery ? 'Try adjusting your search terms.' : 'There are no users in the system yet.'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.user_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <div className="text-sm font-medium text-gray-900">
                          {user.name || 'No name'}
                        </div>
                        <div className="text-sm text-gray-500">{user.email}</div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {user.platform_role === 'admin' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                          <Crown className="w-3 h-3 mr-1" /> Admin
                        </span>
                      ) : user.platform_role === 'editor' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                          <Pencil className="w-3 h-3 mr-1" /> Editor
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                          <Eye className="w-3 h-3 mr-1" /> Viewer
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {user.is_active ? (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          <Check className="w-3 h-3 mr-1" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                          <X className="w-3 h-3 mr-1" /> Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {user.owned_apps_count}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {user.api_keys_count}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(user.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      {user.email === currentUser?.email ? (
                        <span className="text-xs text-gray-500 italic">Your account</span>
                      ) : (
                        <ActionDropdown
                          actions={[
                            ...(user.platform_role !== 'viewer' ? [{
                              label: settingRole === user.user_id ? 'Setting...' : 'Set as Viewer',
                              onClick: () => { void handleSetPlatformRole(user.user_id, 'viewer', user.name || user.email); },
                              icon: <Eye className="w-4 h-4" />,
                              variant: 'default' as const,
                              disabled: settingRole === user.user_id
                            }] : []),
                            ...(user.platform_role !== 'editor' ? [{
                              label: settingRole === user.user_id ? 'Setting...' : 'Set as Editor',
                              onClick: () => { void handleSetPlatformRole(user.user_id, 'editor', user.name || user.email); },
                              icon: <Pencil className="w-4 h-4" />,
                              variant: 'default' as const,
                              disabled: settingRole === user.user_id
                            }] : []),
                            ...(user.platform_role !== 'admin' ? [{
                              label: settingRole === user.user_id ? 'Setting...' : 'Set as Admin',
                              onClick: () => { void handleSetPlatformRole(user.user_id, 'admin', user.name || user.email); },
                              icon: <UserCheck className="w-4 h-4" />,
                              variant: 'default' as const,
                              disabled: settingRole === user.user_id
                            }] : []),
                            ...(user.is_active ? [
                              {
                                label: activatingUser === user.user_id ? 'Deactivating...' : 'Deactivate',
                                onClick: () => { void handleDeactivateUser(user.user_id, user.name || user.email); },
                                icon: <Ban className="w-4 h-4" />,
                                variant: 'warning' as const,
                                disabled: activatingUser === user.user_id
                              }
                            ] : [
                              {
                                label: activatingUser === user.user_id ? 'Activating...' : 'Activate',
                                onClick: () => { void handleActivateUser(user.user_id); },
                                icon: <Check className="w-4 h-4" />,
                                variant: 'success' as const,
                                disabled: activatingUser === user.user_id
                              }
                            ]),
                            {
                              label: resettingQuota === user.user_id ? 'Resetting...' : 'Reset Quota',
                              onClick: () => { void handleResetQuota(user.user_id, user.name || user.email); },
                              icon: <RefreshCcw className="w-4 h-4" />,
                              variant: 'warning' as const,
                              disabled: resettingQuota === user.user_id
                            },
                            {
                              label: deletingUser === user.user_id ? 'Deleting...' : 'Delete',
                              onClick: () => { void handleDeleteUser(user.user_id); },
                              icon: <Trash2 className="w-4 h-4" />,
                              variant: 'danger' as const,
                              disabled: deletingUser === user.user_id
                            }
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

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-6 py-4 border-t border-gray-200">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-700">
                Showing page {currentPage} of {totalPages}
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => setCurrentPage(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <button
                  onClick={() => setCurrentPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default UsersPage; 