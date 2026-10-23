import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { Users, Upload, ArrowDownToLine, Pencil, Trash2,  BarChart2, Globe } from 'lucide-react';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import ActionDropdown from '../../components/ui/ActionDropdown';
import ImportModal from '../../components/ui/ImportModal';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import { ProviderBadge } from '../../components/ui/Badge';
import { AppRole } from '../../types/roles';
import type { ServiceLifecycleFields } from '../../types/services';
import ServiceStatusBadge from '../../components/ui/ServiceStatusBadge';
import UsedByButton from '../../components/services/UsedByButton';
import SystemServiceBadge from '../../components/services/SystemServiceBadge';
import ServiceUsageModal from '../../components/services/ServiceUsageModal';
import { SERVICE_USAGE_STRINGS } from '../../utils/serviceLifecycle';
import type { ConflictMode, ImportResponse } from '../../components/ui/ImportModal';
import { getServiceApiClient } from '../../components/services/serviceApi';
import { useServiceConnectionTest } from '../../components/services/useServiceConnectionTest';
import Title from '../../components/ui/Title';
import LoadingState from '../../components/ui/LoadingState';
import ButtonApp from '../../components/ui/ButtonApp';
import BackgroundImage from '../../components/ui/BackgroundImage';
import SidePanel from '../../components/ui/SidePanel';
import Spinner from '../../components/ui/Spinner';

interface EmbeddingService extends Partial<ServiceLifecycleFields> {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
  needs_api_key?: boolean;
  last_error?: string | null;
  last_error_at?: string | null;
  is_system?: boolean;
}

