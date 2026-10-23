import { useParams } from 'react-router-dom';
import { useState } from 'react';
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
  } = useServicesManager<SandboxService>(appId, api as any, cache as any, { entity: 'sandbox service' });

  const [usageService, setUsageService] = useState<{
    id: number;
    name: string;
    deleteRequested?: boolean;
  } | null>(null);
  const { testAction, modal: connectionTestModal } = useServiceConnectionTest('sandbox');

  async function testConnection(serviceId: number) {
    if (!appId) throw new Error('App ID not found');
    const apiService = (await import('../../services/api')).apiService;
    return apiService.testSandboxServiceConnection(Number.parseInt(appId, 10), serviceId) as Promise<any>;
  }

  if (loading) return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title variant='titSecundario' titulo="Sandbox Services" subtitulo="Manage isolated code-execution environments used by the Code Interpreter capability" />
      </div>
      <LoadingState variant="page" message="Loading sandbox services..." />
    </div>
  );

  if (error) return (
    <div className="p-6">
      <div className="flex items-center justify-between">
        <Title variant='titSecundario' titulo="Sandbox Services" subtitulo="Manage isolated code-execution environments used by the Code Interpreter capability" />
      </div>
      <Alert type="error" message={error} onDismiss={() => { setIsModalOpen(false); setEditingService(null); }} />
    </div>
  );

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <Title variant='titSecundario' titulo='Sandbox Services' subtitulo='Manage isolated code-execution environments used by the Code Interpreter capability'/>
        {canEdit && (
          <div className="flex gap-2">
            <ButtonApp
              label="Add Sandbox Service"
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
        keyExtractor={(service) => (service as any).service_id.toString()}
        columns={[
          {
            header: 'Name',
            render: (service: SandboxService) => (
              <span className="flex items-center gap-1.5">
                <BackgroundImage icon={Box} size={28} iconSize={14} variant="marron" className="mr-2" />
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
          { header: 'Provider', render: (service: SandboxService) => (
            <ProviderBadge provider={service.provider} />
            
          )},
          { header: 'Status', render: (service: SandboxService) => (
            <ServiceStatusBadge needsApiKey={service.needs_api_key} lifecycleStatus={service.lifecycle_status} endOfServiceAt={service.end_of_service_at} deprecationNotice={service.deprecation_notice} />
          )},
          { header: 'Created', className:'text-xs text-fg-secondary dark:text-fg-secondary-dark align-center px-6 py-3', render: (service: any) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: SandboxService) => (
            service.is_system ? (
              // System services are managed by platform admins; the app can only see where they are used.
              <span className="inline-flex items-center gap-3">
                <span className="text-gray-400 text-sm">System</span>
                <UsedByButton serviceName={service.name} onClick={() => setUsageService({ id: service.service_id, name: service.name })} />
              </span>
            ) : canEdit ? (
              <ActionDropdown triggerAriaLabel={`Actions for ${service.name}`} actions={[
                { label: SERVICE_USAGE_STRINGS.action, onClick: () => setUsageService({ id: service.service_id, name: service.name }), icon: <Users className="w-4 h-4" /> },
                testAction(service.service_id, service.name, () => testConnection(service.service_id)),
                { label: 'Edit', onClick: () => void handleEdit(service.service_id), icon: <Pencil className="w-4 h-4" />, variant: 'primary' as const },
                { label: 'Copy', onClick: () => void handleCopy(service.service_id), icon: <ClipboardCopy className="w-4 h-4" />, variant: 'primary' as const },
                { label: 'Delete', onClick: () => setUsageService({ id: service.service_id, name: service.name, deleteRequested: true }), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' as const }
              ]} size="sm" />
            ) : (
              <UsedByButton serviceName={service.name} onClick={() => setUsageService({ id: service.service_id, name: service.name })} />
            )
          ) }
        ]}
        emptyIcon={<Box className="w-10 h-10 text-gray-300" />}
        emptyMessage="No Sandbox Services"
        emptySubMessage="Add a sandbox service to let agents run the Code Interpreter capability."
        loading={loading}
      />

      {!loading && services.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label="Add First Sandbox Service"
            onClick={handleCreate}
            variant="primary"
            size="medium"
          />
        </div>
      )}

      <Alert
        type="info"
        title="About Sandbox Services"
        className="mt-6"
        message="Sandbox Services configure the isolated environment where agents execute Python code when the Code Interpreter capability is enabled. Configure OpenSandbox (self-hosted container), Daytona, or E2B (managed cloud sandboxes)."
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
        <div className="fixed inset-x-0 bottom-0 top-14 z-10 !mt-0">
          <SidePanel
            open
            side="right"
            onClose={() => setUsageService(null)}
            title="Sandbox Services"
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
