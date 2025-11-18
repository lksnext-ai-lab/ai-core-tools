import { useState, useEffect } from 'react';
import FormActions from './FormActions';

export interface ServiceFormData {
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
}

export interface ServiceData {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  created_at: string;
}

export interface ProviderConfig {
  value: string;
  name: string;
}

export interface ProviderDefaults {
  baseUrl: string;
  modelPlaceholder: string;
}

interface BaseServiceFormProps {
  service?: ServiceData | null;
  onSubmit: (data: ServiceFormData) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
  providers: ProviderConfig[];
  getProviderDefaults: (provider: string) => ProviderDefaults;
  formTitle: string;
  serviceType: string; // "AI Service" or "Embedding Service"
}

function BaseServiceForm({
  service,
  onSubmit,
  onCancel,
  providers,
  getProviderDefaults,
  formTitle,
  serviceType
}: Readonly<BaseServiceFormProps>) {
  const [formData, setFormData] = useState<ServiceFormData>({
    name: '',
    provider: '',
    model_name: '',
    api_key: '',
    base_url: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!service && service.service_id !== 0;

  // Initialize form with existing service data
  useEffect(() => {
    if (service) {
      setFormData({
        name: service.name || '',
        provider: service.provider || '',
        model_name: service.model_name || '',
        api_key: service.api_key || '',
        base_url: service.base_url || ''
      });
    }
  }, [service]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));

    // Auto-fill base URL when provider changes
    if (name === 'provider' && value) {
      const defaults = getProviderDefaults(value);
      if (!formData.base_url || formData.base_url === '') {
        setFormData(prev => ({
          ...prev,
          base_url: defaults.baseUrl
        }));
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    
    // Validate required fields
    if (!formData.name.trim()) {
      setError('Name is required');
      return;
    }
    if (!formData.provider) {
      setError('Provider is required');
      return;
    }
    if (!formData.model_name.trim()) {
      setError('Model name is required');
      return;
    }
    if (!formData.base_url.trim()) {
      setError('Base URL is required');
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit(formData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentProviderDefaults = formData.provider ? getProviderDefaults(formData.provider) : null;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">
        {isEditing ? `Edit ${serviceType}` : `Create New ${serviceType}`}
      </h2>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-800 text-sm">{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Name */}
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
            Service Name *
          </label>
          <input
            type="text"
            id="name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="My Service"
            required
          />
        </div>

        {/* Provider */}
        <div>
          <label htmlFor="provider" className="block text-sm font-medium text-gray-700 mb-2">
            Provider *
          </label>
          <select
            id="provider"
            name="provider"
            value={formData.provider}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            required
          >
            <option value="">Select a provider</option>
            {providers.map(provider => (
              <option key={provider.value} value={provider.value}>
                {provider.name}
              </option>
            ))}
          </select>
        </div>

        {/* Model Name */}
        <div>
          <label htmlFor="model_name" className="block text-sm font-medium text-gray-700 mb-2">
            Model Name *
          </label>
          <input
            type="text"
            id="model_name"
            name="model_name"
            value={formData.model_name}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder={currentProviderDefaults?.modelPlaceholder || 'model-name'}
            required
          />
          {currentProviderDefaults && (
            <p className="mt-1 text-sm text-gray-500">
              Example: {currentProviderDefaults.modelPlaceholder}
            </p>
          )}
        </div>

        {/* Base URL */}
        <div>
          <label htmlFor="base_url" className="block text-sm font-medium text-gray-700 mb-2">
            Base URL *
          </label>
          <input
            type="text"
            id="base_url"
            name="base_url"
            value={formData.base_url}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="https://api.example.com/v1"
            required
          />
          {currentProviderDefaults && (
            <p className="mt-1 text-sm text-gray-500">
              Default: {currentProviderDefaults.baseUrl}
            </p>
          )}
        </div>

        {/* API Key */}
        <div>
          <label htmlFor="api_key" className="block text-sm font-medium text-gray-700 mb-2">
            API Key {formData.provider !== 'Custom' && formData.provider !== 'Ollama' && '*'}
          </label>
          <input
            type="password"
            id="api_key"
            name="api_key"
            value={formData.api_key}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="sk-..."
            required={formData.provider !== 'Custom' && formData.provider !== 'Ollama'}
          />
          <p className="mt-1 text-sm text-gray-500">
            {formData.provider === 'Ollama' || formData.provider === 'Custom' 
              ? 'Optional for local/custom providers' 
              : 'Required for cloud providers'}
          </p>
        </div>

        {/* Form Actions */}
        <FormActions
          onCancel={onCancel}
          isSubmitting={isSubmitting}
          isEditing={isEditing}
          submitButtonColor={serviceType === 'AI' ? 'blue' : 'green'}
        />
      </form>
    </div>
  );
}

export default BaseServiceForm;