function EmbeddingServicesPage() {
  const { appId } = useParams();
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const api = {
    getAll: (id: number) => import('../../services/api').then(m => m.apiService.getEmbeddingServices(id)),
    getOne: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.getEmbeddingService(id, sid)),
    create: (id: number, data: any) => import('../../services/api').then(m => m.apiService.createEmbeddingService(id, data)),
    update: (id: number, sid: number, data: any) => import('../../services/api').then(m => m.apiService.updateEmbeddingService(id, sid, data)),
    delete: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.deleteEmbeddingService(id, sid)),
  };

  const cache = {
    get: (id: string) => settingsCache.getEmbeddingServices(id),
    set: (id: string, data: any[]) => settingsCache.setEmbeddingServices(id, data),
    invalidate: (id: string) => settingsCache.invalidateEmbeddingServices(id),
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
    handleSave,
    setIsModalOpen,
    setEditingService,
    forceReload,
  } = useServicesManager<EmbeddingService>(appId, api as any, cache as any, { entity: 'embedding service' });

  const [showImportModal, setShowImportModal] = useState(false);
  const [usageService, setUsageService] = useState<{ id: number; name: string } | null>(null);
  const [exportingServiceId, setExportingServiceId] = useState<number | null>(null);
  const [notification, setNotification] = useState<{message: string; type: 'success' | 'error'} | null>(null);
  const { testAction, modal: connectionTestModal } = useServiceConnectionTest('embedding');

  async function testConnection(serviceId: number) {
    if (!appId) throw new Error('App ID not found');
    const numericAppId = Number.parseInt(appId, 10);
    const apiService = (await import('../../services/api')).apiService;
    const detail = await apiService.getEmbeddingService(numericAppId, serviceId);
    return getServiceApiClient('embedding', 'app', numericAppId).testConnection({
      name: detail.name,
      provider: detail.provider,
      model_name: detail.model_name,
      api_key: detail.api_key,
      base_url: detail.base_url,
      api_version: detail.api_version,
      aws_access_key_id: detail.aws_access_key_id,
      aws_region: detail.aws_region,
    }, serviceId);
  }

  async function handleExport(serviceId: number) {
    if (!appId) return;
    setExportingServiceId(serviceId);
    
    try {
      const apiService = (await import('../../services/api')).apiService;
      const blob = await apiService.exportEmbeddingService(Number.parseInt(appId), serviceId);
      
      // Find service name for filename
      const service = services.find(s => s.service_id === serviceId);
      const serviceName = service?.name || 'embedding-service';
      const sanitizedName = serviceName.replaceAll(/[^a-z0-9]/gi, '-').toLowerCase();
      const timestamp = new Date().toISOString().split('T')[0];
      const filename = `embedding-service-${sanitizedName}-${timestamp}.json`;
      
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
      const result = await apiService.importEmbeddingService(
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
    <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant='titSecundario' titulo="Embedding Services" subtitulo="Manage vector embedding models for document processing and search" />
        </div>
        <LoadingState variant="page" message="Loading embedding services..." />
      </div>
  );

  if (error) return (
    <div className="p-6">
      <div className="flex items-center justify-between">
          <Title variant='titSecundario' titulo="Embedding Services" subtitulo="Manage vector embedding models for document processing and search" />
        </div>

      <Alert
        type="error"
        message={(
          <>
            Error: {error}
            <button type="button" onClick={() => { setIsModalOpen(false); setEditingService(null); }} className="mt-2 block underline">Try again</button>
          </>
        )}
      />
    </div>
  );

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <Title variant='titSecundario' titulo="Embedding Services" subtitulo="Manage vector embedding models for document processing and search" />
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
              label="Add Embedding Service"
              onClick={handleCreate}
              icon={<span aria-hidden="true">+</span>}
              variant="primary"
              size="medium"
            />
          </div>
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      {notification && (
        <Alert
          type={notification.type}
          message={notification.message}
          onDismiss={() => setNotification(null)}
          className="mb-4"
        />
      )}

      <Table
        data={services}
        keyExtractor={(service) => (service as any).service_id.toString()}
        columns={[
          { header: 'Name', render: (service: EmbeddingService) => (
            <div className="flex items-center gap-1.5">
              <BackgroundImage icon={Globe} variant='marron' />
              {canEdit && !service.is_system ? (
                <button type="button" className="text-sm font-medium text-fg dark:text-fg-dark text-left" onClick={() => handleEdit(service.service_id)}>{service.name}</button>
              ) : (
                <span className="text-sm font-medium text-fg dark:text-fg-dark">{service.name}</span>
              )}
              {service.is_system && (
                <SystemServiceBadge />
              )}
            </div>
          ) },
          { header: 'Model', accessor: 'model_name', className: 'text-xs font-medium text-fg-secondary dark:text-fg-secondary-dark' },
          { header: 'Provider', render: (service: EmbeddingService) => (
            <ProviderBadge provider={service.provider} />
          ) },
          { header: 'Status', render: (service: EmbeddingService) => (
            <ServiceStatusBadge needsApiKey={service.needs_api_key} lastError={service.last_error} lastErrorAt={service.last_error_at} lifecycleStatus={service.lifecycle_status} endOfServiceAt={service.end_of_service_at} deprecationNotice={service.deprecation_notice} />
          ) },
          { header: 'Created', className: 'text-xs font-medium text-fg-secondary dark:text-fg-secondary-dark', render: (service: EmbeddingService) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: EmbeddingService) => (
            service.is_system ? (
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
                { label: 'Edit', onClick: () => void handleEdit(service.service_id), icon: <Pencil className="w-4 h-4" />, variant: 'primary' },
                { label: 'Delete', onClick: () => void handleDelete(service.service_id), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' }
              ]} size="sm" />
            ) : (
              <UsedByButton serviceName={service.name} onClick={() => setUsageService({ id: service.service_id, name: service.name })} />
            )
          ) }
        ]}
        emptyIcon={<BarChart2 className="w-10 h-10 text-gray-300" />}
        emptyMessage="No Embedding Services"
        emptySubMessage="Add your first embedding service to enable vector search and document processing."
        loading={loading}
      />

      {!loading && services.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label="Add First Embedding Service"
            onClick={handleCreate}
            icon={<span aria-hidden="true">+</span>}
            variant="primary"
            size="medium"
          />
        </div>
      )}

      <Alert type="info" title="About Embedding Services" message="Embedding services convert text into high-dimensional vectors for semantic search, document similarity, and RAG (Retrieval-Augmented Generation) applications. Popular models include OpenAI's text-embedding-3-large, Mistral's mistral-embed, and local options like Ollama." className="mt-6" />

      {isModalOpen && !editingService && (
        <ServiceWizard
          isOpen
          kind="embedding"
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
          kind="embedding"
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
            title="Embedding Services"
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
              kind="embedding"
              scope="app"
              canNavigate={hasMinRole(AppRole.EDITOR)}
              appId={Number.parseInt(appId, 10)}
              serviceId={usageService.id}
              serviceName={usageService.name}
              onClose={() => setUsageService(null)}
            />
          </SidePanel>
        </div>
      )}

      {connectionTestModal}

      {/* Import Modal */}
      <ImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImport={handleImport}
        componentType="embedding_service"
        componentLabel="Embedding Service"
      />
    </div>
  );

}

export default EmbeddingServicesPage;