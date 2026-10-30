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
import { useTranslation } from 'react-i18next';

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

function getAppRoleTranslationKey(role: string) {
  if (role === 'owner') return 'appsPage.roles.owner';
  if (role === 'administrator') return 'appsPage.roles.administrator';
  if (role === 'editor') return 'appsPage.roles.editor';
  if (role === 'viewer') return 'appsPage.roles.viewer';
  return null;
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
  const { t, i18n } = useTranslation('common');

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
      setError(err instanceof Error ? err.message : t('appsPage.loadFailed'));
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
    setSuccess(t('appsPage.appCreatedSuccessfully', { name: data.name }));
    setError(null);
    void refreshApps();
    setTimeout(() => setSuccess(null), 5000);
  }

  // Function to handle import completion
  function handleImportComplete() {
    setShowImportModal(false);
    setSuccess(t('appsPage.appImportedSuccessfully'));
    void refreshApps();
    setTimeout(() => setSuccess(null), 5000);
  }

  // Show loading spinner while fetching data
  if (loading) {
    return (
      <LoadingState variant="page" message={t('appsPage.loading')} />
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
          titulo={t('appsPage.title')}
          subtitulo={t('appsPage.subtitle')}
          variant="titPrincipal"
        />
        {isEditor && (
          <div className="flex gap-3">
            <ButtonApp
              label={t('appsPage.importApp')}
              variant="secondary"
              size="medium"
              icon={<Download className="h-4 w-4" aria-hidden="true" />}
              className="h-[41px] !py-2"
              onClick={() => setShowImportModal(true)}
            />
            <ButtonApp
              label={`+ ${t('appsPage.newApp')}`}
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
              ariaLabel={t('appsPage.openApp', { name: app.name })}
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
                  {getAppRoleTranslationKey(app.role)
                    ? t(getAppRoleTranslationKey(app.role)!)
                    : app.role}
                </span>
              </div>
              <p className="mb-4 whitespace-pre-line text-[13.5px] leading-[1.45] text-fg-secondary dark:text-fg-secondary-dark">
                {app.created_at ? new Date(app.created_at).toLocaleDateString(i18n.resolvedLanguage) : '-'}
              </p>
              <div className="mb-4 flex flex-wrap gap-2">
                <Badge
                  key="langsmith-configuration"
                  label={app.langsmith_configured ? t('appsPage.configured') : t('appsPage.notConfigured')}
                  variant={app.langsmith_configured ? 'success' : 'error'}
                />
              </div>
              <div className="pointer-events-none relative z-0 mt-auto border-t border-[#e0ddd6] dark:border-line-dark">
                <div className="overflow-x-auto pt-2">
                  <table className="table-fixed text-center leading-none">
                    <thead>
                      <tr>
                        {[
                          { label: t('appsPage.stats.agents'), value: app.agent_count },
                          { label: t('appsPage.stats.repositories'), value: app.repository_count },
                          { label: t('appsPage.stats.domains'), value: app.domain_count },
                          { label: t('appsPage.stats.silos'), value: app.silo_count },
                          { label: t('appsPage.stats.collaborators'), value: totalCollaborators },
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
                          { label: t('appsPage.stats.agents'), value: app.agent_count },
                          { label: t('appsPage.stats.repositories'), value: app.repository_count },
                          { label: t('appsPage.stats.domains'), value: app.domain_count },
                          { label: t('appsPage.stats.silos'), value: app.silo_count },
                          { label: t('appsPage.stats.collaborators'), value: totalCollaborators },
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
            label={t('appsPage.createApp')}
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
        title={t('appsPage.createNewApp')}
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