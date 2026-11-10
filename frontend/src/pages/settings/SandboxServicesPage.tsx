import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Pencil, ClipboardCopy, Trash2, Users } from 'lucide-react';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import { AppRole } from '../../types/roles';
import type { ServiceLifecycleFields } from '../../types/services';
import ServiceStatusBadge from '../../components/ui/ServiceStatusBadge';
import UsedByButton from '../../components/services/UsedByButton';
import SystemServiceBadge from '../../components/services/SystemServiceBadge';
import ServiceUsageModal from '../../components/services/ServiceUsageModal';
import { useServiceConnectionTest } from '../../components/services/useServiceConnectionTest';
import { SERVICE_USAGE_STRINGS } from '../../utils/serviceLifecycle';
import Title from '../../components/ui/Title';
import LoadingState from '../../components/ui/LoadingState';
import ButtonApp from '../../components/ui/ButtonApp';
import BackgroundImage from '../../components/ui/BackgroundImage';
import SidePanel from '../../components/ui/SidePanel';
import { ProviderBadge } from '../../components/ui/Badge';

interface SandboxService extends Partial<ServiceLifecycleFields> {
  service_id: number;
  name: string;
  provider: string;
  created_at: string;
  needs_api_key?: boolean;
  is_system?: boolean;
}

