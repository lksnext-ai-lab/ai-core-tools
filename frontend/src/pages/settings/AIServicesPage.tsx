import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { Bot, Users, ArrowDownToLine, ClipboardCopy, Pencil, Trash2, Upload} from 'lucide-react';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import ActionDropdown from '../../components/ui/ActionDropdown';
import ImportModal, { type ImportResponse, type ConflictMode } from '../../components/ui/ImportModal';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import {  ProviderBadge } from '../../components/ui/Badge';
import { AppRole } from '../../types/roles';
import type { ServiceLifecycleFields } from '../../types/services';
import ServiceStatusBadge from '../../components/ui/ServiceStatusBadge';
import UsedByButton from '../../components/services/UsedByButton';
import SystemServiceBadge from '../../components/services/SystemServiceBadge';
import ServiceUsageModal from '../../components/services/ServiceUsageModal';
import { useServiceConnectionTest } from '../../components/services/useServiceConnectionTest';
import { SERVICE_USAGE_STRINGS } from '../../utils/serviceLifecycle';
import LoadingState from '../../components/ui/LoadingState';
import Title from '../../components/ui/Title';
import ButtonApp from '../../components/ui/ButtonApp';
import BackgroundImage from '../../components/ui/BackgroundImage';
import SidePanel from '../../components/ui/SidePanel';
import Spinner from '../../components/ui/Spinner';

interface AIService extends Partial<ServiceLifecycleFields> {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
  needs_api_key?: boolean;
  is_system?: boolean;
  last_error?: string | null;
  last_error_at?: string | null;
}

