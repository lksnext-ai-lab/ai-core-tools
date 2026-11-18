import { useState, useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { apiService } from '../services/api';
import { useUser } from '../contexts/UserContext';
import { Download, Crown, Shield, LayoutDashboard, Bot, Settings, Upload, LogOut, Trash2, FolderOpen, Globe, Database, Users, Check } from 'lucide-react';
import Modal from '../components/ui/Modal';
import AppForm from '../components/forms/AppForm';
import ActionDropdown from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';
import Table from '../components/ui/Table';
import AppImportStepper from '../components/import/AppImportStepper';
import { APP_LIST_PAGE_SIZE } from '../constants/appList';

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
}

function dedupeApps(apps: readonly App[]): App[] {
  const seenIds = new Set<number>();
  return apps.filter((app) => {
    if (seenIds.has(app.app_id)) return false;
    seenIds.add(app.app_id);
    return true;
  });
}

function hasAppAccessDeniedState(state: unknown): boolean {
  return typeof state === 'object'
    && state !== null
    && 'appAccessDenied' in state
    && state.appAccessDenied === true;
}

// React Component = Function that returns HTML-like JSX
function AppsPage() {
  const { user } = useUser();
  const location = useLocation();
  const isEditor = user?.is_admin || (user?.is_editor ?? false);
  const accessDenied = hasAppAccessDeniedState(location.state);

  // State = variables that trigger re-renders when they change
  const [apps, setApps] = useState<App[]>([]);           // Like self.apps = []
  const [loading, setLoading] = useState(true);          // Like self.loading = True
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [listStatus, setListStatus] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [deletingAppId, setDeletingAppId] = useState<number | null>(null);
  const appsRef = useRef<App[]>([]);
  const nextOffset = useRef(0);
  const committedOffset = useRef(0);
  const listGeneration = useRef(0);
  const loadMoreRequestId = useRef(0);
  const deleteGeneration = useRef(0);
  const refreshingRef = useRef(false);

  // useEffect = runs when component mounts (like __init__)
  useEffect(() => {
    let active = true;
    const generation = ++listGeneration.current;

    async function fetchApps() {
      try {
        setLoading(true);
        setError(null);
        setSuccess(null);
        const response = await apiService.getAppsPage(APP_LIST_PAGE_SIZE, 0);
        if (active && generation === listGeneration.current) {
          const firstPage = dedupeApps(response.apps);
          appsRef.current = firstPage;
          nextOffset.current = response.apps.length;
          committedOffset.current = response.apps.length;
          setApps(firstPage);
          setHasMore(response.hasMore);
          setListStatus(`${firstPage.length} apps loaded.`);
        }
      } catch (err) {
        if (active && generation === listGeneration.current) {
          setError(err instanceof Error ? err.message : 'Failed to load apps');
          setListStatus('Apps could not be loaded.');
        }
      } finally {
        if (active && generation === listGeneration.current) setLoading(false);
      }
    }

    void fetchApps();
    return () => {
      active = false;
      if (listGeneration.current === generation) listGeneration.current += 1;
    };
  }, []);

  // Reload page one after create/import and invalidate any in-flight next-page request.
  async function refreshApps() {
    const generation = ++listGeneration.current;
    loadMoreRequestId.current += 1;
    setLoadingMore(false);
    nextOffset.current = 0;
    refreshingRef.current = true;
    setLoading(true);
    setError(null);
    setListStatus('Refreshing apps…');
    try {
      const response = await apiService.getAppsPage(APP_LIST_PAGE_SIZE, 0);
      if (generation !== listGeneration.current) return;
      const firstPage = dedupeApps(response.apps);
      appsRef.current = firstPage;
      nextOffset.current = response.apps.length;
      committedOffset.current = response.apps.length;
      setApps(firstPage);
      setHasMore(response.hasMore);
      setListStatus(`${firstPage.length} apps loaded.`);
    } catch (err) {
      if (generation === listGeneration.current) {
        nextOffset.current = committedOffset.current;
        setError(err instanceof Error ? err.message : 'Failed to refresh apps');
        setListStatus('Apps could not be refreshed.');
      }
    } finally {
      if (generation === listGeneration.current) {
        refreshingRef.current = false;
        setLoading(false);
      }
    }
  }

  async function loadMoreApps() {
    if (loading || loadingMore || refreshingRef.current || !hasMore) return;

    const generation = listGeneration.current;
    const requestId = ++loadMoreRequestId.current;
    const offset = nextOffset.current;
    const currentDisplayCount = appsRef.current.length;
    try {
      setLoadingMore(true);
      setError(null);
      setListStatus('Loading more apps…');
      const response = await apiService.getAppsPage(APP_LIST_PAGE_SIZE, offset);
      if (
        generation !== listGeneration.current ||
        requestId !== loadMoreRequestId.current ||
        offset !== nextOffset.current
      ) return;
      const mergedApps = dedupeApps([...appsRef.current, ...response.apps]);
      const appendedCount = mergedApps.length - currentDisplayCount;
      appsRef.current = mergedApps;
      nextOffset.current += response.apps.length;
      committedOffset.current = nextOffset.current;
      setApps(mergedApps);
      setHasMore(response.hasMore);
      setListStatus(appendedCount > 0
        ? `Loaded ${appendedCount} more apps.`
        : 'No additional apps were returned.');
    } catch (err) {
      if (generation === listGeneration.current && requestId === loadMoreRequestId.current) {
        setError(err instanceof Error ? err.message : 'Failed to load more apps');
        setListStatus('Could not load more apps. You can try again.');
      }
    } finally {
      if (requestId === loadMoreRequestId.current) setLoadingMore(false);
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
    if (deletingAppId !== null) return;

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

    const requestId = ++deleteGeneration.current;
    setDeletingAppId(app.app_id);
    try {
      setError(null);
      setSuccess(null);
      await apiService.deleteApp(app.app_id);
      setSuccess(`App "${app.name}" has been successfully deleted.`);
      await refreshApps();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete app');
    } finally {
      if (requestId === deleteGeneration.current) setDeletingAppId(null);
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
  if (loading && apps.length === 0) {
    return (
      <div className="space-y-6">
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{listStatus}</div>
        {accessDenied && (
          <Alert
            type="info"
            title="Access denied"
            message="You do not have access to that app."
            polite
          />
        )}
        <div className="flex items-center justify-center py-12" role="status" aria-live="polite">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" aria-hidden="true"></div>
          <span className="ml-2">Loading apps...</span>
        </div>
      </div>
    );
  }

  // Main render
  return (
    <div className="space-y-6">
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{listStatus}</div>
      {accessDenied && (
        <Alert
          type="info"
          title="Access denied"
          message="You do not have access to that app."
          polite
        />
      )}
      {success && <Alert type="success" message={success} onDismiss={() => setSuccess(null)} />}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}
      {deletingAppId !== null && (
        <div role="status" aria-live="polite" className="sr-only">Deleting app…</div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Apps</h1>
          <p className="text-gray-600">Manage your AI applications and workspaces</p>
        </div>
        {isEditor && (
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
        )}
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
                  ...(app.role === 'owner' || app.role === 'viewer' ? [] : [{
                    label: 'Leave App',
                    onClick: () => handleLeaveApp(app),
                    icon: <LogOut className="w-4 h-4" />,
                    variant: 'danger' as const
                  }]),
                  ...(app.role === 'owner' ? [{
                    label: deletingAppId === app.app_id ? 'Deleting App…' : 'Delete App',
                    onClick: () => handleDeleteApp(app),
                    icon: <Trash2 className="w-4 h-4" />,
                    variant: 'danger' as const,
                    disabled: deletingAppId !== null
                  }] : [])
                ]}
                size="sm"
              />
            )
          }
        ]}
        emptyIcon={<Bot className="w-10 h-10 text-gray-300" />}
        emptyMessage="No apps yet"
        emptySubMessage={isEditor
          ? 'Create your first AI application to get started'
          : 'No applications are currently available to your account'}
        loading={loading}
      />

      {hasMore && !loading && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => void loadMoreApps()}
            disabled={loadingMore}
            aria-busy={loadingMore}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
          >
            {loadingMore && (
              <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-current" aria-hidden="true" />
            )}
            Load more apps
          </button>
        </div>
      )}

      {!loading && apps.length === 0 && isEditor && (
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