import { useState, useEffect, useCallback, useRef } from 'react';
import type { SubmitEvent } from 'react';
import { UserPlus } from 'lucide-react';
import { adminService } from '../../services/admin';
import type { User, UserListResponse } from '../../services/admin';
import Alert from '../../components/ui/Alert';
import CreateLocalUserModal from '../../components/ui/CreateLocalUserModal';
import { useDeploymentMode } from '../../contexts/DeploymentModeContext';
import { errorMessage } from '../../constants/messages';
import { Link, useNavigate } from 'react-router-dom';

function UsersPage() {
  const navigate = useNavigate();
  const { authMode, isLoading: modeLoading } = useDeploymentMode();

  // Guard against flicker during the /internal/config fetch.
  const isLocalMode = !modeLoading && authMode === 'local';

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalUsers, setTotalUsers] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [submittedSearchQuery, setSubmittedSearchQuery] = useState('');
  const [error, setError] = useState<string | null>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const listRequestIdRef = useRef(0);

  const perPage = 10;

  const loadUsers = useCallback(async () => {
    const requestId = ++listRequestIdRef.current;
    try {
      setLoading(true);
      setError(null);
      const response: UserListResponse = await adminService.getUsers(
        currentPage,
        perPage,
        submittedSearchQuery || undefined,
      );
      if (requestId !== listRequestIdRef.current) return;
      setUsers(response.users);
      setTotalPages(response.total_pages);
      setTotalUsers(response.total);
    } catch (err) {
      if (requestId !== listRequestIdRef.current) return;
      console.error('Failed to load users:', err);
      setError(`Failed to load users: ${errorMessage(err, 'Unknown error')}`);
    } finally {
      if (requestId === listRequestIdRef.current) setLoading(false);
    }
  }, [currentPage, perPage, submittedSearchQuery]);

  useEffect(() => {
    void loadUsers();
    return () => {
      listRequestIdRef.current += 1;
    };
  }, [loadUsers]);

  function handleSearch(e: SubmitEvent) {
    e.preventDefault();
    setCurrentPage(1);
    setSubmittedSearchQuery(searchQuery.trim());
  }

  if (loading && users.length === 0) {
    return (
      <output className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" aria-hidden="true"></div>
        <span className="ml-2">Loading users...</span>
      </output>
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
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-slate-800 divide-y divide-gray-200 dark:divide-slate-700">
              {users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center">
                    <div className="text-gray-500 dark:text-slate-400">
                      <p className="text-lg font-medium">No users found</p>
                      <p className="text-sm mt-1">
                        {submittedSearchQuery ? 'Try adjusting your search terms.' : 'There are no users in the system yet.'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr
                    key={user.user_id}
                    onClick={() => navigate(`/admin/users/${user.user_id}`)}
                    className="cursor-pointer hover:bg-blue-50 dark:hover:bg-slate-700/70"
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-900 dark:text-slate-100">
                            {user.name || 'No name'}
                          </span>
                        </div>
                        <div className="text-sm text-gray-500 dark:text-slate-400">{user.email}</div>
                        <Link
                          to={`/admin/users/${user.user_id}`}
                          aria-label={`Open user details for ${user.name || user.email}`}
                          onClick={(event) => event.stopPropagation()}
                          className="mt-1 inline-flex rounded text-xs font-medium text-blue-700 underline decoration-transparent underline-offset-2 hover:decoration-current focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:text-blue-300"
                        >
                          View details
                        </Link>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold capitalize text-blue-800 dark:border-blue-900 dark:bg-blue-950/50 dark:text-blue-200">
                        {user.platform_role || 'Role unavailable'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        user.is_active
                          ? 'border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-200'
                          : 'border-gray-300 bg-gray-100 text-gray-700 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200'
                      }`}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
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

    </div>
  );
}

export default UsersPage;
