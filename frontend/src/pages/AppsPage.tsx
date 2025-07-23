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
  const { user } = useUser();

  // useEffect = runs when component mounts (like __init__)
  useEffect(() => {
    loadApps();
  }, []);

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

      {/* Apps Grid */}
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {apps.map((app) => (
            <div key={app.app_id} className="bg-white rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
              <div className="p-6">
                {/* App Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <Link
                      to={`/apps/${app.app_id}`}
                      className="text-lg font-semibold text-gray-900 hover:text-blue-600 transition-colors"
                    >
                      {app.name}
                    </Link>
                    
                    {/* Role and Owner Info */}
                    <div className="mt-2 flex items-center space-x-2">
                      {app.role === 'owner' ? (
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          <span className="mr-1">👑</span>
                          Owner
                        </span>
                      ) : (
                        <div className="flex items-center space-x-2">
                          <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                            Editor
                          </span>
                          <div className="flex items-center text-xs text-gray-600">
                            <div className="w-4 h-4 bg-gray-300 rounded-full flex items-center justify-center mr-1">
                              <span className="text-xs font-medium text-gray-600">
                                {getUserInitials(app.owner_name, app.owner_email)}
                              </span>
                            </div>
                            <span>
                              Owner: {app.owner_name || app.owner_email}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center space-x-2">
                    {app.role === 'editor' && (
                      <button
                        onClick={() => handleLeaveApp(app)}
                        className="p-1 text-gray-400 hover:text-red-600 transition-colors"
                        title="Leave this app"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>

                {/* App Stats */}
                <div className="space-y-2 text-sm text-gray-600">
                  <div className="flex items-center justify-between">
                    <span>LangSmith</span>
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs ${
                      app.langsmith_configured 
                        ? 'bg-green-100 text-green-800' 
                        : 'bg-gray-100 text-gray-600'
                    }`}>
                      {app.langsmith_configured ? '✓ Configured' : 'Not configured'}
                    </span>
                  </div>
                  
                  {app.created_at && (
                    <div className="flex items-center justify-between">
                      <span>Created</span>
                      <span>{new Date(app.created_at).toLocaleDateString()}</span>
                    </div>
                  )}
                </div>

                {/* Quick Actions */}
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <div className="flex space-x-2">
                    <Link
                      to={`/apps/${app.app_id}`}
                      className="flex-1 text-center px-3 py-2 text-sm bg-blue-50 text-blue-700 rounded-md hover:bg-blue-100 transition-colors"
                    >
                      Open
                    </Link>
                    <Link
                      to={`/apps/${app.app_id}/agents`}
                      className="flex-1 text-center px-3 py-2 text-sm bg-gray-50 text-gray-700 rounded-md hover:bg-gray-100 transition-colors"
                    >
                      Agents
                    </Link>
                    <Link
                      to={`/apps/${app.app_id}/settings`}
                      className="flex-1 text-center px-3 py-2 text-sm bg-gray-50 text-gray-700 rounded-md hover:bg-gray-100 transition-colors"
                    >
                      Settings
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          ))}
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