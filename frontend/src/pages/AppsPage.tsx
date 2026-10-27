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