import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiService } from '../services/api';
import { useUser } from '../contexts/UserContext';
import Modal from '../components/ui/Modal';
import AppForm from '../components/forms/AppForm';
import ActionDropdown from '../components/ui/ActionDropdown';
import Speedometer from '../components/ui/Speedometer';

// Define the App type (like your Pydantic models!)
interface UsageStats {
  usage_percentage: number;
  stress_level: 'low' | 'moderate' | 'high' | 'critical' | 'unlimited';
  current_usage: number;
  limit: number;
  remaining: number;
  reset_in_seconds: number;
  is_over_limit: boolean;
}

interface App {
  app_id: number;
  name: string;
  created_at: string;
  owner_id: number;
  owner_name?: string;
  owner_email?: string;
  role: string; // "owner" or "editor"
  langsmith_configured: boolean;
  agent_rate_limit: number;
  // Entity counts for display
  agent_count: number;
  repository_count: number;
  domain_count: number;
  silo_count: number;
  collaborator_count: number;
  // Usage statistics for speedometer
  usage_stats?: UsageStats;
}

// React Component = Function that returns HTML-like JSX
function AppsPage() {
  // State = variables that trigger re-renders when they change
  const [apps, setApps] = useState<App[]>([]);           // Like self.apps = []
  const [loading, setLoading] = useState(true);          // Like self.loading = True
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [usageStats, setUsageStats] = useState<Record<number, UsageStats>>({});

  // useEffect = runs when component mounts (like __init__)
  useEffect(() => {
    loadApps();
    
    // Auto-refresh only usage stats every 30 seconds (not full page)
    const interval = setInterval(() => {
      loadUsageStats();
    }, 3000);
    
    return () => clearInterval(interval);
  }, []);

  // Function to load apps from API
  async function loadApps() {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      const response = await apiService.getApps();
      setApps(response);
      
      // Extract usage stats from response
      const stats: Record<number, UsageStats> = {};
      response.forEach((app: App) => {
        if (app.usage_stats) {
          stats[app.app_id] = app.usage_stats;
        }
      });
      setUsageStats(stats);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load apps');
    } finally {
      setLoading(false);
    }
  }

  // Function to load only usage stats (optimized for auto-refresh)
  async function loadUsageStats() {
    try {
      const response = await apiService.getUsageStats();
      
      // Update only the usage stats, not the full apps data
      const stats: Record<number, UsageStats> = {};
      response.forEach((stat: any) => {
        stats[stat.app_id] = {
          usage_percentage: stat.usage_percentage,
          stress_level: stat.stress_level,
          current_usage: stat.current_usage,
          limit: stat.limit,
          remaining: stat.remaining,
          reset_in_seconds: stat.reset_in_seconds,
          is_over_limit: stat.is_over_limit
        };
      });
      setUsageStats(stats);
    } catch (err) {
      // Silently fail for usage stats refresh to avoid disrupting user experience
      console.warn('Failed to refresh usage stats:', err);
    }
  }

  // Function to create a new app
  async function handleCreateApp(data: { name: string }) {
    try {
      await apiService.createApp(data);
      setShowCreateModal(false);
      setSuccess(`App "${data.name}" created successfully!`);
      setError(null);
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
      setError(null);
      setSuccess(null);
      await apiService.leaveApp(app.app_id);
      setSuccess(`Successfully left "${app.name}"`);
      loadApps(); // Reload the list
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave app');
    }
  }

  // Function to delete an app (for owners only)
  async function handleDeleteApp(app: App) {
    const confirmMessage = `⚠️ DELETE APP: "${app.name}"

This will permanently delete:
• All agents and configurations
• All repositories and uploaded files
• All domains and URLs
• All silos and vector data
• All API keys and settings
• All collaborations

This action cannot be undone!

Type the app name to confirm: "${app.name}"`;

    const userInput = window.prompt(confirmMessage);
    
    if (userInput !== app.name) {
      if (userInput !== null) { // User didn't cancel
        setError('App name does not match. Deletion cancelled.');
        setSuccess(null);
      }
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      await apiService.deleteApp(app.app_id);
      setSuccess(`App "${app.name}" has been successfully deleted.`);
      loadApps(); // Reload the list
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete app');
    } finally {
      setLoading(false);
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
      {/* Success Message */}
      {success && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-green-400 text-xl mr-3">✅</span>
            <div>
              <h3 className="text-sm font-medium text-green-800">Success</h3>
              <p className="text-sm text-green-600 mt-1">{success}</p>
              <button 
                onClick={() => setSuccess(null)}
                className="mt-2 text-sm text-green-600 hover:text-green-800 underline"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">⚠️</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
              <button 
                onClick={() => setError(null)}
                className="mt-2 text-sm text-red-600 hover:text-red-800 underline"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

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
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-visible">
          <div className="overflow-x-auto overflow-visible">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    App Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Role
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    🤖 Agents
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    📁 Repos
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    🌐 Domains
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    🗄️ Silos
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    👥 Collabs
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Owner
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    📊 Usage
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
                      ) : app.role === 'administrator' ? (
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                          <span className="mr-1">⚙️</span>
                          Administrator
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                          Editor
                        </span>
                      )}
                    </td>

                    {/* Agent Count */}
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      <span className={`text-sm font-medium ${app.agent_count > 0 ? 'text-blue-600' : 'text-gray-400'}`}>
                        {app.agent_count}
                      </span>
                    </td>

                    {/* Repository Count */}
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      <span className={`text-sm font-medium ${app.repository_count > 0 ? 'text-green-600' : 'text-gray-400'}`}>
                        {app.repository_count}
                      </span>
                    </td>

                    {/* Domain Count */}
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      <span className={`text-sm font-medium ${app.domain_count > 0 ? 'text-purple-600' : 'text-gray-400'}`}>
                        {app.domain_count}
                      </span>
                    </td>

                    {/* Silo Count */}
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      <span className={`text-sm font-medium ${app.silo_count > 0 ? 'text-orange-600' : 'text-gray-400'}`}>
                        {app.silo_count}
                      </span>
                    </td>

                    {/* Collaborator Count */}
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      <span className={`text-sm font-medium ${(app.collaborator_count + (app.role === 'owner' ? 1 : 0)) > 1 ? 'text-indigo-600' : 'text-gray-400'}`}>
                        {app.collaborator_count + (app.role === 'owner' ? 1 : 0)}
                      </span>
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

                    {/* Usage Speedometer */}
                    <td className="px-4 py-4 whitespace-nowrap text-center">
                      {usageStats[app.app_id] ? (
                        <div className="group relative">
                          <Speedometer 
                            usageStats={usageStats[app.app_id]} 
                            size="sm" 
                            showDetails={false}
                          />
                          {/* Tooltip */}
                          <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-10">
                            <div className="font-medium">
                              {usageStats[app.app_id].stress_level.charAt(0).toUpperCase() + usageStats[app.app_id].stress_level.slice(1)} Stress
                            </div>
                            <div className="text-gray-300">
                              {usageStats[app.app_id].current_usage}/{usageStats[app.app_id].limit === 0 ? '∞' : usageStats[app.app_id].limit} calls
                            </div>
                            {usageStats[app.app_id].limit > 0 && (
                              <div className="text-gray-300">
                                Resets in {Math.ceil(usageStats[app.app_id].reset_in_seconds)}s
                              </div>
                            )}
                            {usageStats[app.app_id].is_over_limit && (
                              <div className="text-red-300 font-medium">
                                Over limit!
                              </div>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="text-gray-400 text-xs">No data</div>
                      )}
                    </td>

                    {/* Created Date */}
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {app.created_at ? new Date(app.created_at).toLocaleDateString() : '-'}
                    </td>

                    {/* Actions Dropdown */}
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <ActionDropdown
                        actions={[
                          {
                            label: 'Open Dashboard',
                            onClick: () => window.location.href = `/apps/${app.app_id}`,
                            icon: '📊',
                            variant: 'primary'
                          },
                          {
                            label: 'Manage Agents',
                            onClick: () => window.location.href = `/apps/${app.app_id}/agents`,
                            icon: '🤖',
                            variant: 'secondary'
                          },
                          {
                            label: 'App Settings',
                            onClick: () => window.location.href = `/apps/${app.app_id}/settings`,
                            icon: '⚙️',
                            variant: 'secondary'
                          },
                          ...(app.role === 'editor' ? [{
                            label: 'Leave App',
                            onClick: () => handleLeaveApp(app),
                            icon: '🚪',
                            variant: 'danger' as const
                          }] : []),
                          ...(app.role === 'owner' ? [{
                            label: 'Delete App',
                            onClick: () => handleDeleteApp(app),
                            icon: '🗑️',
                            variant: 'danger' as const
                          }] : [])
                        ]}
                        size="sm"
                      />
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