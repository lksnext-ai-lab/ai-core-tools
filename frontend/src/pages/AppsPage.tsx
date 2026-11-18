import { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import { useUser } from '../contexts/UserContext';
import { Download, Bot, Settings, Upload, LogOut, Trash2 } from 'lucide-react';
import Modal from '../components/ui/Modal';
import AppForm from '../components/forms/AppForm';
import ActionDropdown, { type ActionItem } from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';
import AppImportStepper from '../components/import/AppImportStepper';
import Title from '../components/ui/Title';
import ButtonCard from '../components/ui/ButtonCard';
import { Badge } from '../components/ui/Badge';
import ButtonApp from '../components/ui/ButtonApp';
import { LoadingState } from '../components/ui/LoadingState';
import { useConfirm } from '../contexts/ConfirmContext';
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
  const confirm = useConfirm();

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

  async function handleExportApp(app: App) {
    try {
      setError(null);
      const blob = await apiService.exportFullApp(app.app_id);
      const url = globalThis.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const timestamp = new Date().toISOString().split('T')[0];
      const sanitizedName = app.name.replaceAll(/[^a-z0-9]/gi, '_').toLowerCase();
      link.href = url;
      link.download = `app-${sanitizedName}-${timestamp}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      globalThis.URL.revokeObjectURL(url);
      setSuccess(t('appsPage.appExportedSuccessfully', { name: app.name }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('appsPage.appExportFailed', { name: app.name }));
    }
  }

  async function handleLeaveApp(app: App) {
    const confirmed = await confirm({
      title: t('appsPage.confirmLeaveTitle'),
      message: t('appsPage.confirmLeaveMessage', { name: app.name }),
      confirmLabel: t('appsPage.actions.leaveApp'),
      variant: 'warning',
    });
    if (!confirmed) return;

    try {
      await apiService.leaveApp(app.app_id);
      setApps((currentApps) => currentApps.filter((currentApp) => currentApp.app_id !== app.app_id));
      setError(null);
      setSuccess(t('appsPage.appLeftSuccessfully', { name: app.name }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('appsPage.appLeaveFailed', { name: app.name }));
    }
  }

  async function handleDeleteApp(app: App) {
    const confirmed = await confirm({
      title: t('appsPage.confirmDeleteTitle'),
      message: t('appsPage.confirmDeleteMessage', { name: app.name }),
      confirmLabel: t('appsPage.actions.deleteApp'),
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await apiService.deleteApp(app.app_id);
      setApps((currentApps) => currentApps.filter((currentApp) => currentApp.app_id !== app.app_id));
      setError(null);
      setSuccess(t('appsPage.appDeletedSuccessfully', { name: app.name }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('appsPage.appDeleteFailed', { name: app.name }));
    }
  }

  // Function to create a new app
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
          const actions: ActionItem[] = [
            {
              label: t('appsPage.actions.manageAgents'),
              onClick: () => { globalThis.location.href = `/apps/${app.app_id}/agents`; },
              icon: <Bot className="w-4 h-4" />,
              variant: 'secondary',
            },
            {
              label: t('appsPage.actions.appSettings'),
              onClick: () => { globalThis.location.href = `/apps/${app.app_id}/settings`; },
              icon: <Settings className="w-4 h-4" />,
              variant: 'secondary',
            },
            {
              label: t('appsPage.actions.exportApp'),
              onClick: () => { void handleExportApp(app); },
              icon: <Upload className="w-4 h-4" />,
              variant: 'secondary',
            },
            ...(app.role === 'owner'
              ? [{
                  label: t('appsPage.actions.deleteApp'),
                  onClick: () => { void handleDeleteApp(app); },
                  icon: <Trash2 className="w-4 h-4" />,
                  variant: 'danger' as const,
                }]
              : [{
                  label: t('appsPage.actions.leaveApp'),
                  onClick: () => { void handleLeaveApp(app); },
                  icon: <LogOut className="w-4 h-4" />,
                  variant: 'danger' as const,
                }]),
          ];

          return (
            <ButtonCard
              key={app.app_id}
              ariaLabel={t('appsPage.openApp', { name: app.name })}
              onClick={() => { globalThis.location.href = `/apps/${app.app_id}`; }}
              interactiveChildren
            >
              <div className="mb-3 flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md border-[1.5px] border-accent bg-surface font-display text-[15px] font-medium text-ink dark:border-accent-dark dark:bg-surface-dark dark:text-ink-dark">
                    TP
                  </div>
                  <div className="flex min-w-0 flex-col items-start">
                    <span className="min-w-0 font-display text-[18px] leading-[1.3] tracking-[-0.02em] text-ink [overflow-wrap:anywhere] dark:text-ink-dark">{app.name}</span>
                    <p className="mt-0.5 whitespace-pre-line text-[12px] leading-[1.45] text-fg-tertiary dark:text-fg-tertiary-dark">
                      {app.created_at ? new Date(app.created_at).toLocaleDateString(i18n.resolvedLanguage) : '-'}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  
                  <ActionDropdown
                    actions={actions}
                    size="sm"
                    triggerText={t('appsPage.actions.menu')}
                    triggerAriaLabel={t('appsPage.actions.menuForApp', { name: app.name })}
                    className="pointer-events-auto relative z-10"
                  />
                </div>
              </div>
              
              <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1.5">
                <span className="whitespace-nowrap rounded-full bg-surface px-2.5 py-1 text-[11px] font-medium text-fg-secondary dark:bg-surface-dark dark:text-fg-secondary-dark">
                  {getAppRoleTranslationKey(app.role)
                    ? t(getAppRoleTranslationKey(app.role)!)
                    : app.role}
                </span>
                <Badge
                  key="langsmith-configuration"
                  label={app.langsmith_configured ? t('appsPage.configured') : t('appsPage.notConfigured')}
                  variant={app.langsmith_configured ? 'success' : 'warning'}
                />
              </div>
              <dl className="pointer-events-none relative z-0 mt-auto grid grid-cols-5 gap-x-2 gap-y-2.5 border-t border-line pt-3 dark:border-line-dark">
                {[
                  { label: t('appsPage.stats.agents'), value: app.agent_count },
                  { label: t('appsPage.stats.repositories'), value: app.repository_count },
                  { label: t('appsPage.stats.domains'), value: app.domain_count },
                  { label: t('appsPage.stats.silos'), value: app.silo_count },
                  { label: t('appsPage.stats.collaborators'), value: totalCollaborators },
                ].map((stat) => (
                  <div key={stat.label} className="flex min-w-0 flex-col-reverse gap-px">
                    <dt className="truncate text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark">{stat.label}</dt>
                    <dd className={`font-display text-[18px] font-medium leading-[1.2] ${stat.value === 0 ? 'text-fg-tertiary dark:text-fg-tertiary-dark' : 'text-ink dark:text-ink-dark'}`}>
                      {stat.value}
                    </dd>
                  </div>
                ))}
              </dl>
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