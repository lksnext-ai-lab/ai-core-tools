import { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import { useUser } from '../contexts/UserContext';
import { Download } from 'lucide-react';
import Modal from '../components/ui/Modal';
import AppForm from '../components/forms/AppForm';
import Alert from '../components/ui/Alert';
import AppImportStepper from '../components/import/AppImportStepper';
import Title from '../components/ui/Title';
import ButtonCard from '../components/ui/ButtonCard';
import { Badge } from '../components/ui/Badge';
import ButtonApp from '../components/ui/ButtonApp';
import { LoadingState } from '../components/ui/LoadingState';

interface App {
  app_id: number;
  name: string;
  created_at: string;
  owner_id: number;
  owner_name?: string;
  owner_email?: string;
  role: string;
  langsmith_configured: boolean;
  agent_rate_limit: number;
  agent_count: number;
  repository_count: number;
  domain_count: number;
  silo_count: number;
  collaborator_count: number;
}

function getAppRoleLabel(role: string) {
  if (role === 'owner') return 'Owner';
  if (role === 'administrator') return 'Administrator';
  if (role === 'editor') return 'Editor';
  if (role === 'viewer') return 'Viewer';
  return role;
}

function AppsPage() {
  const { user } = useUser();
  const isEditor = user?.is_admin || (user?.is_editor ?? false);
  const [apps, setApps] = useState<App[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);

  useEffect(() => {
    void loadApps();
  }, []);

  async function loadApps() {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      const response = await apiService.getApps();
      setApps(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load apps');
    } finally {
      setLoading(false);
    }
  }

  async function refreshApps() {
    try {
      const response = await apiService.getApps();
      setApps(response);
    } catch (err) {
      console.error('Failed to refresh apps:', err);
    }
  }

  async function handleCreateApp(data: { name: string }) {
    await apiService.createApp(data);
    setShowCreateModal(false);
    setSuccess(`App "${data.name}" created successfully!`);
    setError(null);
    void refreshApps();
    setTimeout(() => setSuccess(null), 5000);
  }

  // Function to handle import completion
  function handleImportComplete() {
    setShowImportModal(false);
    setSuccess('App imported successfully!');
    void refreshApps();
    setTimeout(() => setSuccess(null), 5000);
  }

  // Show loading spinner while fetching data
  if (loading) {
    return (
      <LoadingState variant="page" message="Loading apps..." />
    );
  }

  // Main render
  return (
    <div className="space-y-6">
      {success && <Alert type="success" message={success} onDismiss={() => setSuccess(null)} />}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Header */}
      <div className="flex items-center justify-between">
        {/*<div>
          <h1 className="text-2xl font-bold text-gray-900">My Apps</h1>
          <p className="text-gray-600">Manage your AI applications and workspaces</p>
        </div>*/}
        <Title
          titulo="My Apps"
          subtitulo="Manage your AI applications and workspaces"
          variant="titPrincipal"
        />
        {isEditor && (
          <div className="flex gap-3">
            <ButtonApp
              label="Import App"
              variant="secondary"
              size="medium"
              icon={<Download className="h-4 w-4" aria-hidden="true" />}
              className="h-[41px] !py-2"
              onClick={() => setShowImportModal(true)}
            />
            <ButtonApp
              label="+ New App"
              variant="primary"
              size="spacious"
              className="h-[41px] !py-2"
              onClick={() => setShowCreateModal(true)}
            />
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
        {apps.map((app) => {
          const ownerBonus = app.role === 'owner' ? 1 : 0;
          const totalCollaborators = app.collaborator_count + ownerBonus;

          return (
            <ButtonCard
              key={app.app_id}
              ariaLabel={`Open ${app.name}`}
              onClick={() => { globalThis.location.href = `/apps/${app.app_id}`; }}
            >
              <div className="mb-3 flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center overflow-hidden rounded-md border-[0.8px] border-[#FF682C] text-sm font-medium">
                    TP
                  </div>
                  <span className="min-w-0 text-[18px] leading-tight text-ink dark:text-ink-dark">{app.name}</span>
                </div>
                <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-fg-secondary">
                  {getAppRoleLabel(app.role)}
                </span>
              </div>
              <p className="mb-4 whitespace-pre-line text-[13.5px] leading-[1.45] text-fg-secondary dark:text-fg-secondary-dark">
                {app.created_at ? new Date(app.created_at).toLocaleDateString() : '-'}
              </p>
              <div className="mb-4 flex flex-wrap gap-2">
                <Badge
                  key="langsmith-configuration"
                  label={app.langsmith_configured ? 'Configured' : 'Not configured'}
                  variant={app.langsmith_configured ? 'success' : 'error'}
                />
              </div>
              <div className="pointer-events-none relative z-0 mt-auto border-t border-[#e0ddd6] dark:border-line-dark">
                <div className="overflow-x-auto pt-2">
                  <table className="table-fixed text-center leading-none">
                    <thead>
                      <tr>
                        {[
                          { label: 'AGENTS', value: app.agent_count },
                          { label: 'REPOS', value: app.repository_count },
                          { label: 'DOMAINS', value: app.domain_count },
                          { label: 'SILOS', value: app.silo_count },
                          { label: 'COLLABS', value: totalCollaborators },
                        ].map((stat, index, stats) => (
                          <th
                            key={stat.label}
                            className={`px-2 py-0 text-[8px] font-medium uppercase tracking-[0.04em] text-fg-tertiary dark:text-fg-tertiary-dark ${index < stats.length - 1 ? 'border-r border-[#e0ddd6] dark:border-line-dark' : ''}`}
                          >
                            {stat.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        {[
                          { label: 'AGENTS', value: app.agent_count },
                          { label: 'REPOS', value: app.repository_count },
                          { label: 'DOMAINS', value: app.domain_count },
                          { label: 'SILOS', value: app.silo_count },
                          { label: 'COLLABS', value: totalCollaborators },
                        ].map((stat, index, stats) => (
                          <td
                            key={stat.label}
                            className={`px-2 py-0 text-sm font-semibold text-ink dark:text-ink-dark ${index < stats.length - 1 ? 'border-r border-[#e0ddd6] dark:border-line-dark' : ''}`}
                          >
                            {stat.value}
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </ButtonCard>
          );
        })}
      </div>

      {/* Legacy table kept as reference during the migration. */}
      {/*<Table
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
                  />*/}
                  {/* Tooltip */}
                  {/*<div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-10">
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
      />*/}


      {!loading && apps.length === 0 && isEditor && (
        <div className="text-center py-6">
          <ButtonApp
            label="Create App"
            onClick={() => setShowCreateModal(true)}
            variant="primary"
            size="medium"
          />
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