function SandboxServicesPage() {
  const { appId } = useParams();
  const { t, i18n } = useTranslation('common');
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const api = {
    getAll: (id: number) => import('../../services/api').then(m => m.apiService.getSandboxServices(id)),
    getOne: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.getSandboxService(id, sid)),
    create: (id: number, data: any) => import('../../services/api').then(m => m.apiService.createSandboxService(id, data)),
    update: (id: number, sid: number, data: any) => import('../../services/api').then(m => m.apiService.updateSandboxService(id, sid, data)),
    delete: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.deleteSandboxService(id, sid)),
    copy: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.copySandboxService(id, sid)),
  };

  const cache = {
    get: (id: string) => settingsCache.getSandboxServices(id),
    set: (id: string, data: any[]) => settingsCache.setSandboxServices(id, data),
    invalidate: (id: string) => settingsCache.invalidateSandboxServices(id),
  };

  const {
    services,
    loading,
    error,
    isModalOpen,
    editingService,
    handleClose,
    handleCreate,
    handleDelete,
    handleEdit,
    handleCopy,
    handleSave,
    forceReload,
    setIsModalOpen,
    setEditingService,
  } = useServicesManager<SandboxService>(appId, api as any, cache as any, { entity: t('sandboxServicesPage.entity') });

  const [usageService, setUsageService] = useState<{
    id: number;
    name: string;
    deleteRequested?: boolean;
  } | null>(null);
  const { testAction, modal: connectionTestModal } = useServiceConnectionTest('sandbox');

  async function testConnection(serviceId: number) {
    if (!appId) throw new Error(t('sandboxServicesPage.appIdNotFound'));
    const apiService = (await import('../../services/api')).apiService;
    return apiService.testSandboxServiceConnection(Number.parseInt(appId, 10), serviceId) as Promise<any>;
  }

  if (loading) return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title variant='titSecundario' titulo={t('sandboxServicesPage.title')} subtitulo={t('sandboxServicesPage.subtitle')} />
      </div>
      <LoadingState variant="page" message={t('sandboxServicesPage.loading')} />
    </div>
  );

  if (error) return (
    <div className="p-6">
      <div className="flex items-center justify-between">
        <Title variant='titSecundario' titulo={t('sandboxServicesPage.title')} subtitulo={t('sandboxServicesPage.subtitle')} />
      </div>
      <Alert type="error" message={error} onDismiss={() => { setIsModalOpen(false); setEditingService(null); }} />
    </div>
  );

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <Title variant='titSecundario' titulo={t('sandboxServicesPage.title')} subtitulo={t('sandboxServicesPage.subtitle')} />
        {canEdit && (
          <div className="flex gap-2">
            <ButtonApp
              label={t('sandboxServicesPage.addService')}
              onClick={handleCreate}
              icon={<span aria-hidden="true">+</span>}
              variant="primary"
              size="medium"
            />
          </div>
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      <Table
        data={services}
        stickyEdgeColumns
        keyExtractor={(service) => (service as any).service_id.toString()}
        columns={[
          {
            header: t('sandboxServicesPage.columns.name'),
            render: (service: SandboxService) => (
              <span className="flex items-center gap-1.5">
                <BackgroundImage icon={Box} size={34} iconSize={17} variant="marron" className="mr-2" />
                {canEdit && !service.is_system ? (
                  <button type="button" className="text-sm font-medium text-fg dark:text-fg-dark transition-colors text-left" onClick={() => handleEdit(service.service_id)}>
                    {service.name}
                  </button>
                ) : (
                  <span className="text-sm font-medium text-fg dark:text-fg-dark">{service.name}</span>
                )}
                {service.is_system && <SystemServiceBadge />}
              </span>
            )
          },
          { header: t('sandboxServicesPage.columns.provider'), render: (service: SandboxService) => (
            <ProviderBadge provider={service.provider} />
            
          )},
          { header: t('sandboxServicesPage.columns.status'), render: (service: SandboxService) => (
            <ServiceStatusBadge needsApiKey={service.needs_api_key} lifecycleStatus={service.lifecycle_status} endOfServiceAt={service.end_of_service_at} deprecationNotice={service.deprecation_notice} />
          )},
          { header: t('sandboxServicesPage.columns.created'), className:'text-xs text-fg-secondary dark:text-fg-secondary-dark align-center px-6 py-3', render: (service: any) => (service.created_at ? new Date(service.created_at).toLocaleDateString(i18n.resolvedLanguage) : t('sandboxServicesPage.notAvailable')) },
          { header: t('sandboxServicesPage.columns.actions'), sticky: 'right', className: 'relative', render: (service: SandboxService) => {
            if (service.is_system) {
              return (
                <span className="flex flex-col items-center gap-1">
                  <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs">{t('sandboxServicesPage.system')}</span>
                  <UsedByButton serviceName={service.name} onClick={() => setUsageService({ id: service.service_id, name: service.name })} />
                </span>
              );
            }
            if (!canEdit) {
              return <UsedByButton serviceName={service.name} onClick={() => setUsageService({ id: service.service_id, name: service.name })} />;
            }
            return (
              <ActionDropdown actions={[
                { label: SERVICE_USAGE_STRINGS.action, onClick: () => setUsageService({ id: service.service_id, name: service.name }), icon: <Users className="w-4 h-4" /> },
                testAction(service.service_id, service.name, () => testConnection(service.service_id)),
                { label: t('sandboxServicesPage.actions.edit'), onClick: () => void handleEdit(service.service_id), icon: <Pencil className="w-4 h-4" />, variant: 'primary' as const },
                { label: t('sandboxServicesPage.actions.copy'), onClick: () => void handleCopy(service.service_id), icon: <ClipboardCopy className="w-4 h-4" />, variant: 'primary' as const },
                { label: t('sandboxServicesPage.actions.delete'), onClick: () => setUsageService({ id: service.service_id, name: service.name, deleteRequested: true }), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' as const }
              ]} size="sm" triggerAriaLabel={t('sandboxServicesPage.actions.menuForService', { name: service.name })} />
            );
          } }
        ]}
        emptyIcon={<BackgroundImage icon={Box} size={64} iconSize={32} />}
        emptyMessage={t('sandboxServicesPage.empty.title')}
        emptySubMessage={t('sandboxServicesPage.empty.subtitle')}
        loading={loading}
      />

      {!loading && services.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('sandboxServicesPage.addFirstService')}
            onClick={handleCreate}
            variant="primary"
            size="medium"
          />
        </div>
      )}

      <Alert
        type="info"
        title={t('sandboxServicesPage.about.title')}
        className="mt-6"
        message={t('sandboxServicesPage.about.message')}
      />

      {isModalOpen && !editingService && (
        <ServiceWizard
          isOpen
          kind="sandbox"
          scope="app"
          appId={appId ? Number.parseInt(appId) : undefined}
          existingNames={services.map((s) => s.name)}
          onClose={handleClose}
          onSave={handleSave}
        />
      )}

      {isModalOpen && editingService && (
        <CompactServiceEditor
          isOpen
          variant="panel"
          kind="sandbox"
          scope="app"
          appId={appId ? Number.parseInt(appId) : undefined}
          service={editingService}
          existingNames={services.map((s) => s.name)}
          onClose={handleClose}
          onSave={handleSave}
        />
      )}

      {/* Service usage side panel — fixed wrapper that starts below the 56px (h-14) app header */}
      {usageService && appId && (
        <div className="fixed inset-x-0 bottom-0 top-14 z-30 !mt-0">
          <SidePanel
            open
            side="right"
            onClose={() => setUsageService(null)}
            title={t('sandboxServicesPage.title')}
            headerActions={(
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] normal-case tracking-normal text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
                {SERVICE_USAGE_STRINGS.action}
              </span>
            )}
            widthClassName="w-[640px] max-w-full"
          >
            <ServiceUsageModal
              key={usageService.id}
              variant="panel"
              kind="sandbox"
              scope="app"
              canNavigate={hasMinRole(AppRole.EDITOR)}
              appId={Number.parseInt(appId, 10)}
              serviceId={usageService.id}
              serviceName={usageService.name}
              canMove={canEdit}
              onMoved={() => void forceReload()}
              onDelete={usageService.deleteRequested ? () => handleDelete(usageService.id) : undefined}
              onClose={() => setUsageService(null)}
            />
          </SidePanel>
        </div>
      )}

      {connectionTestModal}
    </div>
  );
}

export default SandboxServicesPage;
