import { useParams } from 'react-router-dom';
import { useState } from 'react';
import Modal from '../../components/ui/Modal';
import EmbeddingServiceForm from '../../components/forms/EmbeddingServiceForm';
import ActionDropdown from '../../components/ui/ActionDropdown';
import ImportModal from '../../components/ui/ImportModal';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import { getProviderBadgeColor } from '../../components/ui/providerBadges';
import { AppRole } from '../../types/roles';
import type { ConflictMode, ImportResponse } from '../../components/ui/ImportModal';

interface EmbeddingService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
  needs_api_key?: boolean;
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
  } = useServicesManager<EmbeddingService>(appId, api as any, cache as any);

  const [showImportModal, setShowImportModal] = useState(false);
  const [exportingServiceId, setExportingServiceId] = useState<number | null>(null);
  const [notification, setNotification] = useState<{message: string; type: 'success' | 'error'} | null>(null);

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
        forceReload();
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
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-600 mx-auto"></div>
      <p className="mt-2 text-gray-600">Loading embedding services...</p>
    </div>
  );

  if (error) return (
    <div className="p-6">
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-600">Error: {error}</p>
        <button onClick={() => { setIsModalOpen(false); setEditingService(null); }} className="mt-2 text-red-800 hover:text-red-900 underline">Try again</button>
      </div>
    </div>
  );

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Embedding Services</h2>
          <p className="text-gray-600">Manage vector embedding models for document processing and search</p>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <button
              onClick={() => setShowImportModal(true)}
              className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">📤</span>Import
            </button>
            <button onClick={handleCreate} className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center">
              <span className="mr-2">+</span>Add Embedding Service
            </button>
          </div>
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      {notification && (
        <div className={`mb-4 rounded-lg p-4 ${notification.type === 'success' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <span className={`text-xl ${notification.type === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                {notification.type === 'success' ? '✓' : '✗'}
              </span>
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
              <span className="text-lg">×</span>
            </button>
          </div>
        </div>
      )}

      <Table
        data={services}
        keyExtractor={(service) => (service as any).service_id.toString()}
        columns={[
          { header: 'Name', render: (service: EmbeddingService) => (
            canEdit ? (
              <button type="button" className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left" onClick={() => handleEdit(service.service_id)}>{service.name}</button>
            ) : (
              <span className="text-sm font-medium text-gray-900">{service.name}</span>
            )
          ) },
          { header: 'Model', accessor: 'model_name' },
          { header: 'Provider', render: (service: EmbeddingService) => (
            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getProviderBadgeColor(service.provider)}`}>{service.provider}</span>
          ) },
          { header: 'Status', render: (service: EmbeddingService) => (
            service.needs_api_key ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                ⚠ API Key Required
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Ready
              </span>
            )
          ) },
          { header: 'Created', render: (service: EmbeddingService) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: EmbeddingService) => (
            canEdit ? (
              <ActionDropdown actions={[
                {
                  label: exportingServiceId === service.service_id ? 'Exporting...' : 'Export',
                  onClick: () => void handleExport(service.service_id),
                  icon: exportingServiceId === service.service_id ? '⏳' : '📥',
                  variant: 'primary' as const,
                  disabled: exportingServiceId === service.service_id
                },
                { label: 'Edit', onClick: () => void handleEdit(service.service_id), icon: '✏️', variant: 'primary' },
                { label: 'Delete', onClick: () => void handleDelete(service.service_id), icon: '🗑️', variant: 'danger' }
              ]} size="sm" />
            ) : (
              <span className="text-gray-400 text-sm">View only</span>
            )
          ) }
        ]}
        emptyIcon="📊"
        emptyMessage="No Embedding Services"
        emptySubMessage="Add your first embedding service to enable vector search and document processing."
        loading={loading}
      />

      {!loading && services.length === 0 && canEdit && (
        <div className="text-center py-6">
          <button onClick={handleCreate} className="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg">Add First Embedding Service</button>
        </div>
      )}

      <Alert type="info" title="About Embedding Services" message="Embedding services convert text into high-dimensional vectors for semantic search, document similarity, and RAG (Retrieval-Augmented Generation) applications. Popular models include OpenAI's text-embedding-3-large, Mistral's mistral-embed, and local options like Ollama." className="mt-6" />

      <Modal isOpen={isModalOpen} onClose={handleClose} title={editingService ? 'Edit Embedding Service' : 'Create New Embedding Service'}>
        <EmbeddingServiceForm embeddingService={editingService} onSubmit={handleSave} onCancel={handleClose} />
      </Modal>

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