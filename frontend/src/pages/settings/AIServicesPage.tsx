import { useParams } from 'react-router-dom';
import Modal from '../../components/ui/Modal';
import AIServiceForm from '../../components/forms/AIServiceForm';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import { getProviderBadgeColor } from '../../components/ui/providerBadges';

interface AIService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
}

function AIServicesPage() {
  const { appId } = useParams();
  const settingsCache = useSettingsCache();
  const { isAdmin, userRole } = useAppRole(appId);

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
  } = useServicesManager<AIService>(appId, api as any, cache as any);

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
        {isAdmin && (
          <button onClick={handleCreate} className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center">
            <span className="mr-2">+</span>{' '}Add AI Service
          </button>
        )}
      </div>

      {!isAdmin && <ReadOnlyBanner userRole={userRole} />}

      <Table
        data={services}
        keyExtractor={(service) => (service as any).service_id.toString()}
        columns={[
          {
            header: 'Name',
            render: (service: AIService) => (
              <button type="button" className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left" onClick={() => handleEdit(service.service_id)}>
                {service.name}
              </button>
            )
          },
          { header: 'Model', accessor: 'model_name' },
          { header: 'Provider', render: (service: AIService) => (
            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getProviderBadgeColor(service.provider)}`}>
              {service.provider}
            </span>
          )},
          { header: 'Created', render: (service: any) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: AIService) => (
            isAdmin ? (
              <ActionDropdown actions={[
                { label: 'Edit', onClick: () => void handleEdit(service.service_id), icon: '✏️', variant: 'primary' },
                { label: 'Copy', onClick: () => void handleCopy(service.service_id), icon: '📋', variant: 'primary' },
                { label: 'Delete', onClick: () => void handleDelete(service.service_id), icon: '🗑️', variant: 'danger' }
              ]} size="sm" />
            ) : (
               <span className="text-gray-400 text-sm">View only</span>
            )
          ) }
        ]}
        emptyIcon="🤖"
        emptyMessage="No AI Services"
        emptySubMessage="Add your first AI service to start using language models in your agents."
        loading={loading}
      />

      {!loading && services.length === 0 && isAdmin && (
        <div className="text-center py-6">
          <button onClick={handleCreate} className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg">Add First AI Service</button>
        </div>
      )}

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0"><span className="text-blue-400 text-xl">💡</span></div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">About AI Services</h3>
            <div className="mt-2 text-sm text-blue-700">
              <p>AI Services define the language models your agents can use. Configure OpenAI, Azure OpenAI, Anthropic Claude, or local models like Ollama. Each service requires proper authentication and endpoint configuration.</p>
            </div>
          </div>
        </div>
      </div>

      <Modal isOpen={isModalOpen} onClose={handleClose} title={editingService ? 'Edit AI Service' : 'Create New AI Service'}>
        <AIServiceForm aiService={editingService} onSubmit={handleSave} onCancel={handleClose} />
      </Modal>
    </div>
  );
}

export default AIServicesPage;