import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { Bot, Users, ArrowDownToLine, ClipboardCopy, Pencil, Trash2, Loader2, Upload, CheckCircle2, XCircle, X, Lightbulb } from 'lucide-react';
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
import { getProviderBadgeColor } from '../../components/ui/providerBadges';
import { AppRole } from '../../types/roles';
import type { ServiceLifecycleFields } from '../../types/services';
import ServiceStatusBadge from '../../components/ui/ServiceStatusBadge';
import UsedByButton from '../../components/services/UsedByButton';
import SystemServiceBadge from '../../components/services/SystemServiceBadge';
import ServiceUsageModal from '../../components/services/ServiceUsageModal';
import { useServiceConnectionTest } from '../../components/services/useServiceConnectionTest';
import { SERVICE_USAGE_STRINGS } from '../../utils/serviceLifecycle';

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
  auto_move_to_service_id?: number | null;
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
    <div className="p-6 text-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
      <p className="mt-2 text-gray-600">Loading AI services...</p>
    </div>
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
        <div>
          <h2 className="text-xl font-semibold text-gray-900">AI Services</h2>
          <p className="text-gray-600">Manage language models and AI providers for your agents</p>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <button
              onClick={() => setShowImportModal(true)}
              className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg flex items-center"
            >
              <Upload className="w-4 h-4 mr-2" />Import
            </button>
            <button
              onClick={handleCreate}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>Add AI Service
            </button>
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
                {canEdit && !service.is_system ? (
                  <button type="button" className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left" onClick={() => handleEdit(service.service_id)}>
                    {service.name}
                  </button>
                ) : (
                  <span className="text-sm font-medium text-gray-900">{service.name}</span>
                )}
                {service.is_system && <SystemServiceBadge />}
              </span>
            )
          },
          { header: 'Model', accessor: 'model_name' },
          { header: 'Provider', render: (service: AIService) => (
            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getProviderBadgeColor(service.provider)}`}>
              {service.provider}
            </span>
          )},
          { header: 'Status', render: (service: AIService) => (
            <ServiceStatusBadge needsApiKey={service.needs_api_key} lastError={service.last_error} lastErrorAt={service.last_error_at} lifecycleStatus={service.lifecycle_status} endOfServiceAt={service.end_of_service_at} deprecationNotice={service.deprecation_notice} />
          )},
          { header: 'Created', render: (service: any) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
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
                  icon: exportingServiceId === service.service_id ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowDownToLine className="w-4 h-4" />,
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
        <div className={`mb-4 rounded-lg p-4 ${notification.type === 'success' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <div className="flex items-start">
            <div className="flex-shrink-0">
              {notification.type === 'success'
                ? <CheckCircle2 className="w-5 h-5 text-green-400" />
                : <XCircle className="w-5 h-5 text-red-400" />}
            </div>
            <div className="ml-3 flex-1">
              <p className={`text-sm font-medium ${notification.type === 'success' ? 'text-green-800' : 'text-red-800'}`}>
                {notification.message}
              </p>
            </div>
            <button
              onClick={() => setNotification(null)}
              className={`ml-3 inline-flex rounded-md p-1.5 ${notification.type === 'success' ? 'text-green-500 hover:bg-green-100' : 'text-red-500 hover:bg-red-100'} focus:outline-none`}
            >
              <span className="sr-only">Dismiss</span>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0"><Lightbulb className="w-5 h-5 text-blue-400" /></div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">About AI Services</h3>
            <div className="mt-2 text-sm text-blue-700">
              <p>AI Services define the language models your agents can use. Configure OpenAI, Azure OpenAI, Anthropic Claude, or local models like Ollama. Each service requires proper authentication and endpoint configuration.</p>
            </div>
          </div>
        </div>
      </div>

      {isModalOpen && !editingService && (
        <ServiceWizard
          isOpen
          kind="ai"
          scope="app"
          appId={appId ? Number.parseInt(appId) : undefined}
          existingNames={services.map((s) => s.name)}
          availableAiServices={services}
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
          availableAiServices={services}
          onClose={handleClose}
          onSave={handleSave}
        />
      )}

      {connectionTestModal}

      {usageService && appId && (
        <ServiceUsageModal
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