import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import Modal from '../../components/ui/Modal';
import AIServiceForm from '../../components/forms/AIServiceForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';

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
  const { isOwner, isAdmin, userRole } = useAppRole(appId);
  const [services, setServices] = useState<AIService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingService, setEditingService] = useState<any>(null);

  // Load AI services from cache or API
  useEffect(() => {
    loadAIServices();
  }, [appId]);

  async function loadAIServices() {
    if (!appId) return;
    
    // Check if we have cached data first
    const cachedData = settingsCache.getAIServices(appId);
    if (cachedData) {
      setServices(cachedData);
      setLoading(false);
      return;
    }
    
    // If no cache, load from API
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAIServices(parseInt(appId));
      setServices(response);
      // Cache the response
      settingsCache.setAIServices(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load AI services');
      console.error('Error loading AI services:', err);
    } finally {
      setLoading(false);
    }
  }

  async function forceReloadAIServices() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAIServices(parseInt(appId));
      setServices(response);
      // Cache the response
      settingsCache.setAIServices(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load AI services');
      console.error('Error loading AI services:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(serviceId: number) {
    if (!confirm('Are you sure you want to delete this AI service?')) {
      return;
    }

    if (!appId) return;

    try {
      await apiService.deleteAIService(parseInt(appId), serviceId);
      // Remove from local state
      const newServices = services.filter(s => s.service_id !== serviceId);
      setServices(newServices);
      // Update cache
      settingsCache.setAIServices(appId, newServices);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete service');
      console.error('Error deleting AI service:', err);
    }
  }

  function handleCreateService() {
    setEditingService(null);
    setIsModalOpen(true);
  }

  async function handleEditService(serviceId: number) {
    if (!appId) return;
    
    try {
      const service = await apiService.getAIService(parseInt(appId), serviceId);
      setEditingService(service);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load service details');
      console.error('Error loading AI service:', err);
    }
  }

  async function handleCopyService(serviceId: number) {
    if (!appId) return;
    try {
      await apiService.copyAIService(parseInt(appId), serviceId);
      // Invalidate cache and force reload
      settingsCache.invalidateAIServices(appId);
      await forceReloadAIServices();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to copy service');
      console.error('Error copying AI service:', err);
    }
  }

  async function handleSaveService(data: any) {
    if (!appId) return;

    try {
      if (editingService && editingService.service_id !== 0) {
        // Update existing service - no need to invalidate cache
        await apiService.updateAIService(parseInt(appId), editingService.service_id, data);
        // Just reload normally since cache is still valid
        await loadAIServices();
      } else {
        // Create new service - invalidate cache and force reload
        await apiService.createAIService(parseInt(appId), data);
        settingsCache.invalidateAIServices(appId);
        // Force reload from API to get fresh data
        await forceReloadAIServices();
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
      'azure': 'bg-blue-100 text-blue-800',
      'anthropic': 'bg-purple-100 text-purple-800',
      'ollama': 'bg-orange-100 text-orange-800',
    };
    return colors[provider] || 'bg-gray-100 text-gray-800';
  };

  if (loading) {
    return (
      <div className="p-6 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-2 text-gray-600">Loading AI services...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert 
          type="error" 
          message={error}
          onDismiss={() => loadAIServices()}
        />
      </div>
    );
  }

  return (
    <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">AI Services</h2>
            <p className="text-gray-600">Manage language models and AI providers for your agents</p>
          </div>
          {isAdmin && (
            <button 
              onClick={handleCreateService}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>
              Add AI Service
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
                <div 
                  className="text-sm font-medium text-gray-900 cursor-pointer hover:text-blue-600 transition-colors"
                  onClick={() => handleEditService(service.service_id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleEditService(service.service_id);
                    }
                  }}
                >
                  {service.name}
                </div>
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
                        onClick: () => void handleEditService(service.service_id),
                        icon: '✏️',
                        variant: 'primary'
                      },
                      {
                        label: 'Copy',
                        onClick: () => void handleCopyService(service.service_id),
                        icon: '📋',
                        variant: 'primary'
                      },
                      {
                        label: 'Delete',
                        onClick: () => void handleDelete(service.service_id),
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
          emptyIcon="🤖"
          emptyMessage="No AI Services"
          emptySubMessage="Add your first AI service to start using language models in your agents."
          loading={loading}
        />

        {!loading && services.length === 0 && isAdmin && (
          <div className="text-center py-6">
            <button 
              onClick={handleCreateService}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg"
            >
              Add First AI Service
            </button>
          </div>
        )}

        {/* Info Box */}
        <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <span className="text-blue-400 text-xl">💡</span>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-blue-800">
                About AI Services
              </h3>
              <div className="mt-2 text-sm text-blue-700">
                <p>
                  AI Services define the language models your agents can use. Configure OpenAI, Azure OpenAI, 
                  Anthropic Claude, or local models like Ollama. Each service requires proper authentication 
                  and endpoint configuration.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Create/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={editingService ? 'Edit AI Service' : 'Create New AI Service'}
        >
          <AIServiceForm
            aiService={editingService}
            onSubmit={handleSaveService}
            onCancel={handleCloseModal}
          />  
        </Modal>
      </div>
  );
}

export default AIServicesPage; 