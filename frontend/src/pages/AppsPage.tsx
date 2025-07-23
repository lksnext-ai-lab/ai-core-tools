import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiService } from '../services/api';
import { useUser } from '../contexts/UserContext';
import Modal from '../components/ui/Modal';
import AppForm from '../components/forms/AppForm';

// Define the App type (like your Pydantic models!)
interface App {
  app_id: number;
  name: string;
  created_at: string;
  owner_id: number;
  owner_name?: string;
  owner_email?: string;
  role: string; // "owner" or "editor"
  langsmith_configured: boolean;
}

// React Component = Function that returns HTML-like JSX
function AppsPage() {
  // State = variables that trigger re-renders when they change
  const [apps, setApps] = useState<App[]>([]);           // Like self.apps = []
  const [loading, setLoading] = useState(true);          // Like self.loading = True
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [openActionMenu, setOpenActionMenu] = useState<number | null>(null);
  const { user } = useUser();

  // useEffect = runs when component mounts (like __init__)
  useEffect(() => {
    loadApps();
  }, []);

  // Close action menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Element;
      if (openActionMenu !== null && !target.closest('.action-dropdown')) {
        setOpenActionMenu(null);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [openActionMenu]);

  // Function to load apps from API
  async function loadApps() {
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getApps();
      setApps(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load apps');
    } finally {
      setLoading(false);
    }
  }

  // Function to create a new app
  async function handleCreateApp(data: { name: string }) {
    try {
      await apiService.createApp(data);
      setShowCreateModal(false);
      loadApps(); // Reload the list
    } catch (err) {
      throw err; // Let the form handle the error
    }
  }

  // Function to leave an app (for editors only)
  async function handleLeaveApp(app: App) {
    if (!window.confirm(`Are you sure you want to leave "${app.name}"?`)) {
      return;
    }

    try {
      await apiService.leaveApp(app.app_id);
      loadApps(); // Reload the list
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to leave app');
    }
  }

  // Function to get user initials for avatar
  const getUserInitials = (name?: string, email?: string) => {
    if (name) {
      return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
    }
    if (email) {
      return email[0].toUpperCase();
    }
    return 'U';
  };

  // Show loading spinner while fetching data
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2">Loading apps...</span>
      </div>
    );
  }

  // Show error message if something went wrong
  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex">
          <span className="text-red-400 text-xl mr-3">⚠️</span>
          <div>
            <h3 className="text-sm font-medium text-red-800">Error Loading Apps</h3>
            <p className="text-sm text-red-600 mt-1">{error}</p>
            <button 
              onClick={loadApps}
              className="mt-2 text-sm text-red-600 hover:text-red-800 underline"
            >
              Try again
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Main render
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Apps</h1>
          <p className="text-gray-600">Manage your AI applications and workspaces</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors flex items-center"
        >
          <span className="mr-2">+</span>
          New App
        </button>
      </div>

      {/* Apps Table */}
      {apps.length === 0 ? (
        <div className="text-center py-12">
          <div className="text-6xl mb-4">🤖</div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No apps yet</h3>
          <p className="text-gray-600 mb-4">Create your first AI application to get started</p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors"
          >
            Create App
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    App Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Role
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Owner
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    LangSmith
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {apps.map((app) => (
                  <tr key={app.app_id} className="hover:bg-gray-50 transition-colors">
                    {/* App Name */}
                    <td className="px-6 py-4 whitespace-nowrap">
                      <Link
                        to={`/apps/${app.app_id}`}
                        className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
                      >
                        {app.name}
                      </Link>
                    </td>

                    {/* Role */}
                    <td className="px-6 py-4 whitespace-nowrap">
                      {app.role === 'owner' ? (
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          <span className="mr-1">👑</span>
                          Owner
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                          Editor
                        </span>
                      )}
                    </td>

                    {/* Owner */}
                    <td className="px-6 py-4 whitespace-nowrap">
                      {app.role === 'owner' ? (
                        <span className="text-sm text-gray-500">You</span>
                      ) : (
                        <div className="flex items-center">
                          <div className="w-6 h-6 bg-gray-300 rounded-full flex items-center justify-center mr-2">
                            <span className="text-xs font-medium text-gray-600">
                              {getUserInitials(app.owner_name, app.owner_email)}
                            </span>
                          </div>
                          <span className="text-sm text-gray-900">
                            {app.owner_name || app.owner_email}
                          </span>
                        </div>
                      )}
                    </td>

                    {/* Status */}
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                        app.langsmith_configured 
                          ? 'bg-green-100 text-green-800' 
                          : 'bg-gray-100 text-gray-600'
                      }`}>
                        {app.langsmith_configured ? '✓ Configured' : 'Not configured'}
                      </span>
                    </td>

                    {/* Created Date */}
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {app.created_at ? new Date(app.created_at).toLocaleDateString() : '-'}
                    </td>

                    {/* Actions Dropdown */}
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <div className="relative action-dropdown">
                        <button
                          onClick={() => setOpenActionMenu(openActionMenu === app.app_id ? null : app.app_id)}
                          className="p-2 text-gray-400 hover:text-gray-600 transition-colors rounded-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                          aria-expanded={openActionMenu === app.app_id}
                          aria-haspopup="true"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                          </svg>
                        </button>

                        {/* Dropdown Menu */}
                        {openActionMenu === app.app_id && (
                          <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg ring-1 ring-black ring-opacity-5 z-50">
                            <div className="py-1" role="menu" aria-orientation="vertical">
                              <Link
                                to={`/apps/${app.app_id}`}
                                className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                                role="menuitem"
                                onClick={() => setOpenActionMenu(null)}
                              >
                                <svg className="w-4 h-4 mr-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2H5a2 2 0 00-2-2z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5a2 2 0 012-2h4a2 2 0 012 2v6H8V5z" />
                                </svg>
                                Open Dashboard
                              </Link>

                              <Link
                                to={`/apps/${app.app_id}/agents`}
                                className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                                role="menuitem"
                                onClick={() => setOpenActionMenu(null)}
                              >
                                <svg className="w-4 h-4 mr-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                </svg>
                                Manage Agents
                              </Link>

                              <Link
                                to={`/apps/${app.app_id}/settings`}
                                className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                                role="menuitem"
                                onClick={() => setOpenActionMenu(null)}
                              >
                                <svg className="w-4 h-4 mr-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                App Settings
                              </Link>

                              {app.role === 'editor' && (
                                <div className="border-t border-gray-100">
                                  <button
                                    onClick={() => {
                                      handleLeaveApp(app);
                                      setOpenActionMenu(null);
                                    }}
                                    className="flex items-center w-full px-4 py-2 text-sm text-red-700 hover:bg-red-50 transition-colors"
                                    role="menuitem"
                                  >
                                    <svg className="w-4 h-4 mr-3 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                                    </svg>
                                    Leave App
                                  </button>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create App Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create New App"
      >
        <AppForm
          onSubmit={handleCreateApp}
          onCancel={() => setShowCreateModal(false)}
        />
      </Modal>
    </div>
  );
}

export default AppsPage; 