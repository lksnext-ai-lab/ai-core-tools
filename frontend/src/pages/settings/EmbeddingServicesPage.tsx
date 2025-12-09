import { useParams } from 'react-router-dom';
import Modal from '../../components/ui/Modal';
import EmbeddingServiceForm from '../../components/forms/EmbeddingServiceForm';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import { getProviderBadgeColor } from '../../components/ui/providerBadges';
import { AppRole } from '../../types/roles';

interface EmbeddingService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
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
  } = useServicesManager<EmbeddingService>(appId, api as any, cache as any);

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
          <button onClick={handleCreate} className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center">
            <span className="mr-2">+</span>{' '}Add Embedding Service
          </button>
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

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
          { header: 'Created', render: (service: EmbeddingService) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: EmbeddingService) => (
            canEdit ? (
              <ActionDropdown actions={[ { label: 'Edit', onClick: () => void handleEdit(service.service_id), icon: '✏️', variant: 'primary' }, { label: 'Delete', onClick: () => void handleDelete(service.service_id), icon: '🗑️', variant: 'danger' } ]} size="sm" />
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
    </div>
  );
}

export default EmbeddingServicesPage;