function AIServicesPage() {
  const { appId } = useParams();
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const api = {
    getAll: (id: number) => import('../../services/api').then(m => m.apiService.getAIServices(id)),
    getOne: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.getAIService(id, sid)),
    create: (id: number, data: any) => import('../../services/api').then(m => m.apiService.createAIService(id, data)),
    update: (id: number, sid: number, data: any) => import('../../services/api').then(m => m.apiService.updateAIService(id, sid, data)),
    delete: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.deleteAIService(id, sid)),
    copy: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.copyAIService(id, sid)),
  };

  const cache = {
    get: (id: string) => settingsCache.getAIServices(id),
    set: (id: string, data: any[]) => settingsCache.setAIServices(id, data),
    invalidate: (id: string) => settingsCache.invalidateAIServices(id),
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
    setIsModalOpen,
    setEditingService,
    forceReload,
  } = useServicesManager<AIService>(appId, api as any, cache as any, { entity: 'AI service' });

  const { testAction, modal: connectionTestModal } = useServiceConnectionTest('AI');
  const [showImportModal, setShowImportModal] = useState(false);
  const [exportingServiceId, setExportingServiceId] = useState<number | null>(null);
  const [usageService, setUsageService] = useState<{
    id: number;
    name: string;
    deleteRequested?: boolean;
  } | null>(null);
  const [notification, setNotification] = useState<{message: string; type: 'success' | 'error'} | null>(null);

  async function testConnection(serviceId: number) {
    if (!appId) throw new Error('App ID not found');
    const apiService = (await import('../../services/api')).apiService;
    return apiService.testAIServiceConnection(Number.parseInt(appId, 10), serviceId);
  }

  async function handleExport(serviceId: number) {
    if (!appId) return;
    setExportingServiceId(serviceId);
    
    try {
      const apiService = (await import('../../services/api')).apiService;
      const blob = await apiService.exportAIService(Number.parseInt(appId), serviceId);
      
      // Find service name for filename
      const service = services.find(s => s.service_id === serviceId);
      const serviceName = service?.name || 'ai-service';
      const sanitizedName = serviceName.replaceAll(/[^a-z0-9]/gi, '-').toLowerCase();
      const timestamp = new Date().toISOString().split('T')[0];
      const filename = `ai-service-${sanitizedName}-${timestamp}.json`;
      
      // Create download link
      const url = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      globalThis.URL.revokeObjectURL(url);
      a.remove();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to export service');
    } finally {
      setExportingServiceId(null);
    }
  }

  async function handleImport(
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<ImportResponse> {
    if (!appId) throw new Error('App ID not found');
    
    try {
      const apiService = (await import('../../services/api')).apiService;
      const result = await apiService.importAIService(
        Number.parseInt(appId),
        file,
        conflictMode,
        newName
      );
      
      if (result.success) {
        // Close modal immediately
        setShowImportModal(false);
        // Show success notification
        setNotification({
          message: result.message || 'Import completed successfully',
          type: 'success'
        });
        // Refresh the list
        void forceReload();
        // Auto-dismiss notification after 5 seconds
        setTimeout(() => setNotification(null), 5000);
      }
      
      return result;
    } catch (err) {
      // Show error notification
      setNotification({
        message: err instanceof Error ? err.message : 'Import failed',
        type: 'error'
      });
      setTimeout(() => setNotification(null), 5000);
      // Re-throw the error so ImportModal can catch it
      throw err;
    }
  }

  if (loading) return (
    <LoadingState variant="page" message="Loading AI services..." />
  );

  if (error) return (
    <div className="p-6">
      <Alert type="error" message={error} onDismiss={() => { setIsModalOpen(false); setEditingService(null); }} />
    </div>
  );

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <Title variant='titSecundario' titulo='Ai Services' subtitulo='Manage language models and AI providers for your agents'></Title>
        {canEdit && (
          <div className="flex gap-2">
            <ButtonApp
              label="Import"
              onClick={() => setShowImportModal(true)}
              icon={<Upload className="w-4 h-4" aria-hidden="true" />}
              variant="secondary"
              size="medium"
            />
            <ButtonApp
              label="Add AI Service"
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
            render: (service: AIService) => (
              <span className="flex items-center gap-1.5">
                <BackgroundImage icon={Bot} variant="marron" />
                {canEdit && !service.is_system ? (
                  <button type="button" className="text-sm font-medium text-fg dark:text-fg-dark text-left" onClick={() => handleEdit(service.service_id)}>
                    {service.name}
                  </button>
                ) : (
                  <span className="text-sm font-medium text-fg dark:text-fg-dark">{service.name}</span>
                )}
                {service.is_system && <SystemServiceBadge />}
              </span>
            )
          },
          { header: 'Model', accessor: 'model_name', className: 'text-xs font-medium text-fg-secondary dark:text-fg-secondary-dark' },
          { header: 'Provider', render: (service: AIService) => (
            <ProviderBadge provider={service.provider} />
          )},
          { header: 'Status', render: (service: AIService) => (
            <ServiceStatusBadge needsApiKey={service.needs_api_key} lastError={service.last_error} lastErrorAt={service.last_error_at} lifecycleStatus={service.lifecycle_status} endOfServiceAt={service.end_of_service_at} deprecationNotice={service.deprecation_notice} />
          )},
          { header: 'Created', className:'text-xs text-fg-secondary dark:text-fg-secondary-dark', render: (service: any) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: AIService) => (
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
                {
                  label: exportingServiceId === service.service_id ? 'Exporting...' : 'Export',
                  onClick: () => void handleExport(service.service_id),
                  icon: exportingServiceId === service.service_id ? <Spinner size="sm" tone="current" /> : <ArrowDownToLine className="w-4 h-4" />,
                  variant: 'primary' as const,
                  disabled: exportingServiceId === service.service_id
                },
                { label: 'Edit', onClick: () => void handleEdit(service.service_id), icon: <Pencil className="w-4 h-4" />, variant: 'primary' as const },
                { label: 'Copy', onClick: () => void handleCopy(service.service_id), icon: <ClipboardCopy className="w-4 h-4" />, variant: 'primary' as const },
                { label: 'Delete', onClick: () => setUsageService({ id: service.service_id, name: service.name, deleteRequested: true }), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' as const }
              ]} size="sm" />
            ) : (
              <UsedByButton serviceName={service.name} onClick={() => setUsageService({ id: service.service_id, name: service.name })} />
            )
          ) }
        ]}
        emptyIcon={<Bot className="w-10 h-10 text-gray-300" />}
        emptyMessage="No AI Services"
        emptySubMessage="Add your first AI service to start using language models in your agents."
        loading={loading}
      />

      {!loading && services.length === 0 && canEdit && (
        <div className="text-center py-6">
          <button onClick={handleCreate} className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg">Add First AI Service</button>
        </div>
      )}

      {notification && (
        <Alert
          type={notification.type}
          message={notification.message}
          onDismiss={() => setNotification(null)}
          className="mb-4"
        />
      )}

      <Alert
        type="info"
        title="About AI Services"
        className="mt-6"
        message="AI Services define the language models your agents can use. Configure OpenAI, Azure OpenAI, Anthropic Claude, or local models like Ollama. Each service requires proper authentication and endpoint configuration."
      />

      {isModalOpen && !editingService && (
        <ServiceWizard
          isOpen
          kind="ai"
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
          kind="ai"
          scope="app"
          appId={appId ? Number.parseInt(appId) : undefined}
          service={editingService}
          existingNames={services.map((s) => s.name)}
          onClose={handleClose}
          onSave={handleSave}
        />
      )}

      {connectionTestModal}

      {/* Service usage side panel — fixed wrapper that starts below the 56px (h-14) app header */}
      {usageService && appId && (
        <div className="fixed inset-x-0 bottom-0 top-14 z-10 !mt-0">
          <SidePanel
            open
            side="right"
            onClose={() => setUsageService(null)}
            title="AI Services"
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
              kind="ai"
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

      {/* Import Modal */}
      <ImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImport={handleImport}
        componentType="ai_service"
        componentLabel="AI Service"
      />
    </div>
  );
}

export default AIServicesPage;