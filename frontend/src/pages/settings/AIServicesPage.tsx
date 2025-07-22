import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import SettingsLayout from '../../components/layout/SettingsLayout';
import Modal from '../../components/ui/Modal';
import AIServiceForm from '../../components/forms/AIServiceForm';
import { apiService } from '../../services/api';

interface AIService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
}

function AIServicesPage() {
  const { appId } = useParams();
  const [services, setServices] = useState<AIService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingService, setEditingService] = useState<any>(null);

  // Load AI services from the API
  useEffect(() => {
    loadAIServices();
  }, [appId]);

  async function loadAIServices() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAIServices(parseInt(appId));
      setServices(response);
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
      setServices(services.filter(s => s.service_id !== serviceId));
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

  async function handleSaveService(data: any) {
    if (!appId) return;

    try {
      if (editingService && editingService.service_id !== 0) {
        // Update existing service
        await apiService.updateAIService(parseInt(appId), editingService.service_id, data);
      } else {
        // Create new service
        await apiService.createAIService(parseInt(appId), data);
      }
      
      // Reload services list
      await loadAIServices();
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
      <SettingsLayout>
        <div className="p-6 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading AI services...</p>
        </div>
      </SettingsLayout>
    );
  }

  if (error) {
    return (
      <SettingsLayout>
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error: {error}</p>
            <button 
              onClick={() => loadAIServices()}
              className="mt-2 text-red-800 hover:text-red-900 underline"
            >
              Try again
            </button>
          </div>
        </div>
      </SettingsLayout>
    );
  }

  return (
    <SettingsLayout>
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">AI Services</h2>
            <p className="text-gray-600">Manage language models and AI providers for your agents</p>
          </div>
          <button 
            onClick={handleCreateService}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
          >
            <span className="mr-2">+</span>
            Add AI Service
          </button>
        </div>

        {/* Services Table */}
        {services.length > 0 ? (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Provider
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {services.map((service) => (
                  <tr key={service.service_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">{service.name}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm text-gray-900">{service.model_name}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getProviderBadgeColor(service.provider)}`}>
                        {service.provider}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <div className="flex space-x-2">
                        <button 
                          onClick={() => handleEditService(service.service_id)}
                          className="text-blue-600 hover:text-blue-900"
                        >
                          Edit
                        </button>
                        <button 
                          onClick={() => handleDelete(service.service_id)}
                          className="text-red-600 hover:text-red-900"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">🤖</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No AI Services</h3>
            <p className="text-gray-600 mb-6">
              Add your first AI service to start using language models in your agents.
            </p>
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
    </SettingsLayout>
  );
}

export default AIServicesPage; 