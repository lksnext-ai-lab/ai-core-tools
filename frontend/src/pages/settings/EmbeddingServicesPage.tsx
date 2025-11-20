import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import Modal from '../../components/ui/Modal';
import EmbeddingServiceForm from '../../components/forms/EmbeddingServiceForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';

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
  const { isAdmin, userRole } = useAppRole(appId);
  const [services, setServices] = useState<EmbeddingService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingService, setEditingService] = useState<any>(null);

  // Load embedding services from cache or API
  useEffect(() => {
    loadEmbeddingServices();
  }, [appId]);

  async function loadEmbeddingServices() {
    if (!appId) return;
    
    // Check if we have cached data first
    const cachedData = settingsCache.getEmbeddingServices(appId);
    if (cachedData) {
      setServices(cachedData);
      setLoading(false);
      return;
    }
    
    // If no cache, load from API
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getEmbeddingServices(parseInt(appId));
      setServices(response);
      // Cache the response
      settingsCache.setEmbeddingServices(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load embedding services');
      console.error('Error loading embedding services:', err);
    } finally {
      setLoading(false);
    }
  }

  async function forceReloadEmbeddingServices() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getEmbeddingServices(parseInt(appId));
      setServices(response);
      // Cache the response
      settingsCache.setEmbeddingServices(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load embedding services');
      console.error('Error loading embedding services:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(serviceId: number) {
    if (!confirm('Are you sure you want to delete this embedding service?')) {
      return;
    }

    if (!appId) return;

    try {
      await apiService.deleteEmbeddingService(parseInt(appId), serviceId);
      // Remove from local state
      const newServices = services.filter(s => s.service_id !== serviceId);
      setServices(newServices);
      // Update cache
      settingsCache.setEmbeddingServices(appId, newServices);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete service');
      console.error('Error deleting embedding service:', err);
    }
  }

  function handleCreateService() {
    setEditingService(null);
    setIsModalOpen(true);
  }

  async function handleEditService(serviceId: number) {
    if (!appId) return;
    
    try {
      const service = await apiService.getEmbeddingService(parseInt(appId), serviceId);
      setEditingService(service);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load service details');
      console.error('Error loading embedding service:', err);
    }
  }

  async function handleSaveService(data: any) {
    if (!appId) return;

    try {
      if (editingService && editingService.service_id !== 0) {
        // Update existing service - no need to invalidate cache
        await apiService.updateEmbeddingService(parseInt(appId), editingService.service_id, data);
        await loadEmbeddingServices();
      } else {
        // Create new service - invalidate cache and force reload
        await apiService.createEmbeddingService(parseInt(appId), data);
        settingsCache.invalidateEmbeddingServices(appId);
        await forceReloadEmbeddingServices();
      }
      
      setIsModalOpen(false);
      setEditingService(null);
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to save service');
    }
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingService(null);
  }

  const getProviderBadgeColor = (provider: string) => {
    const colors: Record<string, string> = {
      'openai': 'bg-green-100 text-green-800',
      'OpenAI': 'bg-green-100 text-green-800',
      'azure': 'bg-blue-100 text-blue-800',
      'Azure': 'bg-blue-100 text-blue-800',
      'mistralai': 'bg-purple-100 text-purple-800',
      'MistralAI': 'bg-purple-100 text-purple-800',
      'ollama': 'bg-orange-100 text-orange-800',
      'Ollama': 'bg-orange-100 text-orange-800',
      'custom': 'bg-gray-100 text-gray-800',
      'Custom': 'bg-gray-100 text-gray-800',
    };
    return colors[provider] || 'bg-gray-100 text-gray-800';
  };

  if (loading) {
    return (
      
        <div className="p-6 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading embedding services...</p>
        </div>
      
    );
  }

  if (error) {
    return (
      
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error: {error}</p>
            <button 
              onClick={() => loadEmbeddingServices()}
              className="mt-2 text-red-800 hover:text-red-900 underline"
            >
              Try again
            </button>
          </div>
        </div>
      
    );
  }

  return (
    
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Embedding Services</h2>
            <p className="text-gray-600">Manage vector embedding models for document processing and search</p>
          </div>
          {isAdmin && (
            <button 
              onClick={handleCreateService}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>
              {' '}Add Embedding Service
            </button>
          )}
        </div>
        
        {/* Read-only banner for non-admins */}
        {!isAdmin && <ReadOnlyBanner userRole={userRole} />}

        {/* Services Table */}
        <Table
          data={services}
          keyExtractor={(service) => service.service_id.toString()}
          columns={[
            {
              header: 'Name',
              render: (service) => (
                <button
                  type="button"
                  className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left"
                  onClick={() => void handleEditService(service.service_id)}
                >
                  {service.name}
                </button>
              )
            },
            {
              header: 'Model',
              accessor: 'model_name'
            },
            {
              header: 'Provider',
              render: (service) => (
                <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getProviderBadgeColor(service.provider)}`}>
                  {service.provider}
                </span>
              )
            },
            {
              header: 'Created',
              render: (service) => 
                service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A'
            },
            {
              header: 'Actions',
              className: 'relative',
              render: (service) => (
                isAdmin ? (
                  <ActionDropdown
                    actions={[
                      {
                        label: 'Edit',
                        onClick: () => { void handleEditService(service.service_id); },
                        icon: '✏️',
                        variant: 'primary'
                      },
                      {
                        label: 'Delete',
                        onClick: () => { void handleDelete(service.service_id); },
                        icon: '🗑️',
                        variant: 'danger'
                      }
                    ]}
                    size="sm"
                  />
                ) : (
                  <span className="text-gray-400 text-sm">View only</span>
                )
              )
            }
          ]}
          emptyIcon="📊"
          emptyMessage="No Embedding Services"
          emptySubMessage="Add your first embedding service to enable vector search and document processing."
          loading={loading}
        />

        {!loading && services.length === 0 && isAdmin && (
          <div className="text-center py-6">
            <button 
              onClick={handleCreateService}
              className="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg"
            >
              Add First Embedding Service
            </button>
          </div>
        )}

        {/* Info Box */}
        <Alert 
          type="info" 
          title="About Embedding Services" 
          message="Embedding services convert text into high-dimensional vectors for semantic search, document similarity, and RAG (Retrieval-Augmented Generation) applications. Popular models include OpenAI's text-embedding-3-large, Mistral's mistral-embed, and local options like Ollama."
          className="mt-6"
        />

        {/* Create/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={editingService ? 'Edit Embedding Service' : 'Create New Embedding Service'}
        >
          <EmbeddingServiceForm
            embeddingService={editingService}
            onSubmit={handleSaveService}
            onCancel={handleCloseModal}
          />
        </Modal>
      </div>
    
  );
}

export default EmbeddingServicesPage; 