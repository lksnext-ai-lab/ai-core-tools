import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiService } from '../services/api';
import { Download, Crown, Shield, LayoutDashboard, Bot, Settings, Upload, LogOut, Trash2, FolderOpen, Globe, Database, Users, BarChart2, Check } from 'lucide-react';
import Modal from '../components/ui/Modal';
import AppForm from '../components/forms/AppForm';
import ActionDropdown from '../components/ui/ActionDropdown';
import Speedometer from '../components/ui/Speedometer';
import Alert from '../components/ui/Alert';
import Table from '../components/ui/Table';
import AppImportStepper from '../components/import/AppImportStepper';

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
  const [showImportModal, setShowImportModal] = useState(false);

  // useEffect = runs when component mounts (like __init__)
  useEffect(() => {
    void loadApps();
    
    // Auto-refresh only usage stats every 30 seconds (not full page)
    const interval = setInterval(() => {
      void loadUsageStats();
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

  // Function to refresh apps without showing loading spinner (for after create/import)
  async function refreshApps() {
    try {
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
      // Silently fail to avoid disrupting user experience
      console.error('Failed to refresh apps:', err);
    }
  }

  // Function to load only usage stats (optimized for auto-refresh)
  async function loadUsageStats() {
    try {
      const response = await apiService.getUsageStats();
      
      // Update only the usage stats, not the full apps data
      const stats: Record<number, UsageStats> = {};
      response.forEach((stat: UsageStats & { app_id: number }) => {
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
    await apiService.createApp(data);
    setShowCreateModal(false);
    setSuccess(`App "${data.name}" created successfully!`);
    setError(null);
    void refreshApps(); // Refresh the list without loading spinner
    // Auto-dismiss notification after 5 seconds
    setTimeout(() => setSuccess(null), 5000);
  }

  // Function to leave an app (for editors only)
  async function handleLeaveApp(app: App) {
    if (!globalThis.confirm(`Are you sure you want to leave "${app.name}"?`)) {
      return;
    }

    try {
      setError(null);
      setSuccess(null);
      await apiService.leaveApp(app.app_id);
      setSuccess(`Successfully left "${app.name}"`);
      void refreshApps(); // Refresh the list without loading spinner
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

    const userInput = globalThis.prompt(confirmMessage);
    
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
      void refreshApps(); // Refresh the list without loading spinner
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete app');
    } finally {
      setLoading(false);
    }
  }

  // Function to export full app
  async function handleExportApp(app: App) {
    try {
      setError(null);
      setSuccess(null);
      const blob = await apiService.exportFullApp(app.app_id);
      
      // Create download link
      const url = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const date = new Date().toISOString().split('T')[0];
      a.download = `${app.name.replaceAll(/\s+/g, '-')}-full-export-${date}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      globalThis.URL.revokeObjectURL(url);
      
      setSuccess(`Full app "${app.name}" exported successfully!`);
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export app');
    }
  }

  // Function to handle import completion
  function handleImportComplete() {
    setShowImportModal(false);
    setSuccess('App imported successfully!');
    void refreshApps();
    setTimeout(() => setSuccess(null), 5000);
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

  // Main render
  return (
    <div className="space-y-6">
      {success && <Alert type="success" message={success} onDismiss={() => setSuccess(null)} />}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Apps</h1>
          <p className="text-gray-600">Manage your AI applications and workspaces</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowImportModal(true)}
            className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors flex items-center"
          >
            <Download className="w-4 h-4 mr-2" />
            Import App
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors flex items-center"
          >
            <span className="mr-2">+</span>
            {' '}New App
          </button>
        </div>
      </div>

      {/* Apps Table */}
      <Table
        data={apps}
        keyExtractor={(app) => app.app_id.toString()}
        columns={[
          {
            header: 'App Name',
            render: (app) => (
              <Link
                to={`/apps/${app.app_id}`}
                className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
              >
                {app.name}
              </Link>
            )
          },
          {
            header: 'Role',
            render: (app) => {
              if (app.role === 'owner') {
                return (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                    <Crown className="w-3 h-3 mr-1" />
                    {' '}Owner
                  </span>
                );
              }
              if (app.role === 'administrator') {
                return (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                    <Shield className="w-3 h-3 mr-1" />
                    {' '}Administrator
                  </span>
                );
              }
              if (app.role === 'editor') {              
                return (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                    {' '}Editor
                </span>
                );
              }
              if (app.role === 'viewer') {              
                return (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                    {' '}Viewer
                </span>
                );
              }
              return null;
            }
          },
          {
            header: 'Agents',
            headerContent: <span className="flex items-center gap-1 justify-center"><Bot className="w-3 h-3" /> Agents</span>,
            headerClassName: 'px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-4 py-4 whitespace-nowrap text-center',
            render: (app) => (
              <span className={`text-sm font-medium ${app.agent_count > 0 ? 'text-blue-600' : 'text-gray-400'}`}>
                {app.agent_count}
              </span>
            )
          },
          {
            header: 'Repos',
            headerContent: <span className="flex items-center gap-1 justify-center"><FolderOpen className="w-3 h-3" /> Repos</span>,
            headerClassName: 'px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-4 py-4 whitespace-nowrap text-center',
            render: (app) => (
              <span className={`text-sm font-medium ${app.repository_count > 0 ? 'text-green-600' : 'text-gray-400'}`}>
                {app.repository_count}
              </span>
            )
          },
          {
            header: 'Domains',
            headerContent: <span className="flex items-center gap-1 justify-center"><Globe className="w-3 h-3" /> Domains</span>,
            headerClassName: 'px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-4 py-4 whitespace-nowrap text-center',
            render: (app) => (
              <span className={`text-sm font-medium ${app.domain_count > 0 ? 'text-purple-600' : 'text-gray-400'}`}>
                {app.domain_count}
              </span>
            )
          },
          {
            header: 'Silos',
            headerContent: <span className="flex items-center gap-1 justify-center"><Database className="w-3 h-3" /> Silos</span>,
            headerClassName: 'px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-4 py-4 whitespace-nowrap text-center',
            render: (app) => (
              <span className={`text-sm font-medium ${app.silo_count > 0 ? 'text-orange-600' : 'text-gray-400'}`}>
                {app.silo_count}
              </span>
            )
          },
          {
            header: 'Collabs',
            headerContent: <span className="flex items-center gap-1 justify-center"><Users className="w-3 h-3" /> Collabs</span>,
            headerClassName: 'px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-4 py-4 whitespace-nowrap text-center',
            render: (app) => {
              const ownerBonus = app.role === 'owner' ? 1 : 0;
              const totalCollaborators = app.collaborator_count + ownerBonus;
              const textColor = totalCollaborators > 1 ? 'text-indigo-600' : 'text-gray-400';
              return (
                <span className={`text-sm font-medium ${textColor}`}>
                  {totalCollaborators}
                </span>
              );
            }
          },
          {
            header: 'Owner',
            render: (app) => (
              app.role === 'owner' ? (
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
              )
            )
          },
          {
            header: 'Status',
            render: (app) => (
              <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                app.langsmith_configured 
                  ? 'bg-green-100 text-green-800' 
                  : 'bg-gray-100 text-gray-600'
              }`}>
                {app.langsmith_configured ? <span className="flex items-center gap-1"><Check className="w-3 h-3" /> Configured</span> : 'Not configured'}
              </span>
            )
          },
          {
            header: 'Usage',
            headerContent: <span className="flex items-center gap-1 justify-center"><BarChart2 className="w-3 h-3" /> Usage</span>,
            headerClassName: 'px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-4 py-4 whitespace-nowrap text-center',
            render: (app) => (
              usageStats[app.app_id] ? (
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
              )
            )
          },
          {
            header: 'Created',
            render: (app) => app.created_at ? new Date(app.created_at).toLocaleDateString() : '-',
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
          },
          {
            header: 'Actions',
            headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium',
            render: (app) => (
              <ActionDropdown
                actions={[
                  {
                    label: 'Open Dashboard',
                    onClick: () => { globalThis.location.href = `/apps/${app.app_id}`; },
                    icon: <LayoutDashboard className="w-4 h-4" />,
                    variant: 'primary'
                  },
                  {
                    label: 'Manage Agents',
                    onClick: () => { globalThis.location.href = `/apps/${app.app_id}/agents`; },
                    icon: <Bot className="w-4 h-4" />,
                    variant: 'secondary'
                  },
                  {
                    label: 'App Settings',
                    onClick: () => { globalThis.location.href = `/apps/${app.app_id}/settings`; },
                    icon: <Settings className="w-4 h-4" />,
                    variant: 'secondary'
                  },
                  {
                    label: 'Export Full App',
                    onClick: () => { void handleExportApp(app); },
                    icon: <Upload className="w-4 h-4" />,
                    variant: 'secondary'
                  },
                  ...(app.role === 'owner' ? [] : [{
                    label: 'Leave App',
                    onClick: () => handleLeaveApp(app),
                    icon: <LogOut className="w-4 h-4" />,
                    variant: 'danger' as const
                  }]),
                  ...(app.role === 'owner' ? [{
                    label: 'Delete App',
                    onClick: () => handleDeleteApp(app),
                    icon: <Trash2 className="w-4 h-4" />,
                    variant: 'danger' as const
                  }] : [])
                ]}
                size="sm"
              />
            )
          }
        ]}
        emptyIcon={<Bot className="w-10 h-10 text-gray-300" />}
        emptyMessage="No apps yet"
        emptySubMessage="Create your first AI application to get started"
        loading={loading}
      />

      {!loading && apps.length === 0 && (
        <div className="text-center py-6">
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg"
          >
            Create App
          </button>
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

      {/* Import App Stepper */}
      {showImportModal && (
        <AppImportStepper
          isOpen={showImportModal}
          onClose={() => setShowImportModal(false)}
          onImportComplete={handleImportComplete}
        />
      )}
    </div>
  );
}

export default AppsPage